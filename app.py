import os
import re
import sys
import time
import uuid
import json
import shutil
import hashlib
import requests
import subprocess
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
import document_parser
import voice_service

load_dotenv()
app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed_data")
VOICE_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "voice_uploads")
USER_UPLOADS_DIR = os.path.join(BASE_DIR, "user_uploads")
os.makedirs(VOICE_UPLOAD_DIR, exist_ok=True)
os.makedirs(USER_UPLOADS_DIR, exist_ok=True)

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


def get_vector_db(chroma_dir=CHROMA_DIR):
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


_cached_user_collection = None


def get_user_vector_db(chroma_dir=CHROMA_DIR):
    """Khởi tạo và cache kết nối tới collection user_uploaded_docs cho tài liệu người dùng tải lên."""
    global _cached_chroma_client, _cached_user_collection
    if _cached_user_collection is not None:
        return _cached_user_collection
    get_vector_db(chroma_dir)
    _cached_user_collection = _cached_chroma_client.get_or_create_collection(
        name="user_uploaded_docs",
        metadata={"hnsw:space": "cosine"}
    )
    return _cached_user_collection


def cleanup_expired_user_docs(max_age_hours=None):
    """
    Giữ tài liệu người dùng vĩnh viễn theo phiên làm việc để khi khởi động lại server
    client vẫn có thể tiếp tục truy vấn tài liệu cũ (chỉ xóa khi người dùng chủ động yêu cầu).
    """
    pass


def get_session_uploaded_files(session_id):
    """Lấy danh sách các file duy nhất đã tải lên trong phiên (từ ChromaDB và thư mục user_uploads)."""
    if not session_id:
        return []
    try:
        coll = get_user_vector_db()
        res = coll.get(where={"session_id": session_id}, include=["metadatas"])
        files_map = {}
        if res and res.get("metadatas"):
            for m in res["metadatas"]:
                fname = m.get("filename")
                if fname:
                    if fname not in files_map:
                        files_map[fname] = {
                            "filename": fname,
                            "chunks_count": 0,
                            "uploaded_at": m.get("created_at", time.time())
                        }
                    files_map[fname]["chunks_count"] += 1

        # Đọc thêm từ thư mục đĩa user_uploads/{session_id} để bảo toàn nếu restart server
        session_dir = os.path.join(USER_UPLOADS_DIR, session_id)
        if os.path.exists(session_dir):
            for item in os.listdir(session_dir):
                if item.endswith("_extracted.json"):
                    continue
                fpath = os.path.join(session_dir, item)
                if os.path.isfile(fpath) and item not in files_map:
                    chunks_count = 1
                    ext_json = os.path.join(session_dir, f"{os.path.splitext(item)[0]}_extracted.json")
                    if os.path.exists(ext_json):
                        try:
                            with open(ext_json, "r", encoding="utf-8") as f_ext:
                                d_ext = json.load(f_ext)
                                chunks_count = d_ext.get("total_chunks", len(d_ext.get("chunks", []))) or 1
                        except Exception:
                            pass
                    files_map[item] = {
                        "filename": item,
                        "chunks_count": chunks_count,
                        "uploaded_at": os.path.getmtime(fpath)
                    }

        return list(files_map.values())
    except Exception as e:
        print(f"[!] Error getting session files: {e}")
        return []


def get_session_intro_chunks(session_id):
    """Lấy chunk mở đầu (Trang 1 / chunk_index=0) của từng file tải lên để luôn có tiêu đề và chủ đề."""
    if not session_id:
        return []
    try:
        coll = get_user_vector_db()
        res = coll.get(where={"session_id": session_id}, include=["documents", "metadatas"])
        intro_chunks = []
        seen_files = set()
        if res and res.get("documents"):
            for doc, meta in zip(res["documents"], res["metadatas"]):
                fn = meta.get("filename")
                c_idx = meta.get("chunk_index", 0)
                if fn and fn not in seen_files and (c_idx == 0 or meta.get("page", 1) == 1):
                    seen_files.add(fn)
                    intro_chunks.append({
                        "content": doc,
                        "filename": fn,
                        "page": meta.get("page", 1),
                        "source_type": "user_doc"
                    })
        return intro_chunks
    except Exception as e:
        print(f"[!] Error getting intro chunks: {e}")
        return []


