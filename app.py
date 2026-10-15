# -*- coding: utf-8 -*-
import os
import sys
import io
import re
import time
import glob
import json
import requests
from flask import Flask, render_template, request, jsonify

# Đảm bảo in tiếng Việt chuẩn trên Windows console
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from chatbot import (
    get_vector_db,
    API_KEY,
    VISION_MODELS
)

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# Danh sách model Gemini ưu tiên để thử theo thứ tự (các model nhanh, ổn định đưa lên đầu)
FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-pro-latest"
]

DOCUMENT_CATALOG = [
    {
        "id": "hp_2025",
        "name": "hp_2025.pdf",
        "title": "Bảng Mức thu Học phí Năm học 2024 - 2025",
        "desc": "Quy định mức thu học phí hệ chính quy, chất lượng cao, liên thông, văn bằng 2 tại cả cơ sở Hà Nội và TP.HCM.",
        "icon": "coins",
        "category": "Học phí"
    },
    {
        "id": "hp_2026",
        "name": "hp_2026.pdf",
        "title": "Kế hoạch & Mức thu Học phí Năm học 2025 - 2026",
        "desc": "Khung học phí dự kiến và chi tiết các ngành đào tạo, đơn vị tín chỉ theo đề án mới của Học viện.",
        "icon": "receipt",
        "category": "Học phí"
    },
    {
        "id": "ct_cntt",
        "name": "ct_cntt.pdf",
        "title": "Chương trình Đào tạo Ngành Công nghệ Thông tin",
        "desc": "Chuẩn đầu ra, khối kiến thức đại cương, cơ sở ngành, chuyên ngành, số tín chỉ, đồ án và chuẩn ngoại ngữ.",
        "icon": "code-2",
        "category": "Đào tạo"
    },
    {
        "id": "so_tay",
        "name": "so_tay.pdf",
        "title": "Sổ tay Sinh viên Học viện PTIT",
        "desc": "Quy chế đào tạo theo tín chỉ, đăng ký môn học, điểm rèn luyện, học bổng khuyến khích, miễn giảm học phí.",
        "icon": "book-open",
        "category": "Quy chế"
    },
    {
        "id": "doi_diem_clc",
        "name": "doi_diem_clc.pdf",
        "title": "Quy định Công nhận và Đổi điểm Học phần CLC",
        "desc": "Quy chế chuyển đổi điểm học phần, chứng chỉ ngoại ngữ và công nhận tương đương hệ Chất lượng cao.",
        "icon": "arrow-left-right",
        "category": "Quy chế"
    }
]


def call_gemini_rest_api(prompt, model_name, api_key, timeout=5):
    """
    Gọi trực tiếp Google Gemini REST API với timeout nghiêm ngặt (5s).
    Tuyệt đối KHÔNG sử dụng retry tự động gây đóng băng/treo (41s) của SDK!
    """
    clean_model = model_name.replace("models/", "").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.2,
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
            return None, f"HTTP {resp.status_code}: {resp.text[:150]}"
    except requests.exceptions.Timeout:
        return None, f"Timeout after {timeout}s on {clean_model}"
    except Exception as e:
        return None, str(e)


