import os
import re
import sys
import time
import requests
import subprocess
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# ==============================================================================
# CẤU HÌNH API & CÁC MODEL GEMINI ĐANG HOẠT ĐỘNG
# ==============================================================================
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")

FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
    "gemini-3.6-flash",
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.7-flash",
]

# Kết nối ChromaDB
_cached_chroma_client = None
_cached_collection = None


def get_vector_db(chroma_dir="chroma_db"):
    """Khởi tạo và cache kết nối tới ChromaDB."""
    global _cached_chroma_client, _cached_collection
    if _cached_collection is not None:
        return _cached_collection
    import chromadb
    os.makedirs(chroma_dir, exist_ok=True)
    _cached_chroma_client = chromadb.PersistentClient(path=chroma_dir)
    _cached_collection = _cached_chroma_client.get_or_create_collection(
        name="ptit_knowledge",
        metadata={"hnsw:space": "cosine"}
    )
    return _cached_collection


# ==============================================================================
# GỌI REST API GEMINI (TRỰC TIẾP, ĐỦ THỜI GIAN PHẢN HỒI)
# ==============================================================================

def call_gemini_rest_api(prompt, model_name, api_key=API_KEY, timeout=25):
    """Gọi trực tiếp Google Gemini REST API với timeout 25 giây."""
    clean_model = model_name.replace("models/", "").strip()
    clean_key = api_key.strip() if api_key else API_KEY
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={clean_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048
        }
    }
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"].strip(), None
            return None, "Empty response from Gemini API"
        else:
            return None, f"HTTP {resp.status_code}: {resp.text[:120]}"
    except requests.exceptions.Timeout:
        return None, f"Timeout after {timeout}s on {clean_model}"
    except Exception as e:
        return None, str(e)


def get_embedding_rest(text, api_key=API_KEY, timeout=3.0):
    """Tạo vector embedding cho câu hỏi qua REST API."""
    clean_key = api_key.strip() if api_key else API_KEY
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={clean_key}"
    payload = {"content": {"parts": [{"text": text}]}}
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if "embedding" in data and "values" in data["embedding"]:
                return data["embedding"]["values"]
    except Exception:
        pass
    return None


# ==============================================================================
# HYBRID RETRIEVAL (TÌM KIẾM TÀI LIỆU CHÍNH XÁC & MỞ RỘNG TRANG CHA)
# ==============================================================================

def get_parent_document_page(source_file, page_num, processed_dir="processed_data"):
    """Lấy toàn bộ nội dung của trang tương ứng từ file Markdown gốc."""
    if not source_file:
        return ""
    fpath = os.path.join(processed_dir, source_file)
    if not os.path.exists(fpath):
        return ""
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return ""

    if page_num:
        pages = re.split(r"^## Trang (\d+) - \[([^\]]+)\]", content, flags=re.MULTILINE)
        if len(pages) > 1:
            for i in range(1, len(pages), 3):
                p_no = int(pages[i])
                p_body = pages[i+2].strip() if i+2 < len(pages) else ""
                if p_no == page_num:
                    return p_body

    return content.strip()