IT_SUBJECT_MAPPING = {
    "socket": ["socket", "lập trình mạng"],
    "sockets": ["socket", "lập trình mạng"],
    "network": ["mạng", "mạng máy tính", "lập trình mạng"],
    "networking": ["mạng", "mạng máy tính"],
    "programming": ["lập trình"],
    "database": ["cơ sở dữ liệu"],
    "os": ["hệ điều hành"],
    "operating": ["hệ điều hành"],
    "algorithm": ["thuật toán", "giải thuật"],
    "security": ["an toàn thông tin", "an ninh mạng"],
    "web": ["lập trình web"],
    "ai": ["trí tuệ nhân tạo"]
}


def extract_user_doc_topics(session_id):
    """Trích xuất từ khóa chủ đề cốt lõi từ tên file và trang mở đầu của các tài liệu tải lên."""
    if not session_id:
        return []
    keywords = []
    files = get_session_uploaded_files(session_id)
    for f in files:
        fname = f.get("filename", "")
        name_clean = os.path.splitext(fname)[0].replace("-", " ").replace("_", " ")
        for w in re.findall(r"\w+", name_clean):
            if len(w) > 2 and w.lower() not in ["notes", "slide", "slides", "bai", "giang", "de", "cuong", "doc", "tailieu", "pdf"]:
                keywords.append(w)

    intros = get_session_intro_chunks(session_id)
    for it in intros:
        lines = it.get("content", "").splitlines()[:6]
        for line in lines:
            for w in re.findall(r"\b[A-Za-zÀ-ỹ]{3,}\b", line):
                wl = w.lower()
                if wl not in ["the", "and", "for", "with", "all", "rights", "reserved", "page", "copyright"]:
                    keywords.append(w)

    seen = set()
    unique_kw = []
    for k in keywords:
        kl = k.lower()
        if kl not in seen:
            seen.add(kl)
            unique_kw.append(k)
            # Tự động ánh xạ môn học tiếng Anh sang tiếng Việt PTIT
            if kl in IT_SUBJECT_MAPPING:
                for mapped_term in IT_SUBJECT_MAPPING[kl]:
                    if mapped_term.lower() not in seen:
                        seen.add(mapped_term.lower())
                        unique_kw.append(mapped_term)

    return unique_kw[:12]


VI_STOPWORDS = {
    "là", "gì", "có", "của", "trong", "cho", "với", "như", "thế", "nào",
    "bao", "nhiêu", "file", "tài", "liệu", "này", "đó", "các", "những",
    "được", "không", "hãy", "về", "theo", "tại", "và", "hoặc", "thì",
    "mà", "ở", "khi", "nếu", "để", "từ", "đến", "cần", "phải", "một"
}

_query_embedding_cache = {}


def ensure_session_in_chromadb(session_id, coll=None, custom_api_key=None):
    """
    Tự phục hồi dữ liệu theo từng file: Nếu ChromaDB bị mất vector nhưng file _extracted.json
    vẫn còn trong user_uploads/{session_id}, tự động khôi phục ngay từ vector đã lưu trong JSON
    (0ms, không tốn API) hoặc tạo lại vector nếu JSON cũ chưa có embeddings.
    """
    if not session_id:
        return
    session_dir = os.path.join(USER_UPLOADS_DIR, session_id)
    if not os.path.exists(session_dir):
        return

    try:
        if coll is None:
            coll = get_user_vector_db()
        existing = coll.get(where={"session_id": session_id}, include=["metadatas"])
        existing_files_in_db = set()
        if existing and existing.get("metadatas"):
            for m in existing["metadatas"]:
                if m and m.get("filename"):
                    existing_files_in_db.add(m["filename"])

        active_key = (custom_api_key or "").strip() or API_KEY
        for item in os.listdir(session_dir):
            if not item.endswith("_extracted.json"):
                continue
            json_path = os.path.join(session_dir, item)
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            fname = data.get("filename", item.replace("_extracted.json", ""))
            if fname in existing_files_in_db:
                continue

            chunks = data.get("chunks", [])
            if not chunks:
                continue

            cached_embeddings = data.get("embeddings")
            if not cached_embeddings or len(cached_embeddings) != len(chunks):
                chunk_texts = [c["text"] for c in chunks]
                cached_embeddings = document_parser.batch_get_embeddings(chunk_texts, api_key=active_key)

            valid_ids, valid_emb, valid_docs, valid_metas = [], [], [], []
            now_ts = data.get("uploaded_at", time.time())
            for idx, (c, emb) in enumerate(zip(chunks, cached_embeddings)):
                if emb:
                    valid_ids.append(f"{session_id}_{fname}_{idx}_{int(now_ts)}")
                    valid_emb.append(emb)
                    valid_docs.append(c["text"])
                    valid_metas.append({
                        "session_id": session_id,
                        "filename": fname,
                        "page": c.get("page", 1),
                        "chunk_index": c.get("chunk_index", idx),
                        "created_at": now_ts
                    })
            if valid_ids:
                coll.add(ids=valid_ids, embeddings=valid_emb, documents=valid_docs, metadatas=valid_metas)
                print(f"[*] Tự động phục hồi {len(valid_ids)} chunks của '{fname}' (session '{session_id}') từ cache đĩa.")
    except Exception as e:
        print(f"[!] Warning during ensure_session_in_chromadb: {e}")