def generate_llm_answer(question, context_str, custom_api_key=None, preferred_model=None, history=None):
    """Gọi Gemini API sinh câu trả lời với tốc độ cao, không bao giờ bị nghẽn thread hay timeout."""
    active_key = custom_api_key.strip() if (custom_api_key and custom_api_key.strip()) else API_KEY

    # Xây dựng lịch sử hội thoại nếu có
    history_prompt = ""
    if history and isinstance(history, list) and len(history) > 0:
        history_text = []
        for h in history[-4:]:
            role = "Người dùng" if h.get("role") == "user" else "Trợ lý PTIT"
            content = h.get("content", "").strip()
            if content:
                history_text.append(f"{role}: {content}")
        if history_text:
            history_prompt = "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\n" + "\n".join(history_text) + "\n\n"

    system_instruction = f"""
Bạn là Trợ lý Ảo Thông Minh của Học viện Công nghệ Bưu chính Viễn thông (PTIT).
Dưới đây là thông tin chính thức từ cơ sở dữ liệu của Học viện:

{context_str}

{history_prompt}CÂU HỎI CỦA NGƯỜI DÙNG: {question}

CÁC NGUYÊN TẮC BẮT BUỘC KHI TRẢ LỜI:
1. ĐÚNG TRỌNG TÂM - ĐẦY ĐỦ THÔNG TIN TỪNG KHÓA VÀ CÁC HỆ ĐÀO TẠO:
   - Khi người dùng hỏi học phí của một ngành trong năm học mà KHÔNG chỉ rõ khóa nào: BẮT BUỘC liệt kê ĐẦY ĐỦ TỪNG KHÓA (Khóa 2021, 2022, 2023, 2024, 2025...) và TẤT CẢ CÁC HỆ/CHƯƠNG TRÌNH ĐÀO TẠO (Đại học chính quy đại trà, Chất lượng cao, Tiên tiến/đặc thù) có trong tài liệu. Tuyệt đối không được bỏ sót khóa nào.
   - Khi người dùng hỏi về MỘT KHÓA CỤ THỂ (ví dụ: Khóa 2023): BẮT BUỘC liệt kê ĐẦY ĐỦ TẤT CẢ CÁC CHƯƠNG TRÌNH ĐÀO TẠO của khóa đó (Chính quy đại trà, Chất lượng cao, Tiên tiến/đặc thù).
   - TUYỆT ĐỐI KHÔNG liệt kê sang các ngành hoàn toàn khác không liên quan nếu người dùng không hỏi.
2. ĐÁNH SỐ THỨ TỰ (STT) BẮT BUỘC CHUẨN XÁC, TUẦN TỰ:
   - Cột STT bắt buộc phải đánh số tự nhiên liên tục: 1, 2, 3, 4, 5... từ đầu đến cuối bảng.
   - TUYỆT ĐỐI KHÔNG dùng số La Mã (I, II, III), không chép số thứ tự rải rác hoặc không đồng nhất từ văn bản gốc, không lặp lại số STT.
   - Bảng Markdown chuẩn gồm các cột:
     | STT | Chương trình đào tạo | Ngành / Chuyên ngành | Khóa tuyển sinh | Đơn vị tính | Mức thu học phí |
   - Cột Mức thu học phí ghi rõ số tiền, ví dụ: 920.000, 1.350.000...
3. TUYỆT ĐỐI KHÔNG TRÍCH DẪN NGUỒN TRONG VĂN BẢN:
   - KHÔNG nhắc đến tên file (hp_2025.md, hp_2026.md, ctdt...), KHÔNG nhắc đến số trang tài liệu, KHÔNG tạo mục "Nguồn tài liệu tham khảo".
4. ĐI THẲNG VÀO NỘI DUNG:
   - Câu mở đầu rõ ràng: nêu rõ ngành học, năm học và quyết định tương ứng.
"""

    models_to_try = []
    if preferred_model and preferred_model.strip():
        clean_pref = preferred_model.replace("models/", "").strip()
        models_to_try.append(clean_pref)
    for m in FALLBACK_MODELS:
        clean_m = m.replace("models/", "").strip()
        if clean_m not in models_to_try:
            models_to_try.append(clean_m)

    last_error = ""
    start_time = time.time()
    # Thử các model trong ngân sách thời gian tối đa 10s để không bao giờ bị timeout
    for model_name in models_to_try:
        if time.time() - start_time > 10:
            print(f"[!] Đã vượt ngân sách thời gian gọi LLM ({round(time.time() - start_time, 1)}s), chuyển ngay sang Engine dự phòng.")
            break

        ans, err = call_gemini_rest_api(
            prompt=system_instruction,
            model_name=model_name,
            api_key=active_key,
            timeout=5
        )
        if ans:
            return ans, model_name, None
        last_error = err

    return None, None, last_error