def keyword_search_all(query, processed_dir="processed_data", top_k=3):
    """Tìm kiếm chính xác và theo từ khóa trên toàn bộ các file Markdown."""
    if not os.path.exists(processed_dir):
        return []

    q_lower = query.lower().strip()
    q_words = [w for w in re.findall(r"\w+", q_lower) if len(w) > 1]
    if not q_words:
        return []

    is_form_q = any(k in q_lower for k in ["mẫu đơn", "mau don", "đơn xin", "don xin", "đơn đề nghị", "biểu mẫu", "vắng thi", "nghỉ học", "thôi học", "phúc khảo"])
    is_doi_diem_q = any(k in q_lower for k in ["quy đổi", "quy doi", "đổi điểm", "doi diem", "chuyển điểm", "ielts", "toefl", "toeic", "aptis"])
    is_gv_q = any(k in q_lower for k in ["giảng viên", "giang vien", "thầy", "cô", "pgs", "tiến sĩ"])
    is_hp_q = any(k in q_lower for k in ["học phí", "hoc phi", "mức thu", "tín chỉ"])
    is_hb_q = any(k in q_lower for k in ["học bổng", "hoc bong", "khuyến khích"])
    is_ktx_q = any(k in q_lower for k in ["ký túc xá", "kí túc xá", "ktx", "sơ đồ", "mặt bằng", "khuôn viên", "nhà a1", "nhà a2", "nhà a3", "nhà b2", "b2"])

    cohort_matches = re.findall(r"(?:kh[oó]a\s*|k)(\d{2,4})|\b(202[0-9])\b", q_lower)
    target_cohorts = []
    for cm in cohort_matches:
        c_val = cm[0] or cm[1]
        if c_val:
            target_cohorts.append("20" + c_val if len(c_val) == 2 else c_val)

    results = []
    for fname in os.listdir(processed_dir):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(processed_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        pages = re.split(r"^## Trang (\d+) - \[([^\]]+)\]", content, flags=re.MULTILINE)
        if len(pages) > 1:
            for i in range(1, len(pages), 3):
                p_num = int(pages[i])
                p_type = pages[i+1]
                p_body = pages[i+2].strip() if i+2 < len(pages) else ""
                p_lower = p_body.lower()

                score = 0
                # 1. Khớp cụm từ chính xác
                if q_lower in p_lower:
                    score += 120
                else:
                    for l in range(len(q_words), 1, -1):
                        for start in range(len(q_words) - l + 1):
                            subphrase = " ".join(q_words[start:start+l])
                            if subphrase in p_lower:
                                score += 35 * l

                # 2. Khớp từ khóa đơn
                score += sum(p_lower.count(w) for w in q_words)

                # 3. Ưu tiên theo tài liệu chuyên biệt
                if is_form_q and ("cộng hòa xã hội" in p_lower or "cộng hoà xã hội" in p_lower) and ("kính gửi" in p_lower or "kính đề nghị" in p_lower):
                    score += 200
                elif is_form_q and "so_tay" in fname:
                    score = score * 0.1

                if is_doi_diem_q and "doi_diem" in fname.lower():
                    score += 250
                if is_gv_q and "giang_vien" in fname.lower():
                    score += 200
                if is_hb_q and "hb_" in fname.lower():
                    score += 180

                # Xử lý tìm kiếm học phí chính xác
                if is_hp_q and "hp_" in fname.lower():
                    # Khớp năm học
                    has_2026 = "2026" in q_lower
                    has_2025 = "2025" in q_lower
                    if has_2026 and "2026" in fname:
                        score += 250
                    if has_2025 and "2025" in fname:
                        score += 250
                    if not has_2026 and not has_2025:
                        score += 150

                    # Phân biệt bảng giá thực tế với văn bản mở đầu pháp lý hành chính (preamble)
                    is_preamble = (p_num in [1, 2]) or any(k in p_lower for k in ["căn cứ quyết định", "căn cứ nghị định", "điều 1. ban hành", "nơi nhận:"])
                    is_table_page = (p_type == "SCAN_TABLE") or ("|" in p_body and any(k in p_lower for k in ["mức thu", "đồng/tín chỉ", "đvt"]))

                    if is_table_page:
                        score += 250
                        # Khớp khóa học (ví dụ: Khóa 2023)
                        for tc in target_cohorts:
                            if f"khóa {tc}" in p_lower or f"khoá {tc}" in p_lower or tc in p_lower:
                                score += 200
                        # Khớp ngành đào tạo (ví dụ: Công nghệ thông tin / CNTT)
                        if any(m in q_lower for m in ["cntt", "công nghệ thông tin", "an toàn thông tin", "máy tính"]):
                            if "công nghệ thông tin" in p_lower:
                                score += 150
                    elif is_preamble:
                        score = score * 0.05

                if is_ktx_q and "so_tay" in fname.lower() and p_num == 9:
                    score += 250

                if score > 0:
                    results.append({
                        "content": p_body,
                        "source": fname,
                        "page": p_num,
                        "type": p_type,
                        "score": score
                    })

    results.sort(key=lambda x: x["score"], reverse=True)

    # Nếu là câu hỏi so sánh giữa 2 năm (2025 và 2026), đảm bảo lấy cân bằng tài liệu của cả 2 năm
    if is_hp_q and "2025" in q_lower and "2026" in q_lower:
        res_2025 = [r for r in results if "2025" in r["source"]]
        res_2026 = [r for r in results if "2026" in r["source"]]
        balanced = []
        for i in range(max(len(res_2025), len(res_2026))):
            if i < len(res_2025):
                balanced.append(res_2025[i])
            if i < len(res_2026):
                balanced.append(res_2026[i])
            if len(balanced) >= max(top_k, 4):
                break
        if balanced:
            return balanced

    return results[:top_k]


def smart_query_knowledge_base(query, n_results=4, custom_api_key=None):
    """Truy vấn kết hợp Hybrid Search (Keyword + Vector) và mở rộng trang cha."""
    active_key = custom_api_key.strip() if (custom_api_key and custom_api_key.strip()) else API_KEY
    matched_chunks = []

    try:
        q_vec = get_embedding_rest(query, active_key, timeout=3.0)
        if q_vec:
            collection = get_vector_db()
            res = collection.query(query_embeddings=[q_vec], n_results=n_results)
            if res and res.get("documents") and len(res["documents"]) > 0:
                for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
                    matched_chunks.append({
                        "content": doc,
                        "source": meta.get("source"),
                        "page": meta.get("page"),
                        "type": meta.get("type")
                    })
    except Exception:
        pass

    keyword_hits = keyword_search_all(query, top_k=n_results)
    combined = keyword_hits + matched_chunks

    expanded = []
    seen = set()
    for c in combined:
        src = c.get("source")
        p = c.get("page")
        key = (src, p)
        if key in seen:
            continue
        seen.add(key)
        parent = get_parent_document_page(src, p)
        expanded.append({
            "source": src,
            "page": p,
            "type": c.get("type", "page"),
            "content": parent if parent else c.get("content", "")
        })

    return expanded[:max(n_results, 4)]


# ==============================================================================
# SINH CÂU TRẢ LỜI QUA LLM (GEMINI PROMPT CHUẨN XÁC, KHÔNG BỊA ĐẶT)
# ==============================================================================

def generate_llm_answer(question, context_str, custom_api_key=None, preferred_model=None, history=None):
    """Sinh câu trả lời thông minh qua Gemini LLM."""
    active_key = custom_api_key.strip() if (custom_api_key and custom_api_key.strip()) else API_KEY

    history_prompt = ""
    if history and isinstance(history, list) and len(history) > 0:
        h_lines = []
        for h in history[-4:]:
            role = "Người dùng" if h.get("role") == "user" else "Trợ lý PTIT"
            cnt = h.get("content", "").strip()
            if cnt:
                h_lines.append(f"{role}: {cnt}")
        if h_lines:
            history_prompt = "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\n" + "\n".join(h_lines) + "\n\n"

    system_instruction = f"""
Bạn là Trợ lý Ảo AI chính thức của Học viện Công nghệ Bưu chính Viễn thông (PTIT).
Dưới đây là thông tin trích xuất từ các tài liệu chính thức của Học viện:

{context_str}

{history_prompt}CÂU HỎI CỦA NGƯỜI DÙNG: {question}

NGUYÊN TẮC BẮT BUỘC:
1. TRUNG THỰC & CHUẨN XÁC (QUAN TRỌNG NHẤT):
   - Trả lời đúng trọng tâm câu hỏi dựa vào tài liệu được cung cấp bên trên.
   - Khi hỏi về HỌC PHÍ của một khóa / ngành / năm học: Nêu rõ mức học phí (đồng/tín chỉ) của từng hệ đào tạo (Chương trình chuẩn/đại trà, Chất lượng cao, Cử nhân định hướng ứng dụng...) có trong tài liệu dưới dạng danh sách gạch đầu dòng chi tiết (- **Hệ đào tạo:** Mức phí đồng/tín chỉ). TUYỆT ĐỐI KHÔNG chép lại phần văn bản hành chính mở đầu (Căn cứ quyết định, Căn cứ nghị định...).
   - Khi câu hỏi yêu cầu SO SÁNH (ví dụ so sánh học phí giữa các năm 2025 và 2026, hoặc so sánh giữa các khóa/hệ): Trình bày bảng so sánh Markdown trực quan, chi tiết từng hệ đào tạo/ngành qua các năm và phân tích mức chênh lệch cụ thể (tăng/giảm bao nhiêu).
   - Nếu tài liệu có thông tin: Trả lời ngắn gọn, đầy đủ, mạch lạc.
   - Nếu tài liệu chỉ có thông tin MỘT PHẦN (ví dụ: có vị trí tòa nhà KTX B2 trên sơ đồ nhưng không có bảng giá phòng hay điều kiện nội trú): Hãy nêu rõ những thông tin có trong tài liệu, và thông báo rõ phần thông tin chưa có trong tài liệu kèm hướng dẫn liên hệ phòng ban phụ trách (Phòng Chính trị & Công tác sinh viên tại Nhà A1, Ban quản lý KTX...).
   - Nếu tài liệu hoàn toàn KHÔNG có thông tin để trả lời: Hãy thông báo lịch sự rằng tài liệu hiện có của Học viện chưa có thông tin về vấn đề này. TUYỆT ĐỐI KHÔNG tự bịa đặt hay đưa nội dung của văn bản khác không liên quan.

2. ĐỊNH DẠNG TRÌNH BÀY:
   - THÔNG TIN ĐƠN LẺ (hỏi về 1 giảng viên cụ thể, 1 môn học cụ thể, 1 tòa nhà/địa điểm, 1 mức phí đơn lẻ...): Trình bày dưới dạng danh sách gạch đầu dòng chi tiết (- **Thuộc tính:** Giá trị). TUYỆT ĐỐI KHÔNG DÙNG BẢNG 1 DÒNG.
   - BẢNG BIỂU DỮ LIỆU HOẶC SO SÁNH (bảng quy đổi điểm tiếng Anh, so sánh học phí qua các năm, danh sách môn học, học bổng...): Trình bày dưới dạng bảng Markdown hoàn chỉnh, chuẩn xác, đẹp mắt.
   - BIỂU MẪU ĐƠN TỪ: Cung cấp đầy đủ nguyên văn biểu mẫu (Quốc hiệu tiêu ngữ, Kính gửi, nội dung sinh viên khai, lý do, cam đoan, phần chữ ký...).

3. VĂN PHONG:
   - Thân thiện, tôn trọng, khách quan.
   - TUYỆT ĐỐI KHÔNG dùng ký hiệu LaTeX toán học như $\\ge$, $\\le$ hay dấu $, hãy dùng tiếng Việt tự nhiên (>=, <=, "từ... trở lên").
   - TUYỆT ĐỐI KHÔNG để lộ tên file nội bộ (.md, .pdf), số trang tài liệu hay ghi chú debug trong câu trả lời.
"""

    valid_models = [
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3-flash-preview",
        "gemini-3.6-flash",
        "gemini-flash-latest",
        "gemini-3.5-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-2.5-flash",
    ]
    models_to_try = []
    if preferred_model and preferred_model.strip():
        clean_pref = preferred_model.replace("models/", "").strip()
        if clean_pref in valid_models:
            models_to_try.append(clean_pref)

    for m in FALLBACK_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    last_error = ""
    start_time = time.time()
    for model_name in models_to_try:
        if time.time() - start_time > 32.0:
            break
        ans, err = call_gemini_rest_api(
            prompt=system_instruction,
            model_name=model_name,
            api_key=active_key,
            timeout=22.0
        )
        if ans:
            return ans, model_name, None
        try:
            print(f"[!] Model {model_name} khong phan hoi: {err}")
        except Exception:
            pass
        last_error = err

    return None, None, last_error


# ==============================================================================
# HẬU XỬ LÝ & BỘ LỌC AN TOÀN KHI MẤT KẾT NỐI (SAFE FALLBACK)
# ==============================================================================

def clean_llm_response(text):
    """Làm sạch văn bản trả lời, chuyển bảng 1 dòng sang gạch đầu dòng, sửa LaTeX."""
    if not text:
        return ""
    text = re.sub(r"\n*📌\s*\*\*Nguồn[^\n]*\n*", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\n*\*\*Nguồn tài liệu[^\n]*\n*", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\[[^\]]+\.md\s*\|\s*Trang\s*\d+[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[[^\]]+\.pdf\s*\|\s*Trang\s*\d+[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"##\s*Trang\s*\d+.*?\n", "", text, flags=re.IGNORECASE)

    # Chuyển bảng 1 dòng thành gạch đầu dòng
    if "|" in text:
        lines = text.split("\n")
        out_lines = []
        in_tbl = False
        tbl = []

        def fix_tbl(t):
            data_rows = [l for l in t[2:] if any(c.strip() and c.strip() not in ["-", ":---:", ":---", "---:"] for c in l.strip("|").split("|"))]
            if len(data_rows) == 1:
                hdrs = [c.strip() for c in t[0].strip("|").split("|")]
                cells = [c.strip() for c in data_rows[0].strip("|").split("|")]
                b_lines = []
                for h, c in zip(hdrs, cells):
                    h_clean = re.sub(r"\(.*?\)", "", h).replace("*", "").strip()
                    c_clean = c.replace("*", "").strip()
                    if h_clean.upper() in ["STT", "TT"] or not c_clean or c_clean in ["-", ":---:", ":---", "---:"]:
                        continue
                    b_lines.append(f"- **{h_clean}:** {c_clean}")
                if b_lines:
                    return b_lines
            return t

        for line in lines:
            if line.strip().startswith("|") and line.strip().endswith("|"):
                if not in_tbl:
                    in_tbl = True
                    tbl = [line]
                else:
                    tbl.append(line)
            else:
                if in_tbl:
                    out_lines.extend(fix_tbl(tbl))
                    in_tbl = False
                    tbl = []
                out_lines.append(line)
        if in_tbl:
            out_lines.extend(fix_tbl(tbl))
        text = "\n".join(out_lines)

    # Xử lý ký hiệu toán học
    text = re.sub(r"\$\s*\\ge(q)?\s*([^$]+)\$", r"từ \2 trở lên", text)
    text = re.sub(r"\$\s*\\le(q)?\s*([^$]+)\$", r"dưới hoặc bằng \2", text)
    text = re.sub(r"\\ge(q)?\b", ">=", text)
    text = re.sub(r"\\le(q)?\b", "<=", text)
    text = text.replace("$", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def safe_fallback_answer(question, docs):
    """
    Bộ dự phòng an toàn khi mất kết nối AI hoàn toàn:
    Trích xuất nội dung từ tài liệu có độ khớp cao nhất, loại bỏ văn bản mở đầu hành chính rác.
    """
    if not docs:
        return "Hiện chưa tìm thấy thông tin phù hợp trong tài liệu của Học viện. Bạn vui lòng liên hệ phòng Công tác sinh viên hoặc phòng ban liên quan để được hỗ trợ trực tiếp."

    q_lower = question.lower()
    q_words = [w for w in re.findall(r"\w+", q_lower) if len(w) > 1]

    # 1. Nếu là mẫu đơn hành chính chuẩn (đơn xin vắng thi, nghỉ học...)
    for d in docs:
        c = d.get("content", "")
        c_up = c.upper()
        if ("CỘNG HÒA XÃ HỘI" in c_up or "CỘNG HOÀ XÃ HỘI" in c_up) and ("KÍNH GỬI" in c_up or "KÍNH ĐỀ NGHỊ" in c_up):
            clean_form = re.sub(r"^\s*-\s*\d+\s*-\s*", "", c).strip()
            return f"Dưới đây là mẫu đơn theo quy định của Học viện:\n\n{clean_form}"

    # 2. Tìm trang tài liệu chứa thông tin thực tế (ưu tiên trang có bảng dữ liệu hoặc nội dung chi tiết)
    best_doc = None
    best_matches = 0

    for d in docs:
        c = d.get("content", "").strip()
        if not c:
            continue
        # Bỏ qua các trang mở đầu văn bản pháp lý hành chính thuần túy không chứa dữ liệu cụ thể
        if any(k in c.lower() for k in ["căn cứ nghị định", "căn cứ quyết định", "bộ khoa học và công nghệ"]) and "|" not in c:
            continue

        c_lower = c.lower()
        matches = sum(1 for w in q_words if w in c_lower)
        if "|" in c:
            matches += 2

        if matches > best_matches:
            best_matches = matches
            best_doc = c

    if best_doc and best_matches >= 2:
        clean_text = re.sub(r"^##\s*Trang\s*\d+.*?\n", "", best_doc, flags=re.MULTILINE)
        clean_text = re.sub(r"^#\s*Tài liệu:.*?\n", "", clean_text, flags=re.MULTILINE).strip()
        return f"Thông tin tìm thấy trong tài liệu chính thức của Học viện:\n\n{clean_text}"

    return "Hiện chưa tìm thấy thông tin cụ thể về câu hỏi này trong tài liệu của Học viện. Bạn vui lòng liên hệ phòng Công tác sinh viên hoặc phòng ban liên quan để được hỗ trợ trực tiếp."


# ==============================================================================
# CÁC API ENDPOINTS & GIAO DIỆN WEB
# ==============================================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status", methods=["GET"])
def get_status():
    try:
        coll = get_vector_db()
        count = coll.count()
        return jsonify({
            "status": "ready",
            "chunks_count": count,
            "models_available": FALLBACK_MODELS
        })
    except Exception as e:
        return jsonify({"status": "warning", "chunks_count": 0, "message": str(e)})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    question = (data.get("question") or data.get("message") or "").strip()
    history = data.get("history", [])
    custom_api_key = (data.get("api_key") or data.get("custom_api_key") or "").strip()
    preferred_model = (data.get("model") or data.get("preferred_model") or "").strip()
    top_k = int(data.get("top_k") or 3)

    if not question:
        return jsonify({"error": "Vui lòng nhập câu hỏi."}), 400

    docs = smart_query_knowledge_base(question, n_results=top_k, custom_api_key=custom_api_key)

    context_parts = []
    for i, d in enumerate(docs, start=1):
        context_parts.append(f"--- [TÀI LIỆU {i}] ---\n{d['content']}")
    context_str = "\n\n".join(context_parts) if context_parts else "Không tìm thấy dữ liệu trực tiếp."

    answer, model_used, error_msg = generate_llm_answer(
        question=question,
        context_str=context_str,
        custom_api_key=custom_api_key,
        preferred_model=preferred_model,
        history=history
    )

    if not answer:
        print(f"[!] LLM không phản hồi ({error_msg}), chuyển sang chế độ dự phòng an toàn...")
        answer = safe_fallback_answer(question, docs)
        model_used = "PTIT Safe Engine (Dự phòng)"

    clean_answer = clean_llm_response(answer)
    return jsonify({
        "answer": clean_answer,
        "model_used": model_used,
        "sources": []
    })


@app.route("/api/reset", methods=["POST"])
def reset():
    return jsonify({"status": "success", "message": "Đã làm mới phiên hội thoại."})


def free_port(port):
    """Giải phóng cổng nếu có tiến trình cũ chiếm giữ."""
    try:
        res = subprocess.run(f"netstat -ano | findstr :{port}", shell=True, capture_output=True, text=True)
        for line in res.stdout.splitlines():
            if "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                if pid and pid.isdigit() and int(pid) != os.getpid():
                    print(f"[*] Đang giải phóng cổng {port} từ tiến trình PID {pid}...")
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                    time.sleep(1)
    except Exception:
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    free_port(port)
    print(f"\n{'='*60}")
    print(f"🎓 CHATBOT PTIT ĐANG CHẠY TẠI:")
    print(f"👉 http://127.0.0.1:{port}")
    print(f"{'='*60}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