def keyword_search_user_docs(query, session_id, coll=None):
    """
    Tìm kiếm kết hợp từ khóa & cụm từ (N-gram + Technical Tokens) trên tài liệu người dùng tải lên,
    đã loại bỏ hư từ tiếng Việt (stopwords) để chấm điểm chính xác các thuật ngữ, mục lục, con số.
    """
    if not session_id or not query:
        return []
    q_lower = query.lower().strip()
    raw_words = [w for w in re.findall(r"[\w\.\+\-#%]+", q_lower) if len(w) > 1]
    q_words = [w for w in raw_words if w not in VI_STOPWORDS]
    if not q_words:
        q_words = raw_words
    if not q_words:
        return []

    try:
        if coll is None:
            coll = get_user_vector_db()
        all_docs = coll.get(where={"session_id": session_id}, include=["documents", "metadatas"])
        if not all_docs or not all_docs.get("documents"):
            return []

        results = []
        for doc, meta in zip(all_docs["documents"], all_docs["metadatas"]):
            d_lower = doc.lower()
            score = 0

            # 1. Khớp nguyên câu hoặc cụm từ liền kề (2-gram, 3-gram)
            if len(q_lower) > 4 and q_lower in d_lower:
                score += 160
            else:
                for l in range(min(len(q_words), 4), 1, -1):
                    for start in range(len(q_words) - l + 1):
                        subphrase = " ".join(q_words[start:start + l])
                        if len(subphrase) > 3 and subphrase in d_lower:
                            score += 35 * l

            # 2. Khớp từng từ khóa chuyên môn / số mục
            for w in q_words:
                cnt = d_lower.count(w)
                if cnt > 0:
                    # Ưu tiên cao hơn cho từ khóa chứa chữ số, ký hiệu kỹ thuật (VD: 2.3, socket, c++)
                    weight = 35 if any(ch.isdigit() or ch in ".+-#%" for ch in w) else 20
                    score += weight * min(cnt, 4)

            if score > 0:
                results.append({
                    "content": doc,
                    "filename": meta.get("filename", "Tài liệu người dùng"),
                    "page": meta.get("page", 1),
                    "chunk_index": meta.get("chunk_index", 0),
                    "source_type": "user_doc",
                    "score": score
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:4]
    except Exception as e:
        print(f"[!] Error in keyword_search_user_docs: {e}")
        return []


def _merge_overlapping_text(base_text, next_text):
    """Ghép nối 2 đoạn văn bản liền kề và loại bỏ phần trùng lặp (chunk_overlap) ở biên."""
    if not base_text:
        return next_text
    if not next_text:
        return base_text
    max_overlap = min(250, len(base_text), len(next_text))
    for size in range(max_overlap, 25, -1):
        if base_text[-size:] == next_text[:size]:
            return base_text + next_text[size:]
    return base_text + "\n" + next_text


def expand_neighbor_chunks(top_candidates, session_id, coll=None):
    """
    Kỹ thuật Neighbor Chunk Expansion:
    Với các ứng viên có điểm cao nhất (Top 1 - Top 2), tự động lấy đoạn kế tiếp (chunk_index + 1)
    trong cùng file để ghép nối liền mạch (loại bỏ phần lặp overlap), giúp bảng biểu/định nghĩa
    không bị cắt cụt giữa chừng mà vẫn bảo toàn đủ số lượng n_results đoạn khác nhau.
    """
    if not top_candidates or not session_id:
        return top_candidates

    try:
        if coll is None:
            coll = get_user_vector_db()

        existing_pairs = {(c.get("filename"), c.get("chunk_index")) for c in top_candidates}

        for idx, item in enumerate(top_candidates[:2]):
            fname = item.get("filename")
            c_idx = item.get("chunk_index")
            if fname is None or c_idx is None:
                continue
            next_idx = c_idx + 1
            if (fname, next_idx) in existing_pairs:
                continue

            res_next = coll.get(
                where={"$and": [
                    {"session_id": session_id},
                    {"filename": fname},
                    {"chunk_index": next_idx}
                ]},
                include=["documents", "metadatas"]
            )
            if res_next and res_next.get("documents") and len(res_next["documents"]) > 0:
                next_doc = res_next["documents"][0]
                item["content"] = _merge_overlapping_text(item["content"], next_doc)
                existing_pairs.add((fname, next_idx))

        return top_candidates
    except Exception as e:
        print(f"[!] Error in expand_neighbor_chunks: {e}")
        return top_candidates


def query_user_documents(query, session_id, n_results=4, custom_api_key=None, query_embedding=None):
    """
    Truy vấn kết hợp Hybrid Search (Cosine Similarity Distance + Keyword N-gram Match)
    kèm kỹ thuật Neighbor Chunk Expansion cho tài liệu người dùng tải lên.
    """
    if not session_id:
        return []

    coll = get_user_vector_db()

    # 0. Tự phục hồi dữ liệu từ file _extracted.json nếu ChromaDB bị thiếu vector của phiên
    ensure_session_in_chromadb(session_id, coll, custom_api_key)

    matched = []
    # 1. Vector Search có tính điểm khoảng cách Cosine (Cosine Distance Scoring)
    q_vec = query_embedding or get_embedding_rest(query, api_key=custom_api_key)
    if q_vec:
        try:
            res = coll.query(
                query_embeddings=[q_vec],
                n_results=n_results * 2,
                where={"session_id": session_id},
                include=["documents", "metadatas", "distances"]
            )
            if res and res.get("documents") and len(res["documents"]) > 0:
                docs_list = res["documents"][0]
                metas_list = res["metadatas"][0]
                dists_list = res.get("distances", [[]])[0] if res.get("distances") else [0.3] * len(docs_list)
                for rank_idx, (doc, meta, dist) in enumerate(zip(docs_list, metas_list, dists_list)):
                    sim_score = max(15.0, (1.0 - float(dist)) * 120.0) + max(0, (n_results * 2 - rank_idx) * 5)
                    matched.append({
                        "content": doc,
                        "filename": meta.get("filename", "Tài liệu người dùng"),
                        "page": meta.get("page", 1),
                        "chunk_index": meta.get("chunk_index", 0),
                        "source_type": "user_doc",
                        "score": sim_score
                    })
        except Exception as e:
            print(f"[!] Error querying user docs: {e}")

    # 2. Keyword & Subphrase Search trên toàn bộ chunks của session_id
    keyword_hits = keyword_search_user_docs(query, session_id, coll)

    # 3. Kết hợp và xếp hạng (Hybrid Rank Fusion)
    combined_map = {}

    for item in matched:
        key = (item.get("filename"), item.get("chunk_index"))
        combined_map[key] = dict(item)

    for kw_item in keyword_hits:
        key = (kw_item.get("filename"), kw_item.get("chunk_index"))
        if key in combined_map:
            combined_map[key]["score"] = combined_map[key].get("score", 0) + kw_item.get("score", 0) + 60
        else:
            combined_map[key] = dict(kw_item)

    combined = sorted(combined_map.values(), key=lambda x: x.get("score", 0), reverse=True)
    top_candidates = combined[:n_results]

    # 4. Kỹ thuật Neighbor Chunk Expansion: Ghép nối liền mạch đoạn kế tiếp (chunk_index + 1)
    expanded_candidates = expand_neighbor_chunks(top_candidates, session_id, coll)

    # 5. Luôn bổ sung chunk mở đầu (Trang 1 chứa tên môn/tiêu đề) nếu chưa có
    intro_chunks = get_session_intro_chunks(session_id)
    seen_keys = {(m.get("filename"), m.get("chunk_index")) for m in expanded_candidates}
    for it in intro_chunks:
        it_key = (it.get("filename"), it.get("chunk_index", 0))
        if it_key not in seen_keys and all(it["content"] not in m["content"] for m in expanded_candidates):
            expanded_candidates.insert(0, it)
            seen_keys.add(it_key)

    return expanded_candidates[:max(n_results + 1, len(intro_chunks))]


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
    """Tạo vector embedding cho câu hỏi qua REST API (có bộ nhớ đệm LRU trong RAM để tăng tốc)."""
    if not text:
        return None
    norm_text = text.strip()
    if norm_text in _query_embedding_cache:
        return _query_embedding_cache[norm_text]

    clean_key = api_key.strip() if api_key else API_KEY
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={clean_key}"
    payload = {"content": {"parts": [{"text": norm_text}]}}
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if "embedding" in data and "values" in data["embedding"]:
                vec = data["embedding"]["values"]
                if len(_query_embedding_cache) >= 256:
                    _query_embedding_cache.pop(next(iter(_query_embedding_cache)))
                _query_embedding_cache[norm_text] = vec
                return vec
    except Exception:
        pass
    return None


# ==============================================================================
# HYBRID RETRIEVAL (TÌM KIẾM TÀI LIỆU CHÍNH XÁC & MỞ RỘNG TRANG CHA)
# ==============================================================================

def get_parent_document_page(source_file, page_num, processed_dir=PROCESSED_DIR):
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


def keyword_search_all(query, processed_dir=PROCESSED_DIR, top_k=3):
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


def smart_query_knowledge_base(query, n_results=4, custom_api_key=None, query_embedding=None):
    """Truy vấn kết hợp Hybrid Search (Keyword + Vector) và mở rộng trang cha (hỗ trợ tái sử dụng vector có sẵn)."""
    active_key = custom_api_key.strip() if (custom_api_key and custom_api_key.strip()) else API_KEY
    matched_chunks = []

    try:
        q_vec = query_embedding or get_embedding_rest(query, active_key, timeout=3.0)
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

def generate_llm_answer(question, context_str, custom_api_key=None, preferred_model=None, history=None, has_user_docs=False, user_files=None):
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

    user_docs_instruction = ""
    if has_user_docs:
        files_list_str = ", ".join([f["filename"] for f in (user_files or [])]) if user_files else "Tài liệu người dùng tải lên"
        user_docs_instruction = f"""
4. NGUYÊN TẮC BẮT BUỘC KHI XỬ LÝ TÀI LIỆU NGƯỜI DÙNG TẢI LÊN ({files_list_str}):
   - ĐẶC BIỆT CHÚ Ý ĐẠI TỪ THAY THẾ: Khi người dùng đặt câu hỏi có từ chỉ định như "môn học này", "môn này", "học phần này", "tài liệu này", "file này", "bài này", "nội dung này", "chủ đề này", "kiến thức này":
     -> Người dùng ĐANG HỎI VỀ CHỦ ĐỀ/MÔN HỌC TRONG TÀI LIỆU HỌ VỪA TẢI LÊN ({files_list_str}).
     -> Bạn TUYỆT ĐỐI KHÔNG ĐƯỢC trả lời rằng "chưa xác định rõ môn học nào" hay hỏi ngược lại người dùng.
     -> Hãy phân tích tên file ({files_list_str}) và các đoạn trích dẫn tài liệu người dùng ở trên để xác định môn học/chủ đề (Ví dụ: file Sockets-notes.pdf là về Sockets / Lập trình mạng - Network Programming).
     -> Sau đó, hãy đối chiếu môn học/chủ đề đó với Cơ sở dữ liệu PTIT để trả lời chi tiết: Môn học này có trong chương trình đào tạo của PTIT không, thuộc ngành nào (ví dụ ngành Công nghệ Thông tin, chuyên ngành Mạng máy tính và truyền thông dữ liệu...), mã học phần là gì, số tín chỉ, học kỳ, môn tiên quyết nếu có.
   - Khi trả lời, hãy mở đầu rõ ràng: "Dựa trên tài liệu **{files_list_str}** bạn đã tải lên, tài liệu đề cập đến môn học/chủ đề **[Tên môn/chủ đề]**... Đối chiếu với chương trình đào tạo của Học viện PTIT...".
   - Nếu có sự khác biệt hoặc mâu thuẫn giữa thông tin trong file người dùng tải lên và quy định chính thức của PTIT, hãy chỉ ra điểm khác biệt đó một cách khách quan.
"""

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
{user_docs_instruction}"""

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


@app.route("/api/upload", methods=["POST"])
def upload_documents():
    session_id = request.form.get("session_id", "").strip()
    custom_api_key = request.form.get("api_key", "").strip()
    active_key = custom_api_key if custom_api_key else API_KEY

    if not session_id:
        return jsonify({"error": "Thiếu mã phiên (session_id)."}), 400

    if "files" not in request.files:
        return jsonify({"error": "Không tìm thấy file tải lên."}), 400

    uploaded_files = request.files.getlist("files")
    if not uploaded_files or (len(uploaded_files) == 1 and uploaded_files[0].filename == ""):
        return jsonify({"error": "Vui lòng chọn ít nhất 1 file."}), 400

    existing_files = get_session_uploaded_files(session_id)
    existing_filenames = {f["filename"] for f in existing_files}

    valid_new_files = [f for f in uploaded_files if f.filename]
    incoming_filenames = {f.filename for f in valid_new_files}
    total_unique = len(existing_filenames.union(incoming_filenames))

    if total_unique > 3:
        return jsonify({
            "error": f"Mỗi phiên chỉ được tải tối đa 3 tài liệu. Hiện tại bạn đã có {len(existing_files)} tài liệu."
        }), 400

    coll = get_user_vector_db()
    processed_files = []

    for f in valid_new_files:
        fname = f.filename
        if not document_parser.is_allowed_file(fname):
            return jsonify({
                "error": f"File '{fname}' không được hỗ trợ. Chỉ chấp nhận các định dạng: .pdf, .docx, .txt, .md"
            }), 400

        file_bytes = f.read()
        if len(file_bytes) > document_parser.MAX_FILE_SIZE_BYTES:
            return jsonify({
                "error": f"File '{fname}' vượt quá dung lượng tối đa 5MB cho phép."
            }), 400

        file_hash = hashlib.md5(file_bytes).hexdigest()
        session_dir = os.path.join(USER_UPLOADS_DIR, session_id)
        os.makedirs(session_dir, exist_ok=True)
        base_name = os.path.splitext(fname)[0]
        extracted_json_path = os.path.join(session_dir, f"{base_name}_extracted.json")

        # 0. Kiểm tra Cache MD5 nếu người dùng tải lại đúng file cũ không thay đổi
        chunks = None
        embeddings = None
        if os.path.exists(extracted_json_path):
            try:
                with open(extracted_json_path, "r", encoding="utf-8") as f_cached:
                    cached_data = json.load(f_cached)
                if cached_data.get("file_hash") == file_hash and cached_data.get("chunks") and cached_data.get("embeddings"):
                    chunks = cached_data["chunks"]
                    embeddings = cached_data["embeddings"]
            except Exception:
                pass

        if chunks is None:
            try:
                chunks = document_parser.extract_chunks_from_document(file_bytes, fname)
            except ValueError as ve:
                return jsonify({"error": str(ve)}), 400
            except Exception as ex:
                return jsonify({"error": f"Lỗi xử lý file '{fname}': {str(ex)}"}), 500

        # LƯU FILE GỐC CỦA CLIENT VÀO user_uploads/{session_id}/
        saved_file_path = os.path.join(session_dir, fname)
        with open(saved_file_path, "wb") as f_out:
            f_out.write(file_bytes)

        if embeddings is None:
            chunk_texts = [c["text"] for c in chunks]
            embeddings = document_parser.batch_get_embeddings(chunk_texts, api_key=active_key)

        now_ts = time.time()
        # LƯU DỮ LIỆU TRÍCH XUẤT KÈM HASH & EMBEDDINGS ĐỂ PHỤC HỒI TỨC THÌ (0ms)
        try:
            with open(extracted_json_path, "w", encoding="utf-8") as f_json:
                json.dump({
                    "filename": fname,
                    "session_id": session_id,
                    "file_hash": file_hash,
                    "uploaded_at": now_ts,
                    "total_chunks": len(chunks),
                    "chunks": chunks,
                    "embeddings": embeddings
                }, f_json, ensure_ascii=False)
        except Exception as e_json:
            print(f"[!] Warning saving extracted json: {e_json}")

        if fname in existing_filenames:
            try:
                coll.delete(where={"$and": [{"session_id": session_id}, {"filename": fname}]})
            except Exception:
                pass

        valid_ids = []
        valid_embeddings = []
        valid_docs = []
        valid_metas = []

        for idx, (c, emb) in enumerate(zip(chunks, embeddings)):
            if emb:
                valid_ids.append(f"{session_id}_{fname}_{idx}_{int(now_ts)}")
                valid_embeddings.append(emb)
                valid_docs.append(c["text"])
                valid_metas.append({
                    "session_id": session_id,
                    "filename": fname,
                    "page": c.get("page", 1),
                    "chunk_index": c.get("chunk_index", 0),
                    "created_at": now_ts
                })

        if not valid_embeddings:
            return jsonify({
                "error": f"Không thể tạo vector nhúng cho file '{fname}'. Vui lòng kiểm tra lại API Key hoặc kết nối mạng."
            }), 500

        coll.add(
            ids=valid_ids,
            embeddings=valid_embeddings,
            documents=valid_docs,
            metadatas=valid_metas
        )
        processed_files.append({"filename": fname, "chunks": len(valid_docs)})

    updated_files = get_session_uploaded_files(session_id)
    return jsonify({
        "status": "success",
        "message": f"Đã nạp thành công {len(processed_files)} tài liệu.",
        "files": updated_files
    })


@app.route("/api/session-docs", methods=["GET", "DELETE"])
def session_docs():
    if request.method == "GET":
        session_id = request.args.get("session_id", "").strip()
        files = get_session_uploaded_files(session_id)
        return jsonify({"files": files})

    data = request.get_json() or {}
    session_id = (data.get("session_id") or request.args.get("session_id") or "").strip()
    filename = (data.get("filename") or request.args.get("filename") or "").strip()

    if not session_id:
        return jsonify({"error": "Thiếu mã phiên (session_id)."}), 400

    coll = get_user_vector_db()
    try:
        session_dir = os.path.join(USER_UPLOADS_DIR, session_id)
        if filename:
            coll.delete(where={"$and": [{"session_id": session_id}, {"filename": filename}]})
            target_file = os.path.join(session_dir, filename)
            extracted_json = os.path.join(session_dir, f"{os.path.splitext(filename)[0]}_extracted.json")
            if os.path.exists(target_file):
                try:
                    os.remove(target_file)
                except Exception:
                    pass
            if os.path.exists(extracted_json):
                try:
                    os.remove(extracted_json)
                except Exception:
                    pass
        else:
            coll.delete(where={"session_id": session_id})
            if os.path.exists(session_dir):
                shutil.rmtree(session_dir, ignore_errors=True)
    except Exception as e:
        print(f"[!] Delete session doc error: {e}")

    files = get_session_uploaded_files(session_id)
    return jsonify({"status": "success", "files": files})


@app.route("/api/upload-voice", methods=["POST"])
def upload_voice():
    """Nhận file âm thanh ghi âm từ client và lưu trữ để phát lại kiểu Messenger."""
    if "audio" not in request.files:
        return jsonify({"error": "Không tìm thấy dữ liệu âm thanh."}), 400

    file = request.files["audio"]
    if not file or file.filename == "":
        return jsonify({"error": "File âm thanh rỗng."}), 400

    filename = file.filename or "recording.webm"
    ext = "webm"
    if "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ["webm", "wav", "mp3", "ogg", "m4a"]:
        ext = "webm"

    timestamp = int(time.time() * 1000)
    unique_id = uuid.uuid4().hex[:8]
    saved_filename = f"voice_{timestamp}_{unique_id}.{ext}"
    filepath = os.path.join(VOICE_UPLOAD_DIR, saved_filename)

    try:
        file.save(filepath)
        audio_url = f"/static/voice_uploads/{saved_filename}"
        return jsonify({
            "status": "success",
            "audio_url": audio_url,
            "filename": saved_filename
        })
    except Exception as e:
        print(f"[!] Lỗi khi lưu file ghi âm: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/tts", methods=["POST"])
def text_to_speech():
    """Tạo âm thanh đọc câu trả lời tiếng Việt đồng nhất (Edge-TTS + gTTS fallback)."""
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    voice = (data.get("voice") or "vi-VN-HoaiMyNeural").strip()

    if not text:
        return jsonify({"error": "Vui lòng cung cấp văn bản cần đọc."}), 400

    result = voice_service.generate_speech(text=text, voice=voice)
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route("/api/stt", methods=["POST"])
def speech_to_text():
    """Nhận diện giọng nói tiếng Việt bằng Google Gemini Audio API (STT Fallback)."""
    if "audio" not in request.files:
        return jsonify({"error": "Không tìm thấy file âm thanh."}), 400

    file = request.files["audio"]
    custom_api_key = request.form.get("api_key", "").strip()

    try:
        audio_bytes = file.read()
        mime_type = file.mimetype or "audio/webm"
        transcript = voice_service.transcribe_audio_gemini(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            api_key=custom_api_key or API_KEY
        )
        return jsonify({"status": "success", "transcript": transcript})
    except Exception as e:
        print(f"[!] STT Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    question = (data.get("question") or data.get("message") or "").strip()
    session_id = (data.get("session_id") or "").strip()
    scope = (data.get("scope") or "hybrid").strip().lower()
    history = data.get("history", [])
    custom_api_key = (data.get("api_key") or data.get("custom_api_key") or "").strip()
    preferred_model = (data.get("model") or data.get("preferred_model") or "").strip()
    top_k = int(data.get("top_k") or 4)

    if not question:
        return jsonify({"error": "Vui lòng nhập câu hỏi."}), 400

    user_files = get_session_uploaded_files(session_id) if session_id else []
    has_user_files = len(user_files) > 0
    effective_scope = scope if has_user_files else "ptit_only"

    user_docs = []
    ptit_docs = []

    # Phát hiện các câu hỏi dùng đại từ chỉ định ("môn học này", "tài liệu này"...)
    q_lower = question.lower()
    is_referential = any(k in q_lower for k in [
        "môn học này", "môn này", "học phần này", "tài liệu này", "file này",
        "bài này", "nội dung này", "chủ đề này", "kiến thức này", "giáo trình này",
        "đề cương này", "trong file", "trong tài liệu", "tài liệu vừa", "file vừa",
        "môn nào", "ngành nào", "chương trình nào"
    ])
    user_topics = extract_user_doc_topics(session_id) if has_user_files else []

    ptit_search_query = question
    if has_user_files and is_referential and user_topics:
        # Bổ sung từ khóa của tài liệu vào câu truy vấn tra cứu PTIT
        ptit_search_query = f"{question} {' '.join(user_topics)}"

    if effective_scope == "user_only":
        user_docs = query_user_documents(question, session_id, n_results=top_k, custom_api_key=custom_api_key)
    elif effective_scope == "ptit_only":
        ptit_docs = smart_query_knowledge_base(question, n_results=top_k, custom_api_key=custom_api_key)
    else:  # hybrid: Quota Retrieval chạy song song (Parallel) & Tối ưu 1 lần gọi Embedding API duy nhất
        active_key = custom_api_key if custom_api_key else API_KEY
        if ptit_search_query == question:
            q_vec_user = get_embedding_rest(question, active_key, timeout=3.0)
            q_vec_ptit = q_vec_user
        else:
            batch_vecs = document_parser.batch_get_embeddings([question, ptit_search_query], api_key=active_key, timeout=4.0)
            q_vec_user = batch_vecs[0] if len(batch_vecs) > 0 else None
            q_vec_ptit = batch_vecs[1] if len(batch_vecs) > 1 else q_vec_user

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_user = executor.submit(
                query_user_documents,
                question,
                session_id,
                4,
                custom_api_key,
                q_vec_user
            )
            future_ptit = executor.submit(
                smart_query_knowledge_base,
                ptit_search_query,
                4,
                custom_api_key,
                q_vec_ptit
            )
            user_docs = future_user.result()
            ptit_docs = future_ptit.result()

    context_sections = []
    if user_docs:
        u_parts = [f"--- [{d['filename']} - Trang {d['page']}] ---\n{d['content']}" for d in user_docs]
        context_sections.append("=== [TÀI LIỆU DO NGƯỜI DÙNG TẢI LÊN] ===\n" + "\n\n".join(u_parts))

    if ptit_docs:
        p_parts = [f"--- [TÀI LIỆU PTIT {i}] ---\n{d['content']}" for i, d in enumerate(ptit_docs, start=1)]
        context_sections.append("=== [CƠ SỞ DỮ LIỆU CHÍNH THỨC PTIT] ===\n" + "\n\n".join(p_parts))

    context_str = "\n\n".join(context_sections) if context_sections else "Không tìm thấy dữ liệu trực tiếp."

    answer, model_used, error_msg = generate_llm_answer(
        question=question,
        context_str=context_str,
        custom_api_key=custom_api_key,
        preferred_model=preferred_model,
        history=history,
        has_user_docs=bool(user_docs),
        user_files=user_files
    )

    if not answer:
        print(f"[!] LLM không phản hồi ({error_msg}), chuyển sang chế độ dự phòng an toàn...")
        answer = safe_fallback_answer(question, ptit_docs or user_docs)
        model_used = "PTIT Safe Engine (Dự phòng)"

    clean_answer = clean_llm_response(answer)
    referenced_files = [f["filename"] for f in user_files] if user_docs else []
    return jsonify({
        "answer": clean_answer,
        "model_used": model_used,
        "scope_used": effective_scope,
        "referenced_files": referenced_files,
        "sources": []
    })


@app.route("/api/reset", methods=["POST"])
def reset():
    data = request.get_json() or {}
    session_id = (data.get("session_id") or "").strip()
    if session_id:
        try:
            coll = get_user_vector_db()
            coll.delete(where={"session_id": session_id})
            session_dir = os.path.join(USER_UPLOADS_DIR, session_id)
            if os.path.exists(session_dir):
                shutil.rmtree(session_dir, ignore_errors=True)
        except Exception:
            pass
    return jsonify({"status": "success", "message": "Đã làm mới phiên hội thoại và dọn dẹp tài liệu tải lên."})


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