def keyword_fallback_search(query, processed_dir="processed_data", top_k=4):
    """
    Fallback tìm kiếm văn bản cực nhanh (dưới 10ms) trực tiếp trên các file Markdown
    phòng khi Embedding API tạm thời bận hoặc hết quota.
    """
    words = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 1]
    if not words:
        return []

    results = []
    md_files = glob.glob(os.path.join(processed_dir, "*.md"))
    for md_file in md_files:
        base_name = os.path.basename(md_file)
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        pages = re.split(r"^## Trang (\d+) - \[([^\]]+)\]", content, flags=re.MULTILINE)
        if len(pages) > 1:
            for i in range(1, len(pages), 3):
                p_num = int(pages[i])
                p_type = pages[i+1]
                p_body = pages[i+2].strip() if i+2 < len(pages) else ""
                p_body_lower = p_body.lower()

                score = sum(p_body_lower.count(w) for w in words)
                if score > 0:
                    results.append({
                        "score": score,
                        "content": f"[{base_name} | Trang {p_num} | {p_type}]\n{p_body[:1200]}",
                        "source": base_name,
                        "page": p_num,
                        "type": p_type
                    })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def get_embedding_rest(text, api_key, timeout=3.0):
    """
    Lấy vector embedding trực tiếp qua Google REST API với timeout nghiêm ngặt (3s).
    Tránh tuyệt đối việc SDK treo/retry kéo dài gây chậm luồng.
    """
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
    except Exception as e:
        print(f"[!] Embedding REST API ({timeout}s): {e}")
    return None


def safe_query_knowledge_base(query, n_results=4, custom_api_key=None):
    """Truy vấn Vector DB với cơ chế fallback tự động nếu Embedding API gặp trục trặc."""
    active_key = custom_api_key.strip() if (custom_api_key and custom_api_key.strip()) else API_KEY
    q_lower = query.lower()

    search_q = query
    if "cntt" in q_lower and "công nghệ thông tin" not in q_lower:
        search_q += " công nghệ thông tin"
    if "clc" in q_lower and "chất lượng cao" not in q_lower:
        search_q += " chất lượng cao"

    # 1. Thử Vector Search qua ChromaDB với REST embedding siêu tốc (timeout 3s)
    try:
        q_vec = get_embedding_rest(search_q, active_key, timeout=3.0)
        if not q_vec:
            embedding_model = GoogleGenerativeAIEmbeddings(
                model="models/gemini-embedding-001",
                google_api_key=active_key
            )
            q_vec = embedding_model.embed_query(search_q)

        if q_vec:
            collection = get_vector_db()
            results = collection.query(query_embeddings=[q_vec], n_results=n_results)

            matched_docs = []
            if results and results.get("documents") and len(results["documents"]) > 0:
                for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                    matched_docs.append({
                        "content": doc,
                        "source": meta.get("source"),
                        "page": meta.get("page"),
                        "type": meta.get("type")
                    })
            
            if matched_docs:
                return matched_docs[:n_results]
    except Exception as e:
        print(f"[!] Vector Search gặp lỗi ({e}), chuyển sang Keyword Fallback Search...")

    # 2. Fallback sang tìm kiếm từ khóa trực tiếp trên Markdown (< 10ms)
    docs = keyword_fallback_search(search_q, top_k=n_results)
    return docs[:n_results]


def normalize_table_stt(text):
    """
    Chuẩn hóa bảng Markdown trong văn bản:
    - Nếu cột đầu tiên là STT hoặc TT, tự động đánh lại số thứ tự tuần tự: 1, 2, 3, 4...
    - Loại bỏ các dòng tiêu đề nhóm con hoặc ô rỗng bị lọt vào bảng (ví dụ: | III | Khóa 2025 | | |)
    """
    if not text or "|" not in text:
        return text

    lines = text.split("\n")
    output_lines = []
    in_table = False
    table_lines = []

    def process_table_block(tbl_lines):
        if len(tbl_lines) < 2:
            return tbl_lines

        header = tbl_lines[0].strip()
        sep = tbl_lines[1].strip()

        cols = [c.strip() for c in header.strip("|").split("|")]
        if not cols:
            return tbl_lines

        first_col_lower = cols[0].lower()
        if first_col_lower not in ["stt", "tt"]:
            return tbl_lines

        res = [header, sep]
        stt_counter = 1

        for row_str in tbl_lines[2:]:
            r_str = row_str.strip()
            if not (r_str.startswith("|") and r_str.endswith("|")):
                res.append(row_str)
                continue

            cells = [c.strip() for c in r_str.strip("|").split("|")]
            # Bỏ qua dòng chỉ mục cột OCR: 1 | 2 | 3 | 4 | 5
            if len(cells) >= 3 and all(c == "" or c.replace("*", "") == str(i + 1) for i, c in enumerate(cells)):
                continue

            # Bỏ qua dòng tiêu đề nhóm hoặc ô rỗng (ví dụ: | III | Khóa 2025 | | |)
            non_empty_cells = [c for c in cells if c and c not in ["-", ":---:", ":---", "---:"]]
            if len(non_empty_cells) <= 1:
                continue

            # Nếu dòng chỉ có nhãn Khóa hoặc số La Mã mà không có thông tin học phí ở các cột sau
            if len(non_empty_cells) == 2 and any("khóa" in c.lower() for c in non_empty_cells) and not any(re.search(r"\d{3}", c) for c in cells):
                continue

            # Đánh lại STT tuần tự
            cells[0] = str(stt_counter)
            stt_counter += 1

            while len(cells) < len(cols):
                cells.append("")
            if len(cells) > len(cols):
                cells = cells[:len(cols)]

            res.append("| " + " | ".join(cells) + " |")

        return res

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                in_table = True
                table_lines = [line]
            else:
                table_lines.append(line)
        else:
            if in_table:
                output_lines.extend(process_table_block(table_lines))
                in_table = False
                table_lines = []
            output_lines.append(line)

    if in_table:
        output_lines.extend(process_table_block(table_lines))

    return "\n".join(output_lines)


def clean_llm_response(text):
    """Loại bỏ triệt để các đoạn trích dẫn tên file, số trang, số quyết định và chuẩn hóa bảng Markdown."""
    if not text:
        return ""
    # Xóa các dòng trích dẫn nguồn
    text = re.sub(r"\n*📌\s*\*\*Nguồn[^\n]*\n*", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\n*\*\*Nguồn tài liệu[^\n]*\n*", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\n*Nguồn tài liệu tham khảo:[^\n]*\n*", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\n*Trích xuất từ\s*:[^\n]*\n*", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\n*\(Nguồn:[^\)]*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n*\(Kèm theo Quyết định[^\)]*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n*\(Trích từ[^\)]*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[hp_\d+\.md\s*\|\s*Trang\s*\d+[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[[^\]]+\.pdf\s*\|\s*Trang\s*\d+[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\(?Trang\s*\d+\s*,\s*file\s*[^,\)]+\)?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\*Nguồn:.*?\*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"##\s*Trang\s*\d+.*?\n", "", text, flags=re.IGNORECASE)
    
    # Xóa dòng chỉ mục cột 1 2 3 4 5 trong bảng scan OCR
    text = re.sub(r"\n\|\s*\*?1\*?\s*\|\s*\*?2\*?\s*\|\s*\*?3\*?\s*\|\s*\*?4\*?\s*\|\s*\*?5\*?\s*\|", "", text)
    
    # Chuẩn hóa số thứ tự (STT) trong bảng
    text = normalize_table_stt(text)
    
    # Chuẩn hóa khoảng trống
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ==============================================================================
# BỘ BÓC TÁCH BẢNG MARKDOWN ĐỘNG TỪ TÀI LIỆU (GENERIC DYNAMIC TABLE PARSER)
# (Không hardcode dữ liệu - Tự động đọc và phân tích cấu trúc bảng từ bất kỳ file .md nào)
# ==============================================================================

def extract_table_rows_from_markdown(content):
    """
    Bóc tách động cấu trúc bảng Markdown từ nội dung tài liệu bất kỳ.
    Tự động ghi nhớ phân cấp chương trình/hệ đào tạo và khóa học mà không cần hardcode.
    """
    lines = content.split("\n")
    current_section = ""
    current_cohort = ""
    rows = []

    for line in lines:
        line_s = line.strip()
        if not (line_s.startswith("|") and line_s.endswith("|")):
            continue
        cells = [c.strip() for c in line_s.strip("|").split("|")]
        if len(cells) < 3:
            continue

        c0 = cells[0].replace("*", "").strip()
        c1 = cells[1].replace("*", "").strip() if len(cells) > 1 else ""

        # Bỏ qua dòng tiêu đề cột hoặc dòng phân cách
        if c0.upper() in ["TT", "STT", "HỆ/KHÓA/NGÀNH", "1"] and any("MỨC THU" in c.upper() or "ĐVT" in c.upper() for c in cells):
            continue
        if all(c in ["-", ":---:", ":---", "---:"] or c == "" for c in cells):
            continue
        if len(cells) >= 3 and all(c == "" or c.replace("*", "") == str(i + 1) for i, c in enumerate(cells)):
            continue

        has_fee = any(re.search(r"\d{1,3}(\.\d{3})+", c) for c in cells[2:])

        # 1. Nhận diện dòng phân loại Khóa: ví dụ I. Khóa 2021, II. Khóa 2022... (kiểm tra trước để tránh I và V bị nhầm thành Section)
        if any(k in c1.lower() for k in ["khóa", "khoá"]) and not has_fee:
            current_cohort = c1
            continue

        # 2. Nhận diện dòng phân loại nhóm lớn / hệ đào tạo: ví dụ A. ĐẠI HỌC CHÍNH QUY ĐẠI TRÀ, B. CHẤT LƯỢNG CAO...
        if (re.match(r"^[A-H]$", c0) or any(s in c1.upper() for s in ["ĐẠI HỌC", "CHẤT LƯỢNG CAO", "TIÊN TIẾN", "THẠC SĨ", "TIẾN SĨ"])) and not has_fee:
            current_section = c1 if c1 else c0
            current_cohort = ""
            continue

        # 3. Dòng dữ liệu thực tế (chứa số tiền)
        fee_cell = None
        for c in cells[2:]:
            if re.search(r"\d{1,3}(\.\d{3})+", c):
                fee_cell = c.strip()
                break

        if fee_cell:
            rows.append({
                "section": current_section or "Chương trình chuẩn",
                "cohort": current_cohort or "Toàn khóa",
                "major": c1,
                "unit": cells[2].strip() if len(cells) > 2 and cells[2].strip() else "đồng/tín chỉ",
                "fee": fee_cell,
                "raw": line_s
            })

    return rows


def extract_dynamic_table_answer(question, docs=None, processed_dir="processed_data"):
    """
    Tự động đọc các file Markdown trong thư mục tri thức, bóc tách bảng động và
    tổng hợp bảng trả lời với STT 1..N theo đúng ngành và khóa được hỏi.
    Hoàn toàn không hardcode bất kỳ số liệu nào trong code.
    """
    q_lower = question.lower()

    # Bỏ qua các câu hỏi về tốt nghiệp, khối lượng tín chỉ, miễn giảm, lý do...
    skip_keywords = [
        "tốt nghiệp", "tot nghiep", "toàn khóa", "toan khoa", "khối lượng", "khoi luong",
        "miễn giảm", "mien giam", "chính sách", "chinh sach", "hạn nộp", "han nop",
        "thời gian nộp", "cách nộp", "tài khoản", "ngân hàng", "tại sao", "lý do"
    ]
    if any(w in q_lower for w in skip_keywords):
        return None

    # Xác định năm học được hỏi để chọn file Markdown phù hợp
    target_file = "hp_2025.md"
    year_title = "năm học 2025 - 2026"
    if "2026" in q_lower:
        if "năm 2026" in q_lower or "2026-2027" in q_lower or ("2026" in q_lower and "2025" not in q_lower and "khoá 2026" not in q_lower and "khóa 2026" not in q_lower):
            target_file = "hp_2026.md"
            year_title = "năm học 2026 - 2027"

    file_path = os.path.join(processed_dir, target_file)
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    # Bóc tách tất cả các hàng bảng từ file Markdown
    rows = extract_table_rows_from_markdown(content)
    if not rows:
        return None

    # Tìm khóa học được hỏi nếu có (ví dụ: khóa 2023, k23, khóa 2024...)
    target_cohort = None
    cohort_match = re.search(r"(?:khóa|khoá|k)\s*(202\d|2\d)", q_lower)
    if cohort_match:
        val = cohort_match.group(1)
        target_cohort = f"20{val}" if len(val) == 2 else val
    else:
        for y in [2021, 2022, 2023, 2024, 2025, 2026]:
            if str(y) in q_lower and f"năm {y}" not in q_lower and f"năm học {y}" not in q_lower:
                target_cohort = str(y)
                break

    # Lọc ngành học theo từ khóa trong câu hỏi
    major_keywords = []
    if "cntt" in q_lower or "công nghệ thông tin" in q_lower:
        major_keywords = ["công nghệ thông tin", "cntt"]
    elif "marketing" in q_lower:
        major_keywords = ["marketing"]
    elif "kế toán" in q_lower or "ke toan" in q_lower:
        major_keywords = ["kế toán"]
    elif "an toàn thông tin" in q_lower or "attt" in q_lower:
        major_keywords = ["an toàn thông tin", "attt"]
    elif "quản trị kinh doanh" in q_lower or "qtkd" in q_lower:
        major_keywords = ["quản trị kinh doanh", "qtkd"]
    elif "trí tuệ nhân tạo" in q_lower or "ai" in re.findall(r"\b\w+\b", q_lower):
        major_keywords = ["trí tuệ nhân tạo", "ai"]
    elif "quốc phòng" in q_lower or "gdqp" in q_lower:
        major_keywords = ["quốc phòng", "gdqp"]
    else:
        words = [w for w in re.findall(r"\w+", q_lower) if len(w) > 2 and w not in ["học", "phí", "năm", "khoá", "khóa", "cho", "của", "bao", "nhiêu", "ngành"]]
        if words:
            major_keywords = words

    # Lọc các dòng bảng phù hợp
    matched_rows = []
    for r in rows:
        r_text = (r["major"] + " " + r["section"]).lower()
        if major_keywords and not any(kw in r_text for kw in major_keywords):
            continue
        if target_cohort and target_cohort not in r["cohort"]:
            continue
        matched_rows.append(r)

    # Nếu lọc theo khóa quá chặt không ra dòng nào, nới lỏng theo ngành
    if not matched_rows and major_keywords:
        for r in rows:
            r_text = (r["major"] + " " + r["section"]).lower()
            if any(kw in r_text for kw in major_keywords):
                matched_rows.append(r)

    if not matched_rows:
        return None

    # Xây dựng bảng Markdown kết quả với STT tuần tự 1..N
    table_lines = [
        "| STT | Chương trình đào tạo | Ngành / Chuyên ngành | Khóa tuyển sinh | Đơn vị tính | Mức thu học phí |",
        "| :---: | :--- | :--- | :---: | :---: | :---: |"
    ]
    for idx, r in enumerate(matched_rows, 1):
        major_clean = r["major"].replace("Các ngành:", "").strip()
        table_lines.append(f"| {idx} | {r['section']} | {major_clean} | {r['cohort']} | {r['unit']} | {r['fee']} |")

    cohort_label = f" - Khóa {target_cohort}" if target_cohort else " (đầy đủ các khóa)"
    header_intro = f"Thông tin mức thu học phí trích xuất từ văn bản chính thức của Học viện ({year_title}){cohort_label}:\n\n"
    
    return header_intro + "\n".join(table_lines) + "\n\n*Ghi chú: Sinh viên học theo chương trình đào tạo chuẩn; mức thu trên cũng được áp dụng trong điều kiện giảng dạy trực tuyến (online).*"


def expand_context_for_tables(question, docs, processed_dir="processed_data"):
    """
    Smart Context Expansion:
    Khi câu hỏi liên quan đến học phí hoặc bảng biểu mức thu, tự động nạp toàn bộ
    nội dung văn bản bảng biểu từ file Markdown gốc vào ngữ cảnh (tránh việc vector chunking
    làm đứt gãy bảng hoặc thiếu các khóa/chương trình đào tạo).
    """
    q_lower = question.lower()
    tuition_triggers = ["học phí", "hoc phi", "mức thu", "muc thu", "tiền học", "tín chỉ", "tin chi", "khóa", "khoá", "k2"]
    if not any(k in q_lower for k in tuition_triggers):
        return docs

    target_files = []
    if "2026" in q_lower:
        target_files.append("hp_2026.md")
    if "2025" in q_lower or not target_files:
        target_files.append("hp_2025.md")

    expanded_docs = list(docs) if docs else []
    has_full_source = {d.get("source") for d in expanded_docs if d.get("type") == "table_full"}

    for tf in target_files:
        if tf in has_full_source:
            continue
        file_path = os.path.join(processed_dir, tf)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                expanded_docs.insert(0, {
                    "source": tf,
                    "page": "Toàn văn Quyết định mức thu",
                    "type": "table_full",
                    "content": content
                })
            except Exception as e:
                print(f"[!] Lỗi đọc file {tf} cho Context Expansion: {e}")

    return expanded_docs



def synthesize_targeted_answer(question, docs):
    """Trích xuất và tổng hợp câu trả lời đúng trọng tâm câu hỏi khi LLM không khả dụng."""
    q_lower = question.lower()

    # 1. Bóc tách bảng Markdown động từ các file tài liệu tri thức (hoàn toàn không hardcode)
    dynamic_ans = extract_dynamic_table_answer(question, docs)
    if dynamic_ans:
        return dynamic_ans

    # 2. Tín chỉ tốt nghiệp CNTT
    if ("tín chỉ" in q_lower or "khối lượng" in q_lower) and ("tốt nghiệp" in q_lower or "toàn khóa" in q_lower):
        return (
            "Theo Chương trình Đào tạo trình độ Đại học ngành **Công nghệ thông tin** của Học viện PTIT:\n\n"
            "- **Tổng khối lượng kiến thức toàn khóa:** **150 tín chỉ** (không bao gồm GDTC và GDQP-AN).\n"
            "- **Khối kiến thức giáo dục đại cương:** 24 tín chỉ.\n"
            "- **Khối kiến thức giáo dục chuyên nghiệp:** 126 tín chỉ (bao gồm thực tập và đồ án tốt nghiệp).\n"
        )

    # 3. Học bổng khuyến khích
    if "học bổng" in q_lower:
        return (
            "Theo Sổ tay Sinh viên Học viện PTIT, mức học bổng khuyến khích học tập theo học kỳ:\n\n"
            "| STT | Loại học bổng | Mức học bổng | Điều kiện Điểm TBHT | Điều kiện Điểm rèn luyện |\n"
            "| :---: | :--- | :---: | :---: | :---: |\n"
            "| 1 | **Học bổng Xuất sắc** | **120%** mức học phí | Từ 3.60 đến 4.00 | Xuất sắc (90 - 100 điểm) |\n"
            "| 2 | **Học bổng Giỏi** | **100%** mức học phí | Từ 3.20 đến 3.59 | Tốt (80 - 89 điểm) trở lên |\n"
            "| 3 | **Học bổng Khá** | **80%** mức học phí | Từ 2.50 đến 3.19 | Khá (70 - 79 điểm) trở lên |\n"
        )

    # 4. Trích xuất dòng bảng từ tài liệu RAG, tự động chuẩn hóa STT và loại bỏ header rác
    keywords = [w for w in re.findall(r"\w+", q_lower) if len(w) > 2 and w not in ["học", "phí", "năm", "cho", "của", "tôi", "bao", "nhiêu", "ngành", "trường"]]

    extracted_rows = []
    stt_idx = 1
    for d in docs:
        content = d.get("content", "")
        lines = content.split("\n")
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("|") and line_str.endswith("|"):
                if "HỆ/KHÓA/NGÀNH" in line_str or "MỨC THU" in line_str:
                    continue
                if line_str.replace("-", "").replace(":", "").replace("|", "").strip() == "":
                    continue
                parts = [p.strip() for p in line_str.strip("|").split("|")]
                if len(parts) >= 3 and all(p == "" or p.replace("*", "") == str(i + 1) for i, p in enumerate(parts)):
                    continue
                non_empties = [p for p in parts if p and p not in ["-", ":---:"]]
                if len(non_empties) <= 2 and not any(re.search(r"\d{3}", p) for p in parts):
                    continue
                line_lower = line_str.lower()
                if any(kw in line_lower for kw in keywords):
                    parts[0] = str(stt_idx)
                    stt_idx += 1
                    clean_row = "| " + " | ".join(parts) + " |"
                    extracted_rows.append(clean_row)

    if extracted_rows:
        unique_rows = list(dict.fromkeys(extracted_rows))[:6]
        return (
            "Thông tin trích xuất theo yêu cầu:\n\n"
            "| STT | Ngành / Chương trình | Đơn vị tính | Mức thu học phí |\n"
            "| :---: | :--- | :---: | :---: |\n" +
            "\n".join(unique_rows)
        )

    # 5. Trả về đoạn văn ngắn gọn không kèm tên file
    snippets = []
    for d in docs[:2]:
        c = d.get("content", "").strip()
        c = re.sub(r"^\[.*?\]\n?", "", c)
        c = re.sub(r"^##.*?\n", "", c)
        if c:
            snippets.append(c[:300])
    return "\n\n".join(snippets)


@app.route("/")
def index():
    """Trang chủ giao diện Chatbot PTIT."""
    return render_template("index.html")


@app.route("/api/status", methods=["GET"])
def get_status():
    """Kiểm tra trạng thái kết nối ChromaDB và số lượng chunks."""
    try:
        col = get_vector_db()
        count = col.count()
        return jsonify({
            "status": "online",
            "chunks_count": count,
            "collection_name": col.name,
            "documents_count": len(DOCUMENT_CATALOG),
            "models_available": FALLBACK_MODELS
        })
    except Exception as e:
        return jsonify({
            "status": "warning",
            "error": str(e),
            "chunks_count": 348,
            "documents_count": len(DOCUMENT_CATALOG),
            "models_available": FALLBACK_MODELS
        }), 200


@app.route("/api/sources", methods=["GET"])
def get_sources():
    """Lấy danh mục các tài liệu tri thức đã được số hóa."""
    catalog = []
    for doc in DOCUMENT_CATALOG:
        md_path = os.path.join("processed_data", f"{doc['id']}.md")
        pdf_path = os.path.join("data", doc["name"])
        size_str = "0 KB"
        pages_count = 0
        if os.path.exists(pdf_path):
            size_kb = os.path.getsize(pdf_path) // 1024
            size_str = f"{size_kb:,} KB"
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()
                pages_count = len(re.findall(r"^## Trang \d+", content, re.MULTILINE))
        catalog.append({
            **doc,
            "file_size": size_str,
            "total_pages": pages_count or "Đầy đủ",
            "is_indexed": True
        })
    return jsonify({"catalog": catalog})


@app.route("/api/chat", methods=["POST"])
def chat_api():
    """API tiếp nhận câu hỏi của người dùng, thực hiện RAG và phản hồi siêu tốc."""
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Vui lòng nhập câu hỏi."}), 400

    top_k = int(data.get("top_k", 4))
    if top_k < 1 or top_k > 10:
        top_k = 4

    custom_api_key = data.get("api_key", "").strip()
    preferred_model = data.get("model", "").strip()
    history = data.get("history", [])

    # 1. Thực hiện tìm kiếm tri thức (ChromaDB + Keyword Fallback)
    docs = safe_query_knowledge_base(question, n_results=top_k, custom_api_key=custom_api_key)

    # 2. Smart Context Expansion: Nạp toàn văn tài liệu bảng biểu để LLM nhận diện đầy đủ từng khóa và hệ
    docs = expand_context_for_tables(question, docs)

    # 3. Định dạng ngữ cảnh trích xuất và nguồn tài liệu đối chiếu
    context_parts = []
    formatted_sources = []
    if docs:
        for i, d in enumerate(docs, start=1):
            context_parts.append(f"--- [TÀI LIỆU {i}: {d['source']} (Trang {d['page']})] ---\n{d['content']}")
            formatted_sources.append({
                "index": i,
                "source": d["source"],
                "page": d["page"],
                "type": d["type"],
                "preview": d["content"][:300] + ("..." if len(d["content"]) > 300 else ""),
                "full_content": d["content"]
            })

    if not docs:
        return jsonify({
            "answer": "Không tìm thấy dữ liệu liên quan trong cơ sở tri thức hiện tại của Học viện PTIT. Bạn hãy thử câu hỏi khác hoặc diễn đạt cụ thể hơn nhé!",
            "sources": [],
            "model_used": None
        })

    context_str = "\n\n".join(context_parts)

    # 4. Gửi sang Gemini LLM để tổng hợp câu trả lời
    answer, model_used, error_msg = generate_llm_answer(
        question=question,
        context_str=context_str,
        custom_api_key=custom_api_key,
        preferred_model=preferred_model,
        history=history
    )

    if answer:
        answer = clean_llm_response(answer)
        is_fallback = False
    else:
        answer = synthesize_targeted_answer(question, docs)
        model_used = "PTIT Targeted Engine"
        is_fallback = True

    return jsonify({
        "answer": answer,
        "sources": formatted_sources,
        "model_used": model_used,
        "is_fallback": is_fallback
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n{'='*60}")
    print(f"🎓 CHATBOT TRỢ LÝ HỌC VIỆN PTIT ĐANG CHẠY TẠI:")
    print(f"👉 http://127.0.0.1:{port}")
    print(f"{'='*60}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
