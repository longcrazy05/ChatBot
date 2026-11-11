import os
import re
import sys
import time
import uuid
import json
import shutil
import hashlib
import requests
from requests.adapters import HTTPAdapter
import subprocess
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, send_file
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import document_parser
import voice_service
import web_search

load_dotenv()
app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed_data")
DATA_DIR = os.path.join(BASE_DIR, "data")
VOICE_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "voice_uploads")
USER_UPLOADS_DIR = os.path.join(BASE_DIR, "user_uploads")
os.makedirs(VOICE_UPLOAD_DIR, exist_ok=True)
os.makedirs(USER_UPLOADS_DIR, exist_ok=True)

# Danh mục ánh xạ chuẩn giữa tên file Markdown nội bộ, file PDF gốc và tên văn bản chính thức
PTIT_DOC_METADATA = {
    "clb": {
        "pdf_file": "clb.pdf",
        "md_file": "clb.md",
        "title": "Danh sách Câu lạc bộ Sinh viên PTIT",
        "category": "Hoạt động Sinh viên"
    },
    "ct_cntt": {
        "pdf_file": "ct_cntt.pdf",
        "md_file": "ct_cntt.md",
        "title": "Quyết định 979/QĐ-HV Chương trình đào tạo ngành CNTT",
        "category": "Chương trình Đào tạo"
    },
    "doi_diem_clc": {
        "pdf_file": "doi_diem_clc.pdf",
        "md_file": "doi_diem_clc.md",
        "title": "Bảng quy đổi điểm tiếng Anh Chương trình Chất lượng cao",
        "category": "Quy chế Đào tạo"
    },
    "giang_vien": {
        "pdf_file": "giang_vien.pdf",
        "md_file": "giang_vien.md",
        "title": "Danh sách Giảng viên cơ hữu Học viện PTIT",
        "category": "Thông tin Giảng viên"
    },
    "hb_hk1_25-26": {
        "pdf_file": "HB_HK1_25-26.pdf",
        "md_file": "HB_HK1_25-26.md",
        "title": "Điểm chuẩn Học bổng KKHT Học kỳ 1 năm học 2025-2026",
        "category": "Học bổng"
    },
    "hp_2025": {
        "pdf_file": "hp_2025.pdf",
        "md_file": "hp_2025.md",
        "title": "Quyết định 1120/QĐ-HV Mức thu học phí năm học 2025-2026",
        "category": "Học phí"
    },
    "hp_2026": {
        "pdf_file": "hp_2026.pdf",
        "md_file": "hp_2026.md",
        "title": "Quyết định 1462/QĐ-HV Mức thu học phí năm học 2026-2027",
        "category": "Học phí"
    },
    "mau-don-sinh-vien": {
        "pdf_file": "Mau-don-sinh-vien.pdf",
        "md_file": "Mau-don-sinh-vien.md",
        "title": "Tổng hợp Biểu mẫu Đơn từ Sinh viên PTIT",
        "category": "Biểu mẫu Sinh viên"
    },
    "mien_giam_hp": {
        "pdf_file": "mien_giam_hp.pdf",
        "md_file": "mien_giam_hp.md",
        "title": "Thông báo Chính sách Miễn giảm học phí & Hỗ trợ chi phí học tập",
        "category": "Chính sách & Học phí"
    },
    "mien_hoc_thi": {
        "pdf_file": "mien_hoc_thi.pdf",
        "md_file": "mien_hoc_thi.md",
        "title": "Thông báo Xét miễn học, miễn thi & Chuyển đổi điểm tiếng Anh",
        "category": "Quy chế Đào tạo"
    },
    "mon_hoc": {
        "pdf_file": "mon_hoc.pdf",
        "md_file": "mon_hoc.md",
        "title": "Khung Chương trình đào tạo & Danh mục Học phần ngành CNTT",
        "category": "Chương trình Đào tạo"
    },
    "so_tay": {
        "pdf_file": "so_tay.pdf",
        "md_file": "so_tay.md",
        "title": "Sổ tay Sinh viên Học viện Công nghệ Bưu chính Viễn thông",
        "category": "Sổ tay & Quy chế"
    },
    "ts_thac_si": {
        "pdf_file": "ts_thac_si.pdf",
        "md_file": "ts_thac_si.md",
        "title": "Thông báo Tuyển sinh trình độ Thạc sĩ năm 2026",
        "category": "Tuyển sinh"
    },
}


def resolve_doc_display_info(raw_filename, is_user_doc=False):
    """Chuẩn hóa tên file trích dẫn (.md -> .pdf) kèm tên văn bản hiển thị chuẩn Mẫu 1."""
    if not raw_filename:
        return {
            "file": "Tai_lieu_PTIT.pdf",
            "md_file": None,
            "title": "Tài liệu Học viện PTIT",
            "is_user_doc": is_user_doc
        }
    clean_name = os.path.basename(str(raw_filename).strip())
    stem = os.path.splitext(clean_name)[0].lower()
    if not is_user_doc and stem in PTIT_DOC_METADATA:
        meta = PTIT_DOC_METADATA[stem]
        return {
            "file": meta["pdf_file"],
            "md_file": meta["md_file"],
            "title": meta["title"],
            "is_user_doc": False
        }
    if is_user_doc:
        return {
            "file": clean_name,
            "md_file": None,
            "title": "Tài liệu người dùng tải lên",
            "is_user_doc": True
        }
    # Trường hợp file PTIT mới chưa khai báo cứng trong từ điển
    pdf_guess = f"{os.path.splitext(clean_name)[0]}.pdf" if clean_name.lower().endswith(".md") else clean_name
    return {
        "file": pdf_guess,
        "md_file": f"{os.path.splitext(clean_name)[0]}.md",
        "title": f"Tài liệu Học viện ({pdf_guess})",
        "is_user_doc": False
    }

# ==============================================================================
# TỐI ƯU 2: HTTP KEEP-ALIVE SESSION & QUẢN LÝ MODEL THÔNG MINH (STICKY MODEL)
# ==============================================================================
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")

# Tái sử dụng kết nối TCP/SSL giúp giảm 150ms - 300ms độ trễ mỗi lần gọi Gemini API
_HTTP_SESSION = requests.Session()
_http_adapter = HTTPAdapter(pool_connections=20, pool_maxsize=30, max_retries=1)
_HTTP_SESSION.mount("https://", _http_adapter)
_HTTP_SESSION.mount("http://", _http_adapter)

# Danh sách 3 model chính thức trên Google Generative Language API
FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
]

# Không sử dụng alias - gọi trực tiếp chính xác tên model Google API
MODEL_ALIAS_MAP = {}

# Ghi nhớ các model bị 404 (loại bỏ vĩnh viễn), model bị 429 (tạm nghỉ 60s), model không hỗ trợ thinkingConfig + Sticky Model
_dead_models_404 = set()
_cooldown_models_429 = {}
_no_thinking_config_models = set()
_sticky_working_model = None

# ==============================================================================
# TỐI ƯU 3 & 5: BỘ NHỚ ĐỆM DỮ LIỆU MARKDOWN TRONG RAM & CACHE CÂU TRẢ LỜI (LRU)
# ==============================================================================
_RAM_DOCS_MTIME = 0.0
_RAM_PARSED_PAGES = []        # Danh sách các trang đã tách sẵn + chữ thường (p_lower) phục vụ tìm kiếm < 2ms
_RAM_PAGE_LOOKUP = {}         # {(source_file, page_num): p_body}
_RAM_FULL_DOC_LOOKUP = {}     # {source_file: full_content}
_RESPONSE_CACHE = {}          # {(norm_q, scope, files_sig): {"answer": ..., "model_used": ..., "referenced_files": ...}}
_SESSION_FILES_CACHE = {}     # {session_id: [file_info, ...]} tránh gọi ChromaDB lặp lại mỗi câu hỏi
MAX_RESPONSE_CACHE_SIZE = 300

# Kết nối ChromaDB
_cached_chroma_client = None
_cached_collection = None


def get_vector_db(chroma_dir=CHROMA_DIR):
    """Khởi tạo và cache kết nối tới ChromaDB (ưu tiên collection httm_knowledge_base có sẵn 594 chunks)."""
    global _cached_chroma_client, _cached_collection
    if _cached_collection is not None:
        return _cached_collection
    import chromadb
    os.makedirs(chroma_dir, exist_ok=True)
    _cached_chroma_client = chromadb.PersistentClient(path=chroma_dir)
    try:
        coll_httm = _cached_chroma_client.get_or_create_collection(
            name="httm_knowledge_base",
            metadata={"hnsw:space": "cosine"}
        )
        if coll_httm.count() > 0:
            _cached_collection = coll_httm
            return _cached_collection
    except Exception:
        pass
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


def _find_extracted_json_path(session_dir, fname):
    """Trả về đường dẫn file _extracted.json theo tên file đầy đủ (tránh trùng khi 2 file cùng tên khác đuôi)."""
    full_json = os.path.join(session_dir, f"{fname}_extracted.json")
    if os.path.exists(full_json):
        return full_json
    legacy_json = os.path.join(session_dir, f"{os.path.splitext(fname)[0]}_extracted.json")
    if os.path.exists(legacy_json):
        return legacy_json
    return full_json


def get_session_uploaded_files(session_id, force_refresh=False):
    """
    Lấy danh sách các file duy nhất đã tải lên trong phiên (có cache RAM < 0.01ms).
    Nếu phiên chưa từng tạo thư mục user_uploads/{session_id}, trả về [] ngay lập tức mà không cần truy vấn SQLite ChromaDB.
    """
    if not session_id:
        return []
    if not force_refresh and session_id in _SESSION_FILES_CACHE:
        return _SESSION_FILES_CACHE[session_id]

    session_dir = os.path.join(USER_UPLOADS_DIR, session_id)
    if not os.path.exists(session_dir):
        _SESSION_FILES_CACHE[session_id] = []
        return []

    try:
        files_map = {}
        for item in os.listdir(session_dir):
            if item.endswith("_extracted.json"):
                continue
            fpath = os.path.join(session_dir, item)
            if os.path.isfile(fpath) and item not in files_map:
                chunks_count = 1
                ext_json = _find_extracted_json_path(session_dir, item)
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

        if not files_map:
            coll = get_user_vector_db()
            res = coll.get(where={"session_id": session_id}, include=["metadatas"])
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

        res_list = list(files_map.values())
        _SESSION_FILES_CACHE[session_id] = res_list
        return res_list
    except Exception as e:
        print(f"[!] Error getting session files: {e}")
        return []


def get_session_intro_chunks(session_id):
    """Lấy chunk mở đầu (Trang 1 / chunk_index=0) của từng file tải lên để luôn có tiêu đề và chủ đề."""
    if not session_id:
        return []
    try:
        coll = get_user_vector_db()
        ensure_session_in_chromadb(session_id, coll=coll)
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
                        "source_type": "user_doc",
                        "is_direct_match": False
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

GENERIC_PTIT_WORDS = VI_STOPWORDS | {
    "sinh", "viên", "học", "viện", "ptit", "trường", "tập", "điều", "kiện",
    "tiêu", "chuẩn", "quy", "định", "xét", "cấp", "thông", "tin", "biết",
    "hỏi", "xin", "công", "nghệ", "bưu", "chính", "viễn", "phòng", "ban",
    "liên", "hệ", "nhà", "báo", "cụ", "thể", "chi", "tiết", "hiện", "nay"
}


def normalize_academic_query(text):
    """
    Chuẩn hóa các từ viết tắt hoặc lỗi nhận diện giọng nói (STT) phổ biến của sinh viên PTIT:
    - 'gba', 'g p a', 'ji pi ay' -> 'GPA'
    - 'pê tít', 'pờ tít' -> 'PTIT'
    """
    if not text:
        return ""
    s = text.strip()
    s = re.sub(r"\b(?:gba|g\.p\.a|g\s+p\s+a|ji\s*pi\s*ay)\b", "GPA", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(?:pê\s*tít|pê\s*tit|pờ\s*tít)\b", "PTIT", s, flags=re.IGNORECASE)
    return s


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
                    d_val = float(dist)
                    sim_score = max(15.0, (1.0 - d_val) * 120.0) + max(0, (n_results * 2 - rank_idx) * 5)
                    matched.append({
                        "content": doc,
                        "filename": meta.get("filename", "Tài liệu người dùng"),
                        "page": meta.get("page", 1),
                        "chunk_index": meta.get("chunk_index", 0),
                        "source_type": "user_doc",
                        "score": sim_score,
                        "is_direct_match": d_val <= 0.42
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
        is_strong_kw = kw_item.get("score", 0) >= 35
        if key in combined_map:
            combined_map[key]["score"] = combined_map[key].get("score", 0) + kw_item.get("score", 0) + 60
            if is_strong_kw:
                combined_map[key]["is_direct_match"] = True
        else:
            kw_copy = dict(kw_item)
            kw_copy["is_direct_match"] = is_strong_kw
            combined_map[key] = kw_copy

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
# GỌI REST API & STREAMING GEMINI (HTTP KEEP-ALIVE + STICKY MODEL SIÊU TỐC)
# ==============================================================================

def _resolve_and_order_models(preferred_model=None):
    """
    Trả về danh sách model khả dụng theo thứ tự ưu tiên tốc độ cao nhất:
    - Tự động ánh xạ các tên model ảo sang model thật (tránh lỗi 404 làm mất 0.5-1.5s).
    - Ưu tiên Sticky Model vừa phản hồi thành công gần nhất.
    - Bỏ qua các model đã xác nhận 404 hoặc đang trong thời gian chờ 429 cooldown.
    """
    global _sticky_working_model
    now = time.time()
    candidates = []

    if preferred_model and preferred_model.strip():
        raw_pref = preferred_model.replace("models/", "").strip()
        mapped_pref = MODEL_ALIAS_MAP.get(raw_pref, raw_pref)
        candidates.append(mapped_pref)
        if raw_pref != mapped_pref and raw_pref not in _dead_models_404:
            candidates.append(raw_pref)

    if _sticky_working_model and _sticky_working_model not in candidates:
        candidates.insert(0 if not preferred_model else 1, _sticky_working_model)

    for m in FALLBACK_MODELS:
        if m not in candidates:
            candidates.append(m)

    filtered = []
    for m in candidates:
        if m in _dead_models_404:
            continue
        cooldown_until = _cooldown_models_429.get(m, 0.0)
        if now < cooldown_until:
            continue
        filtered.append(m)

    return filtered if filtered else ["gemini-3.5-flash-lite", "gemini-3.6-flash"]


def _build_gemini_payload(prompt, clean_model):
    """Tạo payload tối ưu tốc độ (tắt hoặc giảm suy nghĩ ngầm để phản hồi tức thì)."""
    gen_cfg = {
        "temperature": 0.1,
        "maxOutputTokens": 1800
    }
    if clean_model not in _no_thinking_config_models:
        if "3.8" in clean_model:
            gen_cfg["thinkingConfig"] = {"thinkingLevel": "low"}
        else:
            gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_cfg
    }


def call_gemini_rest_api(prompt, model_name, api_key=API_KEY, timeout=8.5):
    """Gọi trực tiếp Google Gemini REST API qua kết nối Keep-Alive với timeout ngắn."""
    global _sticky_working_model
    clean_model = model_name.replace("models/", "").strip()
    clean_key = api_key.strip() if api_key else API_KEY
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={clean_key}"

    payload = _build_gemini_payload(prompt, clean_model)
    headers = {"Content-Type": "application/json"}
    try:
        resp = _HTTP_SESSION.post(url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code == 400 and "thinkingConfig" in payload.get("generationConfig", {}):
            # Ghi nhớ model không hỗ trợ thinkingConfig để không bao giờ lặp lại lỗi 400 ở các câu sau
            _no_thinking_config_models.add(clean_model)
            payload["generationConfig"].pop("thinkingConfig", None)
            resp = _HTTP_SESSION.post(url, json=payload, headers=headers, timeout=timeout)

        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                text_parts = [p.get("text", "") for p in parts if "text" in p and not p.get("thought")]
                full_txt = "".join(text_parts).strip()
                if full_txt:
                    _sticky_working_model = clean_model
                    return full_txt, None
            return None, "Empty response from Gemini API"
        elif resp.status_code == 404:
            _dead_models_404.add(clean_model)
            return None, f"HTTP 404 (Model not found: {clean_model})"
        elif resp.status_code == 429:
            _cooldown_models_429[clean_model] = time.time() + 60.0
            return None, f"HTTP 429 (Quota exceeded on {clean_model})"
        else:
            return None, f"HTTP {resp.status_code}: {resp.text[:120]}"
    except requests.exceptions.Timeout:
        _cooldown_models_429[clean_model] = time.time() + 30.0
        return None, f"Timeout after {timeout}s on {clean_model}"
    except Exception as e:
        return None, str(e)


def stream_gemini_rest_api(prompt, model_name, api_key=API_KEY, timeout=8.5):
    """
    Gọi Gemini Streaming API (SSE) qua kết nối Keep-Alive với chunk_size=64 (không đệm).
    Yield từng đoạn văn bản (chunk) ngay khi token đầu tiên xuất hiện (~0.5s - 0.9s).
    """
    global _sticky_working_model
    clean_model = model_name.replace("models/", "").strip()
    clean_key = api_key.strip() if api_key else API_KEY
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:streamGenerateContent?alt=sse&key={clean_key}"

    payload = _build_gemini_payload(prompt, clean_model)
    headers = {"Content-Type": "application/json"}

    resp = _HTTP_SESSION.post(url, json=payload, headers=headers, timeout=timeout, stream=True)
    if resp.status_code == 400 and "thinkingConfig" in payload.get("generationConfig", {}):
        resp.close()
        _no_thinking_config_models.add(clean_model)
        payload["generationConfig"].pop("thinkingConfig", None)
        resp = _HTTP_SESSION.post(url, json=payload, headers=headers, timeout=timeout, stream=True)

    if resp.status_code == 404:
        resp.close()
        _dead_models_404.add(clean_model)
        raise RuntimeError(f"HTTP 404 ({clean_model})")
    if resp.status_code == 429:
        resp.close()
        _cooldown_models_429[clean_model] = time.time() + 60.0
        raise RuntimeError(f"HTTP 429 ({clean_model})")
    if resp.status_code != 200:
        err_body = resp.text[:120]
        resp.close()
        raise RuntimeError(f"HTTP {resp.status_code}: {err_body}")

    _sticky_working_model = clean_model
    resp.encoding = "utf-8"
    try:
        for line in resp.iter_lines(chunk_size=64, decode_unicode=True):
            if not line:
                continue
            if line.startswith("data:"):
                json_str = line[5:].strip()
                if not json_str or json_str == "[DONE]":
                    continue
                try:
                    chunk_obj = json.loads(json_str)
                    candidates = chunk_obj.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        for p in parts:
                            if "text" in p and not p.get("thought"):
                                yield p["text"]
                except Exception:
                    continue
    finally:
        resp.close()


def get_embedding_rest(text, api_key=API_KEY, timeout=2.5):
    """Tạo vector embedding cho câu hỏi qua REST API Keep-Alive (có bộ nhớ đệm LRU trong RAM)."""
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
        resp = _HTTP_SESSION.post(url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if "embedding" in data and "values" in data["embedding"]:
                vec = data["embedding"]["values"]
                if len(_query_embedding_cache) >= 512:
                    _query_embedding_cache.pop(next(iter(_query_embedding_cache)))
                _query_embedding_cache[norm_text] = vec
                return vec
    except Exception:
        pass
    return None


# ==============================================================================
# TỐI ƯU 3 & 4: CHỈ MỤC RAM (< 3ms) & HYBRID FAST-PATH RETRIEVAL
# ==============================================================================

def ensure_processed_docs_in_ram(processed_dir=PROCESSED_DIR):
    """
    Nạp và tách trang toàn bộ các file .md trong processed_data vào RAM một lần duy nhất,
    kèm tập hợp từ vựng (word_set) cho từng trang để lọc nhanh O(1) (< 3ms).
    """
    global _RAM_DOCS_MTIME, _RAM_PARSED_PAGES, _RAM_PAGE_LOOKUP, _RAM_FULL_DOC_LOOKUP
    if not os.path.exists(processed_dir):
        return

    try:
        dir_mtime = os.path.getmtime(processed_dir)
    except Exception:
        dir_mtime = 1.0

    if _RAM_PARSED_PAGES and dir_mtime == _RAM_DOCS_MTIME:
        return

    parsed_pages = []
    page_lookup = {}
    full_doc_lookup = {}

    for fname in sorted(os.listdir(processed_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(processed_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        full_doc_lookup[fname] = content.strip()
        fname_lower = fname.lower()
        pages = re.split(r"^## Trang (\d+) - \[([^\]]+)\]", content, flags=re.MULTILINE)
        if len(pages) > 1:
            for i in range(1, len(pages), 3):
                p_num = int(pages[i])
                p_type = pages[i + 1]
                p_body = pages[i + 2].strip() if i + 2 < len(pages) else ""
                p_lower = p_body.lower()
                page_lookup[(fname, p_num)] = p_body

                is_preamble = (p_num in [1, 2]) or any(
                    k in p_lower for k in ["căn cứ quyết định", "căn cứ nghị định", "điều 1. ban hành", "nơi nhận:"]
                )
                is_table_page = (p_type == "SCAN_TABLE") or (
                    "|" in p_body and any(k in p_lower for k in ["mức thu", "đồng/tín chỉ", "đvt"])
                )
                is_form_page = ("cộng hòa xã hội" in p_lower or "cộng hoà xã hội" in p_lower) and (
                    "kính gửi" in p_lower or "kính đề nghị" in p_lower
                )

                parsed_pages.append({
                    "fname": fname,
                    "fname_lower": fname_lower,
                    "p_num": p_num,
                    "p_type": p_type,
                    "p_body": p_body,
                    "p_lower": p_lower,
                    "word_set": set(re.findall(r"\w+", p_lower)),
                    "is_preamble": is_preamble,
                    "is_table_page": is_table_page,
                    "is_form_page": is_form_page,
                })

    _RAM_PARSED_PAGES = parsed_pages
    _RAM_PAGE_LOOKUP = page_lookup
    _RAM_FULL_DOC_LOOKUP = full_doc_lookup
    _RAM_DOCS_MTIME = dir_mtime


def get_parent_document_page(source_file, page_num, processed_dir=PROCESSED_DIR):
    """Lấy toàn bộ nội dung của trang tương ứng từ bộ nhớ RAM (< 0.01ms)."""
    if not source_file:
        return ""
    ensure_processed_docs_in_ram(processed_dir)
    if page_num and (source_file, int(page_num)) in _RAM_PAGE_LOOKUP:
        return _RAM_PAGE_LOOKUP[(source_file, int(page_num))]
    return _RAM_FULL_DOC_LOOKUP.get(source_file, "")


def keyword_search_all(query, processed_dir=PROCESSED_DIR, top_k=3):
    """Tìm kiếm chính xác và theo từ khóa trực tiếp trên chỉ mục RAM với bộ lọc word_set (< 3ms)."""
    ensure_processed_docs_in_ram(processed_dir)
    if not _RAM_PARSED_PAGES:
        return []

    q_norm = normalize_academic_query(query)
    q_lower = q_norm.lower().strip()
    raw_words = [w for w in re.findall(r"\w+", q_lower) if len(w) > 1]
    if not raw_words:
        return []
    q_words = [w for w in raw_words if w not in VI_STOPWORDS] or raw_words
    q_word_set = set(q_words)

    is_form_q = any(k in q_lower for k in ["mẫu đơn", "mau don", "đơn xin", "don xin", "đơn đề nghị", "biểu mẫu", "vắng thi", "nghỉ học", "thôi học", "phúc khảo", "hoãn thi"])
    is_doi_diem_q = any(k in q_lower for k in ["quy đổi", "quy doi", "đổi điểm", "doi diem", "chuyển điểm", "ielts", "toefl", "toeic", "aptis", "chuẩn đầu ra tiếng anh"])
    is_gv_q = any(k in q_lower for k in ["giảng viên", "giang vien", "thầy", "cô", "pgs", "tiến sĩ"])
    is_hp_q = any(k in q_lower for k in ["học phí", "hoc phi", "mức thu"])
    has_gpa_kw = any(k in q_lower for k in ["gpa", "gba", "tbcmr", "điểm trung bình", "diem trung binh", "điểm tbc", "tbcht"])
    has_drl_kw = any(k in q_lower for k in ["rèn luyện", "ren luyen", "đrl", "drl"])
    has_hb_level_kw = any(k in q_lower for k in ["loại xuất sắc", "loại giỏi", "loại khá", "học bổng xuất sắc", "học bổng giỏi", "học bổng khá"])
    is_the_sv_q = any(k in q_lower for k in ["thẻ sinh viên", "the sinh vien", "mất thẻ", "đeo thẻ", "làm lại thẻ", "cấp lại thẻ"])
    is_hb_q = (
        any(k in q_lower for k in ["học bổng", "hoc bong", "khuyến khích", "hb kkht", "tbcmr"])
        or has_hb_level_kw
        or (has_gpa_kw and has_drl_kw)
        or (has_gpa_kw and any(k in q_lower for k in ["điều kiện", "tiêu chuẩn", "xét", "bao nhiêu", "như thế nào", "thì được", "cần"]))
        or (has_drl_kw and not is_the_sv_q and any(k in q_lower for k in ["điều kiện", "tiêu chuẩn", "xét", "bao nhiêu", "như thế nào", "thì được", "loại", "đạt"]))
    )
    is_ktx_q = any(k in q_lower for k in ["ký túc xá", "kí túc xá", "ktx", "sơ đồ", "mặt bằng", "khuôn viên", "nhà a1", "nhà a2", "nhà a3", "nhà b2", "b2"])
    is_ctdt_q = any(k in q_lower for k in ["chương trình đào tạo", "khối lượng", "tốt nghiệp", "môn học", "học phần", "tín chỉ", "tiên quyết", "chuyên ngành", "int1"])
    is_sotay_q = any(k in q_lower for k in ["quy chế", "sổ tay", "học lại", "cải thiện", "cảnh báo", "buộc thôi học", "rèn luyện", "điểm chữ", "hệ 4"])
    is_clb_q = any(k in q_lower for k in ["câu lạc bộ", "clb", "đoàn", "hội sinh viên"])
    is_miengiam_q = any(k in q_lower for k in ["miễn giảm", "trợ cấp", "hộ nghèo", "chính sách"])
    is_mien_hoc_thi_q = any(k in q_lower for k in ["miễn học", "miễn thi", "chuyển điểm tiếng anh"])
    is_thac_si_q = any(k in q_lower for k in ["thạc sĩ", "cao học", "sau đại học", "tuyển sinh thạc sĩ"])

    cohort_matches = re.findall(r"(?:kh[oó]a\s*|k)(\d{2,4})|\b(202[0-9])\b", q_lower)
    target_cohorts = []
    for cm in cohort_matches:
        c_val = cm[0] or cm[1]
        if c_val:
            target_cohorts.append("20" + c_val if len(c_val) == 2 else c_val)

    has_2026 = "2026" in q_lower
    has_2025 = "2025" in q_lower
    is_cntt_q = any(m in q_lower for m in ["cntt", "công nghệ thông tin", "an toàn thông tin", "máy tính"])

    # Tiền tính toán danh sách cụm từ con (subphrases) 1 lần ngoài vòng lặp.
    # Cụm từ chứa từ khóa đặc trưng (không thuộc từ phổ thông GENERIC_PTIT_WORDS) được trọng số cao gấp 7 lần.
    subphrases = []
    max_l = min(len(raw_words), 5)
    for l in range(max_l, 1, -1):
        for start in range(len(raw_words) - l + 1):
            chunk_words = raw_words[start:start + l]
            has_distinctive = any(cw not in GENERIC_PTIT_WORDS for cw in chunk_words)
            sp_weight = (40 * l) if has_distinctive else (5 * l)
            subphrases.append((" ".join(chunk_words), sp_weight))

    results = []
    for item in _RAM_PARSED_PAGES:
        matched_words = q_word_set & item["word_set"]
        fname_lower = item["fname_lower"]
        p_num = item["p_num"]

        is_special_doc = (
            (is_hp_q and "hp_" in fname_lower)
            or (is_hb_q and ("hb_" in fname_lower or ("so_tay" in fname_lower and p_num == 39)))
            or (is_doi_diem_q and "doi_diem" in fname_lower)
            or (is_gv_q and "giang_vien" in fname_lower)
            or (is_clb_q and "clb" in fname_lower)
            or (is_miengiam_q and "mien_giam" in fname_lower)
            or (is_mien_hoc_thi_q and "mien_hoc_thi" in fname_lower)
            or (is_thac_si_q and "ts_thac_si" in fname_lower)
            or (is_ktx_q and "so_tay" in fname_lower and p_num == 9)
        )

        # Bỏ qua ngay lập tức (O(1)) nếu trang không chứa bất kỳ từ khóa nào và không thuộc nhóm trang đặc biệt
        if not matched_words and not is_special_doc:
            continue

        p_lower = item["p_lower"]
        fname = item["fname"]

        score = 0
        # 1. Khớp cụm từ chính xác
        if q_lower in p_lower:
            score += 150
        elif len(matched_words) >= 2:
            for sp, sp_weight in subphrases:
                if sp in p_lower:
                    score += sp_weight

        # 2. Khớp từ khóa đơn (giới hạn tối đa 5 lần/từ trên 1 trang để các từ phổ thông "sinh", "viên", "học" không làm nhiễu điểm)
        for w in matched_words:
            cnt = min(p_lower.count(w), 5)
            score += cnt * (2 if w in GENERIC_PTIT_WORDS else 10)

        # 3. Ưu tiên theo tài liệu chuyên biệt
        if is_form_q and item["is_form_page"]:
            score += 220
        elif is_form_q and "so_tay" in fname_lower:
            score = score * 0.1

        if is_doi_diem_q and "doi_diem" in fname_lower:
            score += 280
        if is_gv_q and "giang_vien" in fname_lower:
            score += 250
        if is_hb_q:
            if "hb_" in fname_lower:
                score += 380
                if p_num == 1:
                    score += 80
                for tc in target_cohorts:
                    if tc in p_lower:
                        score += 120
                if any(k in q_lower for k in ["clc", "chất lượng cao", "báo chí", "khmt", "khoa học máy tính", "iot", "điều khiển", "tài chính"]) and p_num == 3:
                    score += 180
                if any(k in q_lower for k in ["game", "vi mạch", "bán dẫn", "trí tuệ nhân tạo", "quan hệ công chúng", "logistic", "nhật"]) and p_num == 4:
                    score += 180
                if any(k in q_lower for k in ["attt", "an toàn thông tin", "qtkd", "quản trị", "kế toán", "marketing", "tmđt", "thương mại điện tử", "truyền thông"]) and p_num == 2:
                    score += 180
            elif "so_tay" in fname_lower:
                if "học bổng" in p_lower:
                    score += 435
                else:
                    score = score * 0.12
            elif "mien_giam" in fname_lower and "học bổng" in p_lower:
                score += 140

        # Giảm trọng số các trang sổ ghi chép trống ở cuối Sổ tay sinh viên (Trang 70-76) và trang Thẻ sinh viên (Trang 43-44) khi không hỏi về thẻ
        if "so_tay" in fname_lower:
            if p_num >= 70:
                score = score * 0.02
            elif p_num in (43, 44) and not is_the_sv_q:
                score = score * 0.15

        if is_ctdt_q and ("ct_cntt" in fname_lower or "mon_hoc" in fname_lower):
            score += 110
        if is_sotay_q and "so_tay" in fname_lower and not is_hb_q:
            score += 90
        if is_clb_q and "clb" in fname_lower:
            score += 220
        if is_miengiam_q and "mien_giam" in fname_lower:
            score += 220
        if is_mien_hoc_thi_q and "mien_hoc_thi" in fname_lower:
            score += 250
        if is_thac_si_q and "ts_thac_si" in fname_lower:
            score += 250

        # Xử lý tìm kiếm học phí chính xác
        if is_hp_q and "hp_" in fname_lower:
            if has_2026 and "2026" in fname_lower:
                score += 250
            if has_2025 and "2025" in fname_lower:
                score += 250
            if not has_2026 and not has_2025:
                score += 150

            if item["is_table_page"]:
                score += 250
                for tc in target_cohorts:
                    if f"khóa {tc}" in p_lower or f"khoá {tc}" in p_lower or tc in p_lower:
                        score += 200
                if is_cntt_q and "công nghệ thông tin" in p_lower:
                    score += 150
            elif item["is_preamble"]:
                score = score * 0.05

        if is_ktx_q and "so_tay" in fname_lower and p_num == 9:
            score += 250

        if score > 0:
            results.append({
                "content": item["p_body"],
                "source": fname,
                "page": p_num,
                "type": item["p_type"],
                "score": score
            })

    results.sort(key=lambda x: x["score"], reverse=True)

    # Nếu là câu hỏi so sánh giữa 2 năm (2025 và 2026), đảm bảo lấy cân bằng tài liệu của cả 2 năm
    if is_hp_q and has_2025 and has_2026:
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
    """
    Truy vấn kết hợp Hybrid Search (Keyword RAM < 3ms + Vector Search) và Context Trimming:
    - Fast-Path: Nếu Keyword Search trên RAM đạt độ khớp tốt (score >= 85), bỏ qua bước gọi
      mạng Embedding API (tiết kiệm 400ms - 600ms) trừ khi vector đã có sẵn trong RAM cache.
    - Context Trimming: Chỉ mở rộng toàn bộ trang cha cho Top 2 kết quả chính (hoặc 4 khi so sánh 2 năm),
      các kết quả phụ được giữ gọn để giảm ~45% token đầu vào cho LLM.
    """
    active_key = custom_api_key.strip() if (custom_api_key and custom_api_key.strip()) else API_KEY

    # 1. Chạy Keyword Search trên RAM trước (< 3ms)
    keyword_hits = keyword_search_all(query, top_k=n_results)
    top_kw_score = keyword_hits[0]["score"] if keyword_hits else 0

    matched_chunks = []
    norm_q = (query or "").strip()
    cached_vec = query_embedding or _query_embedding_cache.get(norm_q)

    # 2. Chỉ gọi mạng Embedding API nếu chưa đạt ngưỡng Fast-Path (score < 85) hoặc đã có sẵn vector trong cache
    if cached_vec or top_kw_score < 85:
        try:
            q_vec = cached_vec or get_embedding_rest(query, active_key, timeout=2.5)
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

    combined = keyword_hits + matched_chunks
    q_lower = (query or "").lower()
    is_compare_years = ("2025" in q_lower and "2026" in q_lower)
    max_full_pages = 4 if is_compare_years else 2

    expanded = []
    seen = set()
    for c in combined:
        src = c.get("source")
        p = c.get("page")
        key = (src, p)
        if key in seen:
            continue
        seen.add(key)

        if len(expanded) < max_full_pages:
            parent = get_parent_document_page(src, p)
            body = parent if parent else c.get("content", "")
        else:
            raw_body = c.get("content", "") or get_parent_document_page(src, p)
            body = raw_body[:1600] if len(raw_body) > 1600 else raw_body

        expanded.append({
            "source": src,
            "page": p,
            "type": c.get("type", "page"),
            "content": body
        })
        if len(expanded) >= max(n_results, 3):
            break

    return expanded


# ==============================================================================
# SINH CÂU TRẢ LỜI QUA LLM (GEMINI PROMPT CHUẨN XÁC & HỖ TRỢ STREAMING SSE)
# ==============================================================================

def build_rag_prompt(question, context_str, history=None, has_user_docs=False, user_files=None, scope="hybrid"):
    """Xây dựng prompt hệ thống chuẩn xác cho cả chế độ thường và chế độ Streaming."""
    history_prompt = ""
    if history and isinstance(history, list) and len(history) > 0:
        h_lines = []
        for h in history[-4:]:
            role = "Người dùng" if h.get("role") == "user" else "Trợ lý PTIT"
            cnt = h.get("content", "").strip()
            if cnt:
                h_lines.append(f"{role}: {cnt[:500]}")
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
     -> Sau đó, hãy đối chiếu môn học/chủ đề đó với Cơ sở dữ liệu PTIT (nếu có) để trả lời chi tiết: Môn học này có trong chương trình đào tạo của PTIT không, thuộc ngành nào (ví dụ ngành Công nghệ Thông tin, chuyên ngành Mạng máy tính và truyền thông dữ liệu...), mã học phần là gì, số tín chỉ, học kỳ, môn tiên quyết nếu có.
   - ĐỐI VỚI TÀI LIỆU NGƯỜI DÙNG TẢI LÊN: Bạn ĐƯỢC PHÉP nêu rõ tên file ({files_list_str}) và số trang trong file của người dùng khi trích dẫn hoặc khi người dùng hỏi vị trí thông tin.
   - Khi câu hỏi liên quan đến tài liệu tải lên, hãy mở đầu rõ ràng: "Dựa trên tài liệu **{files_list_str}** bạn đã tải lên...". Nếu câu hỏi thuần túy hỏi về thông tin chung của PTIT (như học phí, ký túc xá, quy chế) và không liên quan đến tài liệu tải lên, hãy trả lời thẳng vào thông tin PTIT mà không cần nhắc tới tài liệu tải lên.
   - Nếu có sự khác biệt hoặc mâu thuẫn giữa thông tin trong file người dùng tải lên và quy định chính thức của PTIT, hãy chỉ ra điểm khác biệt đó một cách khách quan.
"""

    if scope == "user_only":
        no_info_rule = "- Nếu tài liệu người dùng tải lên hoàn toàn KHÔNG có thông tin để trả lời câu hỏi này: Hãy thông báo rõ rằng các tài liệu bạn vừa tải lên hiện chưa đề cập đến nội dung này (gợi ý người dùng chuyển Phạm vi tra cứu sang 'Kết hợp (Hybrid)' hoặc 'Chỉ PTIT' nếu muốn tra cứu quy chế Học viện)."
    else:
        no_info_rule = "- Nếu tài liệu hoàn toàn KHÔNG có thông tin để trả lời: Hãy thông báo lịch sự rằng tài liệu hiện có chưa có thông tin về vấn đề này. TUYỆT ĐỐI KHÔNG tự bịa đặt hay đưa nội dung của văn bản khác không liên quan."

    return f"""Bạn là Trợ lý Ảo AI chính thức của Học viện Công nghệ Bưu chính Viễn thông (PTIT).
Dưới đây là dữ liệu ngữ cảnh được trích xuất để phục vụ trả lời câu hỏi:

{context_str}

{history_prompt}CÂU HỎI CỦA NGƯỜI DÙNG: {question}

NGUYÊN TẮC BẮT BUỘC:
1. TRUNG THỰC & CHUẨN XÁC (QUAN TRỌNG NHẤT):
   - Trả lời đúng trọng tâm câu hỏi dựa vào tài liệu được cung cấp bên trên.
   - Khi hỏi về HỌC PHÍ của một khóa / ngành / năm học: Nêu rõ mức học phí (đồng/tín chỉ) của từng hệ đào tạo (Chương trình chuẩn/đại trà, Chất lượng cao, Cử nhân định hướng ứng dụng...) có trong tài liệu dưới dạng danh sách gạch đầu dòng chi tiết (- **Hệ đào tạo:** Mức phí đồng/tín chỉ). TUYỆT ĐỐI KHÔNG chép lại phần văn bản hành chính mở đầu (Căn cứ quyết định, Căn cứ nghị định...).
   - Khi hỏi về HỌC BỔNG KHUYẾN KHÍCH HỌC TẬP hoặc hỏi về ĐIỂM GPA / ĐIỂM TRUNG BÌNH (TBCMR) VÀ ĐIỂM RÈN LUYỆN (điều kiện, tiêu chuẩn xét cấp, điểm chuẩn, xếp loại học bổng hoặc mức tiền học bổng theo file HB_HK1_25-26.pdf và so_tay.pdf):
     + Kể cả khi người dùng chỉ hỏi ngắn gọn như "GPA và điểm rèn luyện như thế nào thì được", "loại giỏi cần điều kiện gì", hãy hiểu người dùng đang hỏi về tiêu chuẩn điểm GPA (Điểm TBCMR) và Điểm rèn luyện để xét cấp Học bổng khuyến khích học tập tại PTIT và trả lời đầy đủ!
     + Giải thích rõ 2 tiêu chí xét cấp bắt buộc tại PTIT (theo bảng kết quả xét cấp học bổng khuyến khích học tập HK1 năm học 2025-2026 - File `HB_HK1_25-26.pdf`): Sinh viên phải đạt đồng thời chuẩn **Điểm trung bình chung mở rộng (Điểm TBCMR / GPA - thang điểm 4)** và **Điểm rèn luyện (Điểm RL - thang điểm 100)** theo quy định của từng ngành, từng khóa tại cơ sở đào tạo Hà Nội (HN) hoặc TP. Hồ Chí Minh (HCM) trong phạm vi quỹ học bổng.
     + Nêu rõ tiêu chuẩn cụ thể của 3 mức học bổng trong bảng `HB_HK1_25-26.pdf`:
       * **Học bổng loại Xuất sắc:** Điểm rèn luyện (ĐRL) đạt từ **90 điểm trở lên** và Điểm TBCMR (GPA) đạt từ **3,60 trở lên** (một số ngành/khóa có mức điểm chuẩn TBCMR thực tế từ 3,60 đến 3,76).
       * **Học bổng loại Giỏi:** Điểm rèn luyện (ĐRL) đạt từ **80 điểm trở lên** (tùy ngành/khóa từ 80 đến 90 điểm) và Điểm TBCMR (GPA) đạt tối thiểu từ **3,20 trở lên** (điểm chuẩn thực tế dao động từ 3,20 đến 3,92 tùy ngành, khóa và cơ sở).
       * **Học bổng loại Khá:** Điểm rèn luyện (ĐRL) đạt từ **65 điểm trở lên** (tùy ngành/khóa từ 65 đến 88 điểm) và Điểm TBCMR (GPA) đạt tối thiểu từ **2,50 trở lên** (điểm chuẩn thực tế từ 2,50 đến 3,80 tại các ngành/khóa còn chỉ tiêu quỹ học bổng; nếu cột loại Khá ghi dấu `-` nghĩa là ngành/khóa đó đã xét hết chỉ tiêu quỹ học bổng ở mức Xuất sắc và Giỏi).
     + Nêu rõ quy định tại Điều 6 khoản 2.2 Sổ tay sinh viên (`so_tay.pdf` - Trang 39): Kết quả học cải thiện điểm chỉ dùng để tính điểm trung bình chung tích lũy, **không sử dụng để xét khen thưởng, học bổng**.
     + Nêu ví dụ mức tiền học bổng (đơn vị trong bảng là nghìn đồng, ví dụ 17.480 nghìn đồng = 17.480.000 đồng/học kỳ) hoặc lập bảng chi tiết nếu người dùng hỏi cụ thể một ngành/khóa.
   - Khi câu hỏi yêu cầu SO SÁNH (ví dụ so sánh học phí giữa các năm 2025 và 2026, hoặc so sánh giữa các khóa/hệ): Trình bày bảng so sánh Markdown trực quan, chi tiết từng hệ đào tạo/ngành qua các năm và phân tích mức chênh lệch cụ thể (tăng/giảm bao nhiêu).
   - Nếu tài liệu có thông tin: Trả lời ngắn gọn, đầy đủ, mạch lạc.
   - Nếu tài liệu chỉ có thông tin MỘT PHẦN (ví dụ: có vị trí tòa nhà KTX B2 trên sơ đồ nhưng không có bảng giá phòng hay điều kiện nội trú): Hãy nêu rõ những thông tin có trong tài liệu, và thông báo rõ phần thông tin chưa có trong tài liệu kèm hướng dẫn liên hệ phòng ban phụ trách (Phòng Chính trị & Công tác sinh viên tại Nhà A1, Ban quản lý KTX...).
   - NGUYÊN TẮC VỀ MÔN HỌC GIẢNG DẠY CỦA GIẢNG VIÊN:
     + Nếu câu hỏi hỏi cụ thể về "dạy môn gì", "dạy những môn nào", "các môn giảng dạy" của một Thầy/Cô:
     + Trong file `giang_vien.pdf` chỉ có thông tin chung về "Chuyên ngành giảng dạy" (ví dụ: Công nghệ thông tin), KHÔNG CÓ danh sách các môn học cụ thể.
     + Do đó, bạn BẮT BUỘC phải nêu rõ: "Hiện tại tài liệu nội bộ chỉ ghi nhận chuyên ngành giảng dạy chung là [Tên chuyên ngành] mà chưa liệt kê chi tiết tên từng môn học cụ thể do Thầy/Cô giảng dạy."
   - NGUYÊN TẮC VỀ TUYỂN SINH (ĐẠI HỌC CHÍNH QUY vs THẠC SĨ / SAU ĐẠI HỌC):
     + Khi người dùng hỏi về "tuyển sinh", "chỉ tiêu tuyển sinh", "điểm chuẩn", "phương thức xét tuyển", "thí sinh" mà KHÔNG nói rõ là "thạc sĩ", "sau đại học", "cao học", "tiến sĩ":
       * Mặc định hiểu là người dùng đang hỏi về TUYỂN SINH ĐẠI HỌC CHÍNH QUY.
       * File `ts_thac_si.pdf` (Thông báo Tuyển sinh trình độ Thạc sĩ) CHỈ dành riêng cho bậc Thạc sĩ (Sau đại học). TUYỆT ĐỐI KHÔNG dùng thông tin, chỉ tiêu, môn thi của Thạc sĩ để trả lời cho câu hỏi tuyển sinh đại học!
       * Nếu tài liệu nội bộ không có đề án tuyển sinh đại học chính quy: BẮT BUỘC thông báo rõ ràng rằng tài liệu nội bộ PTIT hiện chỉ có Thông báo tuyển sinh trình độ Thạc sĩ năm 2026, chưa ghi nhận thông tin về chỉ tiêu tuyển sinh Đại học chính quy (để hệ thống tự động kích hoạt tra cứu Internet).
   - NGUYÊN TẮC KIỂM TRA THỰC THỂ BẮT BUỘC (CHỐNG BỊA NGUỒN & CHỐNG DÙNG KIẾN THỨC NGOÀI TÀI LIỆU):
     + Nếu người dùng hỏi về một cá nhân/giảng viên cụ thể (ví dụ: "Hoàng Mạnh Cường"), một trang web/tên miền cụ thể (ví dụ: "it.ptit.edu.vn"), hoặc một đối tượng cụ thể mà tên đó HOÀN TOÀN KHÔNG XUẤT HIỆN trong dữ liệu ngữ cảnh ở trên:
       * TUYỆT ĐỐI KHÔNG tự suy diễn hoặc lấy kiến thức bên ngoài tài liệu để trả lời!
       * BẮT BUỘC trả lời rằng tài liệu hiện có chưa có thông tin về đối tượng/vấn đề này (để hệ thống tự động kích hoạt tìm kiếm Internet).
     + CẤM THAY THẾ ĐỐI TƯỢNG: Nếu người dùng hỏi về một cơ sở / địa điểm / tòa nhà / đơn vị cụ thể (vd: "cơ sở Ngọc Trục") mà tài liệu chỉ có thông tin của cơ sở/địa điểm KHÁC (vd: cơ sở Hà Đông, Trần Phú, Nguyễn Đình Chiểu): TUYỆT ĐỐI KHÔNG đem thông tin của đối tượng khác ra trả lời thay. BẮT BUỘC trả lời rằng tài liệu hiện có chưa có thông tin về đối tượng được hỏi.
   {no_info_rule}

2. ĐỊNH DẠNG TRÌNH BÀY:
   - THÔNG TIN ĐƠN LẺ (hỏi về 1 giảng viên cụ thể, 1 môn học cụ thể, 1 tòa nhà/địa điểm, 1 mức phí đơn lẻ...): Trình bày dưới dạng danh sách gạch đầu dòng chi tiết (- **Thuộc tính:** Giá trị). TUYỆT ĐỐI KHÔNG DÙNG BẢNG 1 DÒNG.
   - BẢNG BIỂU DỮ LIỆU HOẶC SO SÁNH (bảng quy đổi điểm tiếng Anh, so sánh học phí qua các năm, danh sách môn học, học bổng...): Trình bày dưới dạng bảng Markdown hoàn chỉnh, chuẩn xác, đẹp mắt.
   - BIỂU MẪU ĐƠN TỪ: Cung cấp đầy đủ nguyên văn biểu mẫu (Quốc hiệu tiêu ngữ, Kính gửi, nội dung sinh viên khai, lý do, cam đoan, phần chữ ký...).

3. VĂN PHONG:
   - Thân thiện, tôn trọng, khách quan.
   - TUYỆT ĐỐI KHÔNG dùng ký hiệu LaTeX toán học như $\\ge$, $\\le$ hay dấu $, hãy dùng tiếng Việt tự nhiên (>=, <=, "từ... trở lên").
   - Không ghi chú debug như `[SCAN_TABLE]` hay `[TEXT]` trong câu trả lời.
{user_docs_instruction}
5. MỤC TRÍCH DẪN NGUỒN TÀI LIỆU Ở CUỐI CÂU TRẢ LỜI (BẮT BUỘC):
   - Khi và CHỈ KHI câu trả lời thực sự lấy thông tin từ tài liệu ngữ cảnh ở trên, mới viết mục trích dẫn ở cuối cùng theo ĐÚNG định dạng Mẫu 1:
   📌 **Nguồn trích dẫn:**
   - 📄 Trang <số_trang> - File: <tên_file_gốc> (<Tên văn bản>)
   - Ví dụ chuẩn:
   📌 **Nguồn trích dẫn:**
   - 📄 Trang 3 - File: hp_2025.pdf (Quyết định 1120/QĐ-HV Mức thu học phí năm học 2025-2026)
   - Mỗi trang trích dẫn viết trên 1 dòng gạch đầu dòng riêng biệt. CHỈ liệt kê đúng trang và file thực sự chứa thông tin dùng để trả lời câu hỏi.
   - CẤM TUYỆT ĐỐI: Nếu tài liệu hoàn toàn không có thông tin hoặc không đề cập đến thực thể được hỏi thì TUYỆT ĐỐI KHÔNG ĐƯỢC viết mục '📌 Nguồn trích dẫn' và KHÔNG liệt kê bất kỳ file/trang nào."""


def build_web_rag_prompt(question: str, web_context: str, history=None, internal_info=None) -> str:
    """Prompt chuyên dụng khi trả lời từ kết quả tìm kiếm web (hỗ trợ cả trường hợp bổ sung thông tin thiếu)."""
    history_prompt = ""
    if history and isinstance(history, list) and len(history) > 0:
        h_lines = []
        for h in history[-3:]:
            role = "Người dùng" if h.get("role") == "user" else "Trợ lý"
            cnt = h.get("content", "").strip()
            if cnt:
                h_lines.append(f"{role}: {cnt[:400]}")
        if h_lines:
            history_prompt = "LỊCH SỬ HỘI THOẠI:\n" + "\n".join(h_lines) + "\n\n"

    internal_section = ""
    is_supplement = bool(internal_info and not _is_no_info_response(internal_info))
    if is_supplement:
        clean_internal = _strip_all_citations(internal_info)
        internal_section = f"""THÔNG TIN ĐÃ CÓ TỪ CƠ SỞ DỮ LIỆU NỘI BỘ PTIT:
{clean_internal}

"""

    if is_supplement:
        rule1 = """1. BẮT BUỘC kết hợp thông tin từ cơ sở dữ liệu nội bộ ở trên và thông tin chi tiết tìm thấy từ website chính thức của Học viện để trả lời trọn vẹn câu hỏi:
- Mở đầu bằng:
📌 **Theo cơ sở dữ liệu nội bộ và thông tin bổ sung từ Cổng thông tin PTIT (clc.ptit.edu.vn / it.ptit.edu.vn), thông tin như sau:**
- Trình bày rõ thông tin học vị/chức vụ/đơn vị công tác (nếu có từ tài liệu nội bộ).
- Cung cấp danh sách các môn học cụ thể do Thầy/Cô phụ trách giảng dạy được ghi nhận trên trang web của Học viện."""
    else:
        rule1 = """1. BẮT BUỘC mở đầu câu trả lời bằng thông báo rõ ràng cho người dùng theo đúng mẫu sau:
📌 **Tài liệu nội bộ PTIT hiện chưa ghi nhận thông tin về nội dung này.** Hệ thống đã tự động tra cứu bổ sung trên Internet để hỗ trợ bạn:
*(⚠️ Lưu ý: Thông tin dưới đây được tổng hợp từ Internet. Vui lòng xác minh lại nếu cần)*"""

    return f"""Bạn là Trợ lý Ảo AI của Học viện Công nghệ Bưu chính Viễn thông (Học viện BCVT).
{internal_section}KẾT QUẢ TÌM KIẾM TỪ INTERNET ĐỂ THAM KHẢO (CÁC TRANG WEB CHÍNH THỨC CỦA PTIT):

{web_context}

{history_prompt}CÂU HỎI CỦA NGƯỜI DÙNG: {question}

NGUYÊN TẮC BẮT BUỘC:
{rule1}

2. TẬP TRUNG CHÍNH XÁC VÀO THỰC THỂ ĐƯỢC HỎI:
   - Nếu câu hỏi về một cá nhân/giảng viên cụ thể: Chỉ trả lời đúng thông tin về người có tên khớp chính xác.
   - TUYỆT ĐỐI KHÔNG nhận nhầm sang người khác trùng họ hoặc trùng tên đệm.
   - Nếu kết quả tìm kiếm có người khớp chính xác, hãy trình bày rõ: Chức danh/Học vị, Khoa/Bộ môn, Email liên hệ, Môn học giảng dạy (nếu nguồn có ghi nhận).
   - Nếu kết quả tìm kiếm chưa nêu rõ môn học cụ thể, hãy nêu rõ rằng trang thông tin hiện tại chưa ghi chi tiết môn giảng dạy của thầy/cô.

3. KHÔNG tự bịa thêm thông tin ngoài những gì có trong kết quả tìm kiếm.
4. TUYỆT ĐỐI KHÔNG gắn mục "📌 Nguồn trích dẫn" kiểu tài liệu nội bộ — hệ thống sẽ tự động gắn link nguồn web ở phía dưới.
5. Trả lời bằng tiếng Việt, văn phong thân thiện, ngắn gọn, gạch đầu dòng rõ ràng.
6. KHÔNG sử dụng ký hiệu LaTeX toán học."""


def generate_llm_answer(question, context_str, custom_api_key=None, preferred_model=None, history=None, has_user_docs=False, user_files=None, scope="hybrid"):
    """Sinh câu trả lời thông minh qua Gemini LLM (Non-streaming)."""
    active_key = custom_api_key.strip() if (custom_api_key and custom_api_key.strip()) else API_KEY
    system_instruction = build_rag_prompt(question, context_str, history, has_user_docs, user_files, scope)
    models_to_try = _resolve_and_order_models(preferred_model)

    last_error = ""
    start_time = time.time()
    for model_name in models_to_try:
        if time.time() - start_time > 18.0:
            break
        ans, err = call_gemini_rest_api(
            prompt=system_instruction,
            model_name=model_name,
            api_key=active_key,
            timeout=8.5
        )
        if ans:
            return ans, model_name, None
        last_error = err

    return None, None, last_error


# ==============================================================================
# HẬU XỬ LÝ & BỘ LỌC AN TOÀN KHI MẤT KẾT NỐI (SAFE FALLBACK)
# ==============================================================================

def clean_llm_response(text):
    """Làm sạch văn bản trả lời, chuyển bảng 1 dòng sang gạch đầu dòng, sửa LaTeX."""
    if not text:
        return ""
    text = re.sub(r"\[[^\]]+\.md\s*\|\s*Trang\s*\d+[^\]]*\]", "", text, flags=re.IGNORECASE)
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


REFUSAL_PHRASES = [
    "chưa có thông tin",
    "không có thông tin",
    "chưa ghi nhận thông tin",
    "không ghi nhận thông tin",
    "chưa được ghi nhận",
    "không được ghi nhận",
    "chưa chứa đầy đủ thông tin",
    "không chứa đầy đủ thông tin",
    "chưa có đầy đủ thông tin",
    "không có đầy đủ thông tin",
    "chưa có đủ thông tin",
    "không có đủ thông tin",
    "hiện chưa tìm thấy thông tin",
    "không tìm thấy thông tin",
    "chưa tìm thấy thông tin",
    "chưa đề cập đến",
    "không đề cập đến",
    "chưa được đề cập",
    "không được đề cập",
    "không có dữ liệu",
    "chưa có dữ liệu",
    "chưa có đủ dữ liệu",
    "không có đủ dữ liệu",
    "chưa đủ dữ liệu",
    "không đủ dữ liệu",
    "nằm ngoài phạm vi",
    "chưa được cung cấp trong",
    "không tìm thấy dữ liệu",
    "không nằm trong danh sách",
    "không xuất hiện trong danh sách",
    "chưa cập nhật thông tin"
]

REFUSAL_REGEX_PATTERNS = [
    re.compile(r"(?:chưa|không)\s+(?:có|chứa|tìm\s+thấy|được\s+cung\s+cấp|đề\s+cập|ghi\s+nhận)(?:\s+đầy\s+đủ|\s+đủ|\s+chi\s+tiết|\s+cụ\s+thể)*\s*(?:thông\s+tin|dữ\s+liệu)", re.IGNORECASE),
    re.compile(r"(?:tài\s+liệu|cơ\s+sở\s+dữ\s+liệu|danh\s+sách).*?(?:chưa|không)\s+(?:có|đủ|chứa|đề\s+cập|ghi\s+nhận).*?(?:để\s+trả\s+lời|thông\s+tin|dữ\s+liệu|giảng\s+viên)", re.IGNORECASE),
]

CITE_SPLIT_PATTERN = re.compile(
    r"(?:\n+\s*---\s*)?\n*(?:[#*>\-\s]*📌\s*)?\*{0,2}Nguồn(?:\s+tài\s+liệu|\s+từ\s+Internet)?(?:\s+trích\s+dẫn|\s+tham\s+khảo)?\*{0,2}\s*:?\*{0,2}\s*\n",
    flags=re.IGNORECASE
)


def _strip_all_citations(text: str) -> str:
    """Xóa triệt để mọi khối trích dẫn và các dòng bullet trích dẫn khỏi văn bản."""
    if not text:
        return ""
    body = CITE_SPLIT_PATTERN.split(text, maxsplit=1)[0].strip()
    # Xóa mọi dòng trích dẫn lẻ kiểu "- 📄 Trang ... - File: ..." (có hoặc không có icon 📄)
    body = re.sub(
        r"^\s*[-*•+]?\s*(?:📄\s*)?\*{0,2}Trang\s+[\d,\s\-và]+[-–—|•,]\s*\*{0,2}(?:File\s*:?\s*)?[A-Za-z0-9_.\-]+\.[A-Za-z0-9]+.*$",
        "",
        body,
        flags=re.IGNORECASE | re.MULTILINE
    ).strip()
    # Xóa tiêu đề "📌 Nguồn trích dẫn:" nếu nằm ở cuối văn bản
    body = re.sub(
        r"(?:\n+\s*---\s*)?\n*[#*>\-\s]*📌\s*\*{0,2}Nguồn[\s\S]*$",
        "",
        body,
        flags=re.IGNORECASE
    ).strip()
    body = re.sub(r"(?:\n\s*---\s*)+\s*$", "", body.rstrip())
    return body


def _strip_accents_lower(text: str) -> str:
    """Bỏ dấu tiếng Việt + chữ thường + gộp khoảng trắng để so khớp thực thể không phụ thuộc cách gõ."""
    import unicodedata
    s = (text or "").lower().replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s)


# Từ chung / từ để hỏi: gặp là dừng khi trích cụm địa danh phía sau từ kích hoạt
_ENTITY_STOP_WORDS = {
    "đâu", "nào", "gì", "này", "đó", "kia", "ấy", "mới", "cũ", "chính", "phụ", "của", "có", "không",
    "như", "thế", "là", "và", "hay", "hoặc", "với", "cho", "hiện", "nay", "bao", "nhiêu", "học", "viện",
    "trường", "ptit", "thông", "tin", "nằm", "đặt", "ra", "sao", "nhé", "ạ", "ơi", "vậy", "nhỉ", "thì",
    "được", "đang", "sẽ", "đã", "các", "những", "một", "mấy", "để", "từ", "đến", "về", "trong", "ngoài",
    "đào", "tạo", "đại", "tp", "hcm", "phía", "bắc", "nam", "miền", "khi",
}
_ENTITY_TRIGGER_WORDS = {"cơ", "sở", "campus", "khu", "tòa", "ở", "tại", "địa", "chỉ", "trung", "tâm", "câu", "lạc", "bộ", "clb", "hội", "trường", "ký", "túc", "xá", "ktx", "cuộc", "thi"}

_ENTITY_TRIGGER_RE = re.compile(
    r"\b(?:cơ\s+sở|campus|khu|tòa|hội\s+trường|ký\s+túc\s+xá|ktx|trung\s+tâm|câu\s+lạc\s+bộ|clb|cuộc\s+thi|ở|tại|địa\s+chỉ|phường|quận|huyện|xã|thôn|đường|phố|làng)\s+"
    r"([A-Za-zÀ-ỹ]+(?:\s+[A-Za-zÀ-ỹ]+){0,3})",
    re.IGNORECASE
)


def _extract_specific_entity_phrases(question: str) -> list:
    """
    Trích các cụm địa danh / tên riêng cụ thể trong câu hỏi (vd: 'Ngọc Trục', 'Hòa Lạc').
    - Cụm đứng sau từ kích hoạt địa điểm (cơ sở, ở, tại, địa chỉ, phường, đường...), dừng ở từ chung/từ để hỏi.
    - Cụm từ viết hoa liên tiếp (>= 2 từ) không nằm đầu câu.
    Chỉ giữ cụm có >= 2 từ để tránh báo động giả.
    """
    if not question:
        return []
    phrases = []

    for m in _ENTITY_TRIGGER_RE.finditer(question):
        words = []
        for w in m.group(1).split():
            wl = w.lower()
            if wl in _ENTITY_TRIGGER_WORDS:
                if words:
                    break
                continue  # bỏ qua từ kích hoạt lặp ở đầu cụm (vd: "cơ sở ở Ngọc Trục")
            if wl in _ENTITY_STOP_WORDS:
                break
            words.append(w)
        if len(words) >= 2:
            phrases.append(" ".join(words))

    for m in re.finditer(r"(?<!^)(?<![.!?]\s)\b([A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+)+)", question):
        cand = m.group(1)
        if not any(w.lower() in _ENTITY_STOP_WORDS or w.lower() in _ENTITY_TRIGGER_WORDS for w in cand.split()):
            phrases.append(cand)

    seen, result = set(), []
    for p in phrases:
        key = _strip_accents_lower(p)
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def _is_queried_entity_missing_in_context(question: str, context_str: str) -> bool:
    """
    Kiểm tra nhanh xem:
    0. Người dùng có chủ động yêu cầu tra cứu trên Internet / web / Google không.
    1. Câu hỏi có đang hỏi về một tên miền hoặc giảng viên cụ thể mà tài liệu nội bộ không có.
    2. Câu hỏi hỏi về Tuyển sinh / Chỉ tiêu / Điểm chuẩn / Xét tuyển Đại học chính quy trong khi tài liệu nội bộ chỉ có Tuyển sinh Thạc sĩ.
    Nếu có -> Chuyển thẳng sang Web Search Fallback (không chờ LLM sinh câu từ chối hoặc trả lời sai sang thạc sĩ).
    """
    if not question:
        return False
    q_lower = question.lower()
    ctx_lower = (context_str or "").lower()

    # 0. Người dùng chủ động yêu cầu tra cứu trên Internet / tìm kiếm web / Google
    user_requests_web = bool(re.search(
        r"\b(?:tra\s+(?:cứu\s+)?(?:trên\s+|qua\s+)?(?:internet|mạng|google|web)|tìm\s+(?:kiếm\s+)?(?:trên\s+|qua\s+)?(?:internet|mạng|google|web)|search\s+web|cần\s+tra\s+(?:trên\s+)?internet)\b",
        q_lower
    ))
    if user_requests_web:
        return True

    # 1. Kiểm tra nếu người dùng hỏi về một tên miền / trang web cụ thể (vd: it.ptit.edu.vn)
    queried_domains = web_search.extract_queried_domains(question)
    for dom in queried_domains:
        if dom.lower() not in ctx_lower:
            return True

    # 2. Kiểm tra nếu người dùng hỏi về một giảng viên / thầy / cô cụ thể (vd: thầy Hoàng Mạnh Cường)
    lecturer_name = web_search.extract_queried_lecturer_name(question)
    if lecturer_name:
        if lecturer_name.lower() not in ctx_lower:
            return True

    # 2.5. Kiểm tra địa danh / tên riêng cụ thể (vd: "cơ sở Ngọc Trục", "ở Hòa Lạc") và năm học/mốc thời gian cụ thể
    # Nếu hoàn toàn không xuất hiện trong tài liệu nội bộ -> bắt buộc tra Internet.
    ctx_plain = _strip_accents_lower(context_str or "")
    for phrase in _extract_specific_entity_phrases(question):
        if _strip_accents_lower(phrase) not in ctx_plain:
            print(f"[*] Entity Check: '{phrase}' không có trong tài liệu nội bộ -> chuyển sang Web Search.")
            return True

    for yr in re.findall(r"\b(20[2-3]\d)\b", question):
        if yr not in ctx_lower:
            print(f"[*] Year Check: năm '{yr}' không có trong tài liệu nội bộ -> chuyển sang Web Search.")
            return True

    # 3. Kiểm tra câu hỏi về Tuyển sinh / Chỉ tiêu / Điểm chuẩn / Xét tuyển:
    is_asking_admission = any(k in q_lower for k in [
        "tuyển sinh", "chỉ tiêu", "điểm chuẩn", "xét tuyển", "phương thức tuyển", "nguyện vọng"
    ])
    is_explicit_postgrad = any(k in q_lower for k in [
        "thạc sĩ", "thạc sỹ", "sau đại học", "cao học", "tiến sĩ", "tiến sỹ", "ncs", "nghiên cứu sinh"
    ])
    if is_asking_admission and not is_explicit_postgrad:
        # Nếu trong ngữ cảnh tài liệu nội bộ KHÔNG có tài liệu đề án tuyển sinh đại học chính quy
        has_undergrad_admission_doc = any(k in ctx_lower for k in [
            "tuyển sinh đại học chính quy", "tuyển sinh đại học hệ chính quy", "đề án tuyển sinh đại học", "tuyển sinh vào đại học hệ chính quy"
        ])
        if not has_undergrad_admission_doc:
            return True

    return False


def _is_no_info_response(text):
    """
    Kiểm tra xem câu trả lời có phải là thông báo từ chối / không có thông tin trong tài liệu hay không.
    Nếu là câu trả lời từ chối hoàn toàn, tuyệt đối không gắn nguồn trích dẫn và không lưu vào cache.
    """
    if not text:
        return True

    body = _strip_all_citations(text)
    body_lower = body.lower()

    has_refusal = any(p in body_lower for p in REFUSAL_PHRASES) or any(rx.search(body_lower) for rx in REFUSAL_REGEX_PATTERNS)
    if not has_refusal:
        return False

    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    first_para = paragraphs[0].lower() if paragraphs else body_lower
    has_markdown_table = bool(re.search(r"^\|.+\|$", body, flags=re.MULTILINE))
    bullet_lines = re.findall(r"^\s*[-*•+]\s+.+", body, flags=re.MULTILINE)

    first_para_refusal = any(p in first_para for p in REFUSAL_PHRASES) or any(rx.search(first_para) for rx in REFUSAL_REGEX_PATTERNS)
    if first_para_refusal and not has_markdown_table and (len(bullet_lines) == 0 or len(body) < 600):
        return True

    if len(body) < 680 and not has_markdown_table and len(bullet_lines) == 0:
        return True

    return False


PARTIAL_MISSING_INFO_PATTERNS = [
    re.compile(r"(?:tuy\s+nhiên|nhưng|mặc\s+dù|hiện\s+tại|hiện\s+nay).*?(?:chưa|không)\s+(?:liệt\s+kê|ghi\s+nhận|cung\s+cấp|đề\s+cập|có|nêu)(?:\s+chi\s+tiết|\s+cụ\s+thể)*\s*(?:tên\s+từng\s+môn|môn\s+học|danh\s+sách|thông\s+tin|chi\s+tiết)?", re.IGNORECASE),
    re.compile(r"chỉ\s+ghi\s+nhận.*?(?:mà|nhưng|tuy\s+nhiên)\s+(?:chưa|không)", re.IGNORECASE),
    re.compile(r"(?:chưa|không)\s+(?:thể\s+cung\s+cấp|liệt\s+kê|ghi\s+nhận|cung\s+cấp|đề\s+cập|nêu|có)(?:\s+cho\s+bạn)?(?:\s+chi\s+tiết|\s+cụ\s+thể)*\s*(?:về\s+môn|tên\s+từng\s+môn|môn\s+học|thông\s+tin\s+cá\s+nhân|thông\s+tin\s+chi\s+tiết|danh\s+sách)", re.IGNORECASE),
    re.compile(r"(?:tài\s+liệu|dữ\s+liệu).*?(?:chưa|không)\s+(?:liệt\s+kê|ghi\s+nhận|nêu\s+rõ|đề\s+cập).*?(?:môn\s+học|chi\s+tiết|cụ\s+thể)", re.IGNORECASE),
    re.compile(r"(?:chưa\s+có|không\s+có|chưa\s+ghi\s+nhận|chưa\s+cung\s+cấp).*?(?:thông\s+tin|chỉ\s+tiêu|đề\s+án).*?(?:tuyển\s+sinh\s+đại\s+học|đại\s+học\s+chính\s+quy)", re.IGNORECASE),
    re.compile(r"(?:chỉ\s+có|chỉ\s+ghi\s+nhận|chỉ\s+áp\s+dụng\s+cho).*?(?:tuyển\s+sinh\s+thạc\s+sĩ|sau\s+đại\s+học)", re.IGNORECASE),
]


def _has_missing_info_admission(text: str, question: str = "") -> bool:
    """
    Kiểm tra xem câu trả lời có chứa các câu thừa nhận thiếu thông tin chi tiết hay không
    (Ví dụ: có chức vụ nhưng thiếu danh sách môn học, hoặc không có thông tin chi tiết về người được hỏi).
    Nếu có -> Kích hoạt Web Search Fallback để bổ sung thông tin từ website chính thức của PTIT.
    """
    if not text:
        return True
    body = _strip_all_citations(text)

    # Nếu câu hỏi chỉ hỏi về môn học / học phần (số tín chỉ, học kỳ, tiên quyết...) và câu trả lời đã có thông tin cụ thể
    # -> TUYỆT ĐỐI KHÔNG kích hoạt Web Search (tránh lãng phí lượt tìm kiếm khi tài liệu nội bộ đã có)
    if question:
        q_lower = question.lower()
        is_course_detail_q = any(k in q_lower for k in ["môn", "học phần", "tín chỉ", "tiến trình", "khung chương trình"])
        asks_instructor = any(k in q_lower for k in ["ai dạy", "giảng viên nào", "thầy nào", "cô nào", "ai giảng dạy", "ai phụ trách"])
        if is_course_detail_q and not asks_instructor:
            body_lower = body.lower()
            has_course_info = any(k in body_lower for k in ["tín chỉ", "học kỳ", "hk", "mã môn", "tiên quyết", "chuyên ngành"])
            if has_course_info and len(body) > 150:
                return False

    # Nếu 2 đoạn mở đầu thừa nhận tài liệu nội bộ chưa có/chưa đề cập thông tin được hỏi
    # (kể cả khi LLM liệt kê thêm thông tin liên quan hoặc hướng dẫn liên hệ bên dưới) -> kích hoạt Web Search
    head_paras = "\n\n".join(p.strip() for p in body.split("\n\n")[:2] if p.strip()).lower()
    if any(p in head_paras for p in REFUSAL_PHRASES) or any(rx.search(head_paras) for rx in REFUSAL_REGEX_PATTERNS):
        return True

    for rx in PARTIAL_MISSING_INFO_PATTERNS:
        if rx.search(body):
            return True

    # Nếu người dùng hỏi cụ thể về giảng viên dạy môn gì mà câu trả lời chỉ có chuyên ngành chung và chưa có danh sách môn cụ thể
    if question:
        is_asking_subjects = bool(re.search(r"\b(?:dạy\s+(?:những\s+)?môn|môn\s+(?:gì|nào|học)|môn\s+phụ\s+trách|giảng\s+dạy\s+môn)\b", question, re.IGNORECASE))
        if is_asking_subjects:
            body_lower = body.lower()
            if "chuyên ngành giảng dạy" in body_lower or "chuyên ngành" in body_lower:
                has_concrete_subjects = any(w in body_lower for w in ["c++", "giải thuật", "hệ điều hành", "lập trình hướng đối tượng", "lập trình web", "môn học:", "danh sách môn", "các môn:"])
                if not has_concrete_subjects:
                    return True
    return False


def ensure_answer_citations(text, ptit_docs=None, user_docs=None, effective_scope="ptit_only", question=""):
    """
    Chuẩn hóa hoặc tự động bổ sung mục '📌 **Nguồn trích dẫn:**' ở cuối câu trả lời theo đúng Mẫu 1:
    - 📄 Trang xx - File: yy (Tên văn bản)
    Đồng thời trả về danh sách structured sources phục vụ giao diện.
    Nếu câu trả lời là thông báo từ chối / chưa có thông tin, trả về nguyên văn không kèm trích dẫn.
    """
    if not text:
        return "", []

    ptit_docs = ptit_docs or []
    user_docs = user_docs or []
    user_filenames_lower = {
        os.path.basename(d.get("filename", "")).lower(): os.path.basename(d.get("filename", ""))
        for d in user_docs if d.get("filename")
    }

    parts = CITE_SPLIT_PATTERN.split(text, maxsplit=1)
    body_text = _strip_all_citations(parts[0])
    raw_cite_block = parts[1].strip() if len(parts) > 1 else ""

    # Nếu câu trả lời là thông báo không có thông tin -> xóa bỏ mọi trích dẫn sai (nếu có) và trả về ngay
    if _is_no_info_response(text) or _is_no_info_response(body_text):
        return body_text, []

    # Nếu câu hỏi hỏi về thực thể cụ thể (tên giảng viên / tên miền) mà thực thể đó không hề có trong tài liệu -> không gắn trích dẫn giả
    all_docs_text = "\n".join(
        [(d.get("content") or "") for d in ptit_docs] + [(d.get("content") or "") for d in user_docs]
    )
    if question and _is_queried_entity_missing_in_context(question, all_docs_text):
        return body_text, []

    cited_items = []
    seen_cite_keys = set()

    def _add_citation(raw_file, page_num):
        if not raw_file:
            return
        try:
            p_int = max(1, int(page_num))
        except Exception:
            p_int = 1

        clean_f = os.path.basename(str(raw_file).strip().strip("`*'\".,;)"))
        stem_f = os.path.splitext(clean_f)[0].lower()

        is_u_doc = False
        if clean_f.lower() in user_filenames_lower:
            is_u_doc = True
            clean_f = user_filenames_lower[clean_f.lower()]
        else:
            for u_low, u_orig in user_filenames_lower.items():
                if os.path.splitext(u_low)[0] == stem_f:
                    is_u_doc = True
                    clean_f = u_orig
                    break

        info = resolve_doc_display_info(clean_f, is_user_doc=is_u_doc)
        key = (info["file"].lower(), p_int)
        if key not in seen_cite_keys:
            seen_cite_keys.add(key)
            cited_items.append({
                "file": info["file"],
                "source": info["file"],
                "md_file": info["md_file"],
                "page": p_int,
                "title": info["title"],
                "is_user_doc": info["is_user_doc"],
                "type": "USER_DOC" if info["is_user_doc"] else "PTIT_DOC"
            })

    # 1. Phân tích phần trích dẫn do LLM sinh ra (nếu có)
    if raw_cite_block:
        for line in raw_cite_block.splitlines():
            line_s = line.strip()
            if not line_s:
                continue
            # Mẫu chuẩn: Trang 3 - File: hp_2025.pdf (...) hoặc Trang 2, 3 - File: hp_2025.pdf
            m1 = re.search(
                r"Trang\s*([\d\s,; và-]+?)\s*[-–—|•,]\s*(?:File\s*:?\s*)?([A-Za-z0-9_.\-]+\.[A-Za-z0-9]+)",
                line_s,
                flags=re.IGNORECASE
            )
            if m1:
                pages_str, fname = m1.group(1), m1.group(2)
                for p_str in re.findall(r"\d+", pages_str):
                    _add_citation(fname, int(p_str))
                continue

            # Mẫu đảo: File: hp_2025.pdf - Trang 3 hoặc hp_2025.pdf (Trang 3)
            m2 = re.search(
                r"([A-Za-z0-9_.\-]+\.(?:pdf|md|docx|txt))\b.*?Trang\s*([\d\s,;-]+)",
                line_s,
                flags=re.IGNORECASE
            )
            if m2:
                fname, pages_str = m2.group(1), m2.group(2)
                for p_str in re.findall(r"\d+", pages_str):
                    _add_citation(fname, int(p_str))

    # 2. Nếu LLM quên sinh trích dẫn hoặc dùng chế độ Fallback -> Tự động lấy từ tài liệu thực sự khớp nội dung
    has_refusal_hint = _is_no_info_response(body_text) or any(p in body_text.lower() for p in REFUSAL_PHRASES)
    if not cited_items and not has_refusal_hint:
        if effective_scope in ("user_only", "hybrid") and user_docs:
            direct_u = [d for d in user_docs if d.get("is_direct_match")]
            chosen_u = direct_u[:2] if direct_u else (user_docs[:1] if effective_scope == "user_only" else [])
            for d in chosen_u:
                _add_citation(d.get("filename"), d.get("page", 1))

        if effective_scope in ("ptit_only", "hybrid") and ptit_docs:
            body_lower = body_text.lower()
            a_words = set(re.findall(r"\w{3,}", body_lower)) - GENERIC_PTIT_WORDS
            scored_ptit = []
            for d in ptit_docs:
                d_words = set(re.findall(r"\w{3,}", (d.get("content") or "").lower())) - GENERIC_PTIT_WORDS
                overlap = len(d_words & a_words)
                if overlap >= 3:
                    scored_ptit.append((overlap, d))
            scored_ptit.sort(key=lambda x: x[0], reverse=True)
            chosen_p = [item[1] for item in scored_ptit[:2]]
            if not chosen_p and ptit_docs and "thông tin tìm thấy trong tài liệu chính thức" in body_lower:
                chosen_p = ptit_docs[:1]
            for d in chosen_p:
                _add_citation(d.get("source"), d.get("page", 1))

    if not cited_items:
        return body_text, []

    cite_lines = [
        f"- 📄 Trang {item['page']} - File: {item['file']} ({item['title']})"
        for item in cited_items
    ]
    formatted_cite_section = "\n\n---\n📌 **Nguồn trích dẫn:**\n" + "\n".join(cite_lines)
    final_text = body_text + formatted_cite_section
    return final_text, cited_items


def safe_fallback_answer(question, docs):
    """
    Bộ dự phòng an toàn khi mất kết nối AI hoàn toàn:
    Trích xuất nội dung từ tài liệu có độ khớp cao nhất, loại bỏ văn bản mở đầu hành chính rác.
    """
    if not docs:
        return "Hiện chưa tìm thấy thông tin phù hợp trong tài liệu của Học viện. Bạn vui lòng liên hệ phòng Công tác sinh viên hoặc phòng ban liên quan để được hỗ trợ trực tiếp."

    q_lower = normalize_academic_query(question).lower()
    q_words = [w for w in re.findall(r"\w+", q_lower) if len(w) > 1 and w not in GENERIC_PTIT_WORDS]

    # 0. Nếu hỏi về điều kiện / tiêu chuẩn xét cấp học bổng khuyến khích học tập hoặc GPA & Điểm rèn luyện
    if any(k in q_lower for k in ["học bổng", "hoc bong", "khuyến khích", "gpa", "tbcmr", "rèn luyện", "loại giỏi", "loại xuất sắc", "loại khá"]) and any("hb_" in (d.get("source") or "").lower() for d in docs):
        return (
            "Theo **Bảng kết quả xét cấp học bổng khuyến khích học tập (HB KKHT) học kỳ 1 năm học 2025-2026** (`HB_HK1_25-26.pdf`) và **Sổ tay Sinh viên** (`so_tay.pdf`), điều kiện và tiêu chuẩn xét cấp học bổng khuyến khích học tập tại PTIT bao gồm:\n\n"
            "- **1. Hai tiêu chí đánh giá bắt buộc:** Sinh viên phải đạt đồng thời mức điểm chuẩn về **Điểm trung bình chung mở rộng (Điểm TBCMR - thang điểm 4)** và **Điểm rèn luyện (Điểm RL - thang điểm 100)** của học kỳ xét cấp theo quy định riêng cho từng ngành, từng khóa tại Cơ sở Hà Nội (HN) hoặc Cơ sở TP. Hồ Chí Minh (HCM) trong phạm vi quỹ học bổng.\n"
            "- **2. Tiêu chuẩn điểm chuẩn theo 3 loại học bổng:**\n"
            "  + **Học bổng loại Xuất sắc:** Điểm rèn luyện đạt từ **90 điểm trở lên** và Điểm TBCMR đạt từ **3,60 trở lên** (một số ngành/khóa có mức điểm chuẩn TBCMR từ 3,60 đến 3,76).\n"
            "  + **Học bổng loại Giỏi:** Điểm rèn luyện đạt từ **80 điểm trở lên** (tùy ngành/khóa từ 80 - 90 điểm) và Điểm TBCMR đạt tối thiểu từ **3,20 trở lên** (điểm chuẩn thực tế dao động từ 3,20 đến 3,92 tùy ngành, khóa).\n"
            "  + **Học bổng loại Khá:** Điểm rèn luyện đạt từ **65 điểm trở lên** (tùy ngành/khóa từ 65 - 88 điểm) và Điểm TBCMR đạt tối thiểu từ **2,50 trở lên** (áp dụng tại các ngành/khóa còn chỉ tiêu quỹ học bổng sau khi xét loại Xuất sắc và Giỏi).\n"
            "- **3. Quy định về điểm học cải thiện (Điều 6, Khoản 2.2 - Sổ tay sinh viên):** Kết quả học cải thiện điểm chỉ sử dụng để tính điểm trung bình chung tích lũy, **không sử dụng để xét khen thưởng, học bổng**."
        )

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
    incoming_filenames = {os.path.basename(f.filename.strip()) for f in valid_new_files}
    total_unique = len(existing_filenames.union(incoming_filenames))

    if total_unique > 3:
        return jsonify({
            "error": f"Mỗi phiên chỉ được tải tối đa 3 tài liệu. Hiện tại bạn đã có {len(existing_files)} tài liệu."
        }), 400

    coll = get_user_vector_db()
    processed_files = []

    for f in valid_new_files:
        fname = os.path.basename(f.filename.strip())
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
        extracted_json_path = _find_extracted_json_path(session_dir, fname)
        new_extracted_json_path = os.path.join(session_dir, f"{fname}_extracted.json")

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
            with open(new_extracted_json_path, "w", encoding="utf-8") as f_json:
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

    updated_files = get_session_uploaded_files(session_id, force_refresh=True)
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
            extracted_json_full = os.path.join(session_dir, f"{filename}_extracted.json")
            extracted_json_legacy = os.path.join(session_dir, f"{os.path.splitext(filename)[0]}_extracted.json")
            for p in [target_file, extracted_json_full, extracted_json_legacy]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
        else:
            coll.delete(where={"session_id": session_id})
            if os.path.exists(session_dir):
                shutil.rmtree(session_dir, ignore_errors=True)
    except Exception as e:
        print(f"[!] Delete session doc error: {e}")

    _SESSION_FILES_CACHE.pop(session_id, None)
    files = get_session_uploaded_files(session_id, force_refresh=True)
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
    try:
        speed = float(data.get("speed") or 1.0)
    except (ValueError, TypeError):
        speed = 1.0

    if not text:
        return jsonify({"error": "Vui lòng cung cấp văn bản cần đọc."}), 400

    result = voice_service.generate_speech(text=text, voice=voice, speed=speed)
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
        transcript = normalize_academic_query(transcript)
        return jsonify({"status": "success", "transcript": transcript})
    except Exception as e:
        print(f"[!] STT Error: {e}")
        return jsonify({"error": str(e)}), 500


def _get_response_cache_key(question, effective_scope, user_files, history):
    """
    Tạo khóa bộ nhớ đệm (LRU Response Cache) cho câu hỏi.
    Nếu câu hỏi mang tính nối tiếp hội thoại trước đó ("còn...", "thế còn...", "ở trên...") thì không dùng cache.
    """
    q_norm = re.sub(r"\s+", " ", (question or "").lower().strip().rstrip("?.,!;"))
    if not q_norm:
        return None

    if history and len(history) > 1:
        follow_up_markers = [
            "còn ", "thế còn", "vậy còn", "như trên", "ở trên", "vừa nêu",
            "chi tiết hơn", "nói rõ hơn", "giải thích thêm", "môn đó", "ngành đó", "khoản đó"
        ]
        if len(q_norm.split()) <= 4 or any(q_norm.startswith(m) or f" {m}" in q_norm for m in follow_up_markers):
            return None

    files_sig = tuple(sorted(f.get("filename", "") for f in (user_files or [])))
    return (q_norm, effective_scope, files_sig)


def _store_response_cache(cache_key, clean_answer, model_used, referenced_files, sources=None):
    """Lưu câu trả lời chuẩn vào bộ nhớ đệm LRU trong RAM (không lưu câu trả lời từ chối / không có thông tin)."""
    if not cache_key or not clean_answer or _is_no_info_response(clean_answer):
        return
    if len(_RESPONSE_CACHE) >= MAX_RESPONSE_CACHE_SIZE:
        _RESPONSE_CACHE.pop(next(iter(_RESPONSE_CACHE)), None)
    _RESPONSE_CACHE[cache_key] = {
        "answer": clean_answer,
        "model_used": model_used,
        "referenced_files": list(referenced_files or []),
        "sources": list(sources or [])
    }


def _retrieve_rag_context(question, session_id, scope, top_k, custom_api_key, user_files=None, history=None):
    """Thực thi truy vấn ngữ cảnh RAG tối ưu (hỗ trợ Fast-Path RAM, kế thừa ngữ cảnh hội thoại & Parallel Hybrid)."""
    question = normalize_academic_query(question)
    if user_files is None:
        user_files = get_session_uploaded_files(session_id) if session_id else []
    has_user_files = len(user_files) > 0
    effective_scope = scope if has_user_files else "ptit_only"

    user_docs = []
    ptit_docs = []

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
        ptit_search_query = f"{question} {' '.join(user_topics)}"
    elif history and isinstance(history, list) and len(history) > 0:
        # Nếu câu hỏi hiện tại ngắn hoặc nối tiếp hội thoại trước đó mà chưa nêu rõ chủ đề chính (học bổng, học phí, ký túc xá, miễn giảm...),
        # tự động bổ sung từ khóa chủ đề từ câu hỏi/trả lời liền trước để tìm kiếm RAG không bị lệch hướng.
        explicit_topics = [
            "học bổng", "học phí", "ký túc xá", "ktx", "miễn giảm", "miễn học", "miễn thi",
            "quy đổi", "tiếng anh", "ielts", "toeic", "thạc sĩ", "giảng viên", "câu lạc bộ", "clb"
        ]
        has_specific_entity = bool(
            web_search.extract_queried_domains(question)
            or web_search.extract_queried_lecturer_name(question)
        )
        if not has_specific_entity and not any(t in q_lower for t in explicit_topics):
            recent_text = " ".join(
                (h.get("content") or "")[:300].lower()
                for h in history[-3:]
                if isinstance(h, dict) and h.get("content")
            )
            carried_topics = [t for t in explicit_topics if t in recent_text]
            if carried_topics:
                ptit_search_query = f"{question} {' '.join(carried_topics[:2])}"

    if effective_scope == "user_only":
        user_docs = query_user_documents(question, session_id, n_results=top_k, custom_api_key=custom_api_key)
    elif effective_scope == "ptit_only":
        ptit_docs = smart_query_knowledge_base(ptit_search_query, n_results=top_k, custom_api_key=custom_api_key)
    else:
        active_key = custom_api_key if custom_api_key else API_KEY
        if ptit_search_query == question:
            q_vec_user = get_embedding_rest(question, active_key, timeout=2.5)
            q_vec_ptit = q_vec_user
        else:
            batch_vecs = document_parser.batch_get_embeddings([question, ptit_search_query], api_key=active_key, timeout=3.5)
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
        u_parts = [
            f"--- [TÀI LIỆU TẢI LÊN | File: {d['filename']} (Tài liệu người dùng tải lên) | Trang {d['page']}] ---\n{d['content']}"
            for d in user_docs
        ]
        context_sections.append("=== [TÀI LIỆU DO NGƯỜI DÙNG TẢI LÊN] ===\n" + "\n\n".join(u_parts))

    if ptit_docs:
        p_parts = []
        for i, d in enumerate(ptit_docs, start=1):
            info = resolve_doc_display_info(d.get("source"), is_user_doc=False)
            p_parts.append(
                f"--- [TÀI LIỆU PTIT {i} | File: {info['file']} ({info['title']}) | Trang {d.get('page', 1)}] ---\n{d['content']}"
            )
        context_sections.append("=== [CƠ SỞ DỮ LIỆU CHÍNH THỨC PTIT] ===\n" + "\n\n".join(p_parts))

    context_str = "\n\n".join(context_sections) if context_sections else "Không tìm thấy dữ liệu trực tiếp."
    return context_str, effective_scope, user_files, user_docs, ptit_docs, is_referential


def _resolve_referenced_files(user_docs, user_files, clean_answer, effective_scope, is_referential):
    """Xác định chính xác danh sách tài liệu người dùng thực sự được tham chiếu trong câu trả lời."""
    if clean_answer and _is_no_info_response(clean_answer):
        return []
    referenced_files = []
    if user_docs:
        direct_matched_files = list(dict.fromkeys(
            d["filename"] for d in user_docs if d.get("is_direct_match")
        ))
        ans_lower = (clean_answer or "").lower()
        mentioned_files = [
            f["filename"] for f in (user_files or [])
            if f["filename"].lower() in ans_lower
            or os.path.splitext(f["filename"])[0].lower() in ans_lower
        ]
        if effective_scope == "user_only" or is_referential:
            combined = list(dict.fromkeys(direct_matched_files + mentioned_files))
            referenced_files = combined if combined else list(dict.fromkeys(d["filename"] for d in user_docs))
        else:
            referenced_files = list(dict.fromkeys(direct_matched_files + mentioned_files))
    return referenced_files


def _locate_document_path(raw_file, session_id=None):
    """
    Xác định đường dẫn thực tế của tài liệu trên đĩa (chống Path Traversal):
    - Ưu tiên 1: Tài liệu người dùng tải lên trong user_uploads/{session_id}/
    - Ưu tiên 2: Tài liệu PDF gốc của Học viện trong data/
    - Ưu tiên 3: Tài liệu Markdown trong processed_data/
    """
    if not raw_file:
        return None, None, False
    safe_name = os.path.basename(str(raw_file).strip())
    if not safe_name:
        return None, None, False

    if session_id:
        safe_sess = os.path.basename(str(session_id).strip())
        user_path = os.path.join(USER_UPLOADS_DIR, safe_sess, safe_name)
        if os.path.isfile(user_path):
            return user_path, safe_name, True

    info = resolve_doc_display_info(safe_name, is_user_doc=False)
    pdf_candidate = os.path.join(DATA_DIR, info["file"])
    if os.path.isfile(pdf_candidate):
        return pdf_candidate, info["file"], False

    direct_data_path = os.path.join(DATA_DIR, safe_name)
    if os.path.isfile(direct_data_path):
        return direct_data_path, safe_name, False

    if info.get("md_file"):
        md_candidate = os.path.join(PROCESSED_DIR, info["md_file"])
        if os.path.isfile(md_candidate):
            return md_candidate, info["md_file"], False

    return None, None, False


@app.route("/api/view-file", methods=["GET"])
def view_file():
    """Phục vụ xem trực tiếp file PDF / tài liệu gốc trên trình duyệt (hỗ trợ nhảy trang #page=xx)."""
    raw_file = (request.args.get("file") or "").strip()
    session_id = (request.args.get("session_id") or "").strip()

    target_path, resolved_name, _ = _locate_document_path(raw_file, session_id=session_id)
    if not target_path or not os.path.isfile(target_path):
        return jsonify({"error": f"Không tìm thấy file '{raw_file}'."}), 404

    ext = os.path.splitext(resolved_name)[1].lower()
    mime_map = {
        ".pdf": "application/pdf",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/plain; charset=utf-8",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
    mimetype = mime_map.get(ext, "application/octet-stream")
    as_attach = ext == ".docx"

    response = send_file(
        target_path,
        mimetype=mimetype,
        as_attachment=as_attach,
        download_name=resolved_name,
        conditional=True
    )
    if not as_attach:
        encoded_name = quote(resolved_name)
        response.headers["Content-Disposition"] = f"inline; filename=\"{encoded_name}\"; filename*=UTF-8''{encoded_name}"
    return response


@app.route("/api/render-pdf-page", methods=["GET"])
def render_pdf_page():
    """Kết xuất chính xác trang xx của file PDF thành hình ảnh PNG sắc nét bằng PyMuPDF."""
    raw_file = (request.args.get("file") or "").strip()
    session_id = (request.args.get("session_id") or "").strip()
    try:
        page_num = max(1, int(request.args.get("page") or 1))
    except Exception:
        page_num = 1
    try:
        dpi = min(220, max(96, int(request.args.get("dpi") or 150)))
    except Exception:
        dpi = 150

    target_path, resolved_name, _ = _locate_document_path(raw_file, session_id=session_id)
    if not target_path or not resolved_name.lower().endswith(".pdf"):
        return jsonify({"error": "Chỉ hỗ trợ kết xuất hình ảnh trang cho định dạng PDF."}), 404

    try:
        import pymupdf
        doc = pymupdf.open(target_path)
        total_pages = len(doc)
        clamped_page = min(max(1, page_num), total_pages)
        page = doc[clamped_page - 1]
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        doc.close()

        resp = Response(img_bytes, mimetype="image/png")
        resp.headers["Cache-Control"] = "public, max-age=3600"
        resp.headers["X-Total-Pages"] = str(total_pages)
        resp.headers["X-Current-Page"] = str(clamped_page)
        return resp
    except Exception as e:
        return jsonify({"error": f"Lỗi kết xuất trang PDF: {str(e)}"}), 500


@app.route("/api/view-page-detail", methods=["GET"])
def view_page_detail():
    """
    Trả về thông tin chi tiết của Trang xx thuộc File yy:
    - Đường dẫn xem PDF gốc (#page=xx)
    - Đường dẫn ảnh chụp chính xác Trang xx
    - Nội dung văn bản Markdown trích xuất của đúng Trang xx
    - Tổng số trang của tài liệu
    """
    raw_file = (request.args.get("file") or "").strip()
    session_id = (request.args.get("session_id") or "").strip()
    try:
        page_num = max(1, int(request.args.get("page") or 1))
    except Exception:
        page_num = 1

    target_path, resolved_name, is_user_doc = _locate_document_path(raw_file, session_id=session_id)
    if not target_path:
        return jsonify({"error": f"Không tìm thấy tài liệu '{raw_file}'."}), 404

    info = resolve_doc_display_info(resolved_name, is_user_doc=is_user_doc)
    is_pdf = resolved_name.lower().endswith(".pdf")
    total_pages = 1
    text_content = ""

    if is_user_doc:
        safe_sess = os.path.basename(session_id)
        session_dir = os.path.join(USER_UPLOADS_DIR, safe_sess)
        ext_json = _find_extracted_json_path(session_dir, resolved_name)
        if os.path.exists(ext_json):
            try:
                with open(ext_json, "r", encoding="utf-8") as f:
                    d_ext = json.load(f)
                chunks = d_ext.get("chunks", [])
                if chunks:
                    total_pages = max((int(c.get("page", 1)) for c in chunks), default=1)
                    page_chunks = [c.get("text", "") for c in chunks if int(c.get("page", 1)) == page_num]
                    if not page_chunks and page_num > total_pages:
                        page_num = total_pages
                        page_chunks = [c.get("text", "") for c in chunks if int(c.get("page", 1)) == page_num]
                    text_content = "\n\n".join(page_chunks).strip()
            except Exception:
                pass
        if is_pdf:
            try:
                import pymupdf
                doc = pymupdf.open(target_path)
                total_pages = len(doc)
                doc.close()
            except Exception:
                pass
    else:
        ensure_processed_docs_in_ram()
        md_name = info.get("md_file") or f"{os.path.splitext(resolved_name)[0]}.md"
        doc_pages = [p for (fn, p) in _RAM_PAGE_LOOKUP.keys() if fn.lower() == md_name.lower()]
        if doc_pages:
            total_pages = max(doc_pages)
        if is_pdf and os.path.isfile(target_path):
            try:
                import pymupdf
                doc = pymupdf.open(target_path)
                total_pages = max(total_pages, len(doc))
                doc.close()
            except Exception:
                pass
        clamped_page = min(max(1, page_num), total_pages)
        page_num = clamped_page
        text_content = _RAM_PAGE_LOOKUP.get((md_name, page_num), "")
        if not text_content:
            for (fn, p), body in _RAM_PAGE_LOOKUP.items():
                if fn.lower() == md_name.lower() and p == page_num:
                    text_content = body
                    break
        if not text_content:
            text_content = _RAM_FULL_DOC_LOOKUP.get(md_name, "")

    q_sess = f"&session_id={quote(session_id)}" if (is_user_doc and session_id) else ""
    file_url = f"/api/view-file?file={quote(resolved_name)}{q_sess}"
    page_image_url = f"/api/render-pdf-page?file={quote(resolved_name)}&page={page_num}{q_sess}" if is_pdf else None

    return jsonify({
        "file": resolved_name,
        "title": info["title"],
        "page": page_num,
        "total_pages": total_pages,
        "is_pdf": is_pdf,
        "is_user_doc": is_user_doc,
        "file_url": file_url,
        "page_image_url": page_image_url,
        "text_content": text_content or "*(Trang này là hình ảnh scan hoặc không có lớp văn bản tách rời — vui lòng xem bên tab Trang Tài Liệu PDF)*"
    })


@app.route("/api/sources", methods=["GET"])
def list_sources():
    """Trả về danh mục tài liệu chính thức trong Cơ sở tri thức PTIT."""
    catalog = []
    for key, meta in PTIT_DOC_METADATA.items():
        pdf_path = os.path.join(DATA_DIR, meta["pdf_file"])
        size_kb = round(os.path.getsize(pdf_path) / 1024, 1) if os.path.isfile(pdf_path) else 0
        size_str = f"{round(size_kb / 1024, 2)} MB" if size_kb >= 1024 else f"{size_kb} KB"
        catalog.append({
            "name": meta["pdf_file"],
            "title": meta["title"],
            "category": meta["category"],
            "desc": f"Văn bản chính thức của Học viện Công nghệ Bưu chính Viễn thông ({meta['pdf_file']}).",
            "file_size": size_str
        })
    return jsonify({"catalog": catalog})


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

    # TỐI ƯU 5: Kiểm tra Response Cache (< 5ms)
    cache_key = _get_response_cache_key(question, effective_scope, user_files, history)
    if cache_key and cache_key in _RESPONSE_CACHE:
        cached = _RESPONSE_CACHE[cache_key]
        return jsonify({
            "answer": cached["answer"],
            "model_used": f"{cached['model_used']} (Cache)",
            "scope_used": effective_scope,
            "referenced_files": cached["referenced_files"],
            "cached": True,
            "sources": cached.get("sources", [])
        })

    context_str, effective_scope, user_files, user_docs, ptit_docs, is_referential = _retrieve_rag_context(
        question, session_id, scope, top_k, custom_api_key, user_files=user_files, history=history
    )

    entity_missing = _is_queried_entity_missing_in_context(question, context_str)
    skip_local_llm = bool(entity_missing and effective_scope != "user_only" and web_search.is_web_search_available())

    is_fallback = False
    model_used = None
    clean_answer = ""

    if not skip_local_llm:
        answer, model_used, error_msg = generate_llm_answer(
            question=question,
            context_str=context_str,
            custom_api_key=custom_api_key,
            preferred_model=preferred_model,
            history=history,
            has_user_docs=bool(user_docs),
            user_files=user_files,
            scope=effective_scope
        )
        if not answer:
            print(f"[!] LLM không phản hồi ({error_msg}), chuyển sang chế độ dự phòng an toàn...")
            answer = safe_fallback_answer(question, ptit_docs or user_docs)
            model_used = "PTIT Safe Engine (Dự phòng)"
            is_fallback = True
        clean_answer = clean_llm_response(answer)

    # ===========================================================================
    # WEB SEARCH FALLBACK: Tìm kiếm web khi tài liệu nội bộ không có thông tin
    # ===========================================================================
    web_searched = False
    web_sources = []
    needs_web_search = bool(
        (skip_local_llm or _is_no_info_response(clean_answer) or _has_missing_info_admission(clean_answer, question))
        and effective_scope != "user_only"
        and web_search.is_web_search_available()
    )
    if needs_web_search:
        print(f"[*] Web Search Fallback: Tài liệu nội bộ không đủ thông tin, đang tìm kiếm web cho: '{question[:80]}'")
        web_results = web_search.search_web(question, num_results=3)
        if web_results:
            web_context = web_search.build_web_context(web_results)
            web_prompt = build_web_rag_prompt(question, web_context, history, internal_info=clean_answer)
            active_key_ws = custom_api_key.strip() if (custom_api_key and custom_api_key.strip()) else API_KEY
            models_to_try_ws = _resolve_and_order_models(preferred_model)
            web_answer = None
            for model_name_ws in models_to_try_ws:
                web_answer, web_err_ws = call_gemini_rest_api(web_prompt, model_name_ws, active_key_ws, timeout=8.5)
                if web_answer:
                    model_used = model_name_ws
                    break
            if web_answer:
                clean_answer = clean_llm_response(web_answer)
                clean_answer += web_search.format_web_citations(web_results, original_query=question)
                web_searched = True
                web_sources = [{"title": r["title"], "url": r.get("highlight_url") or r["url"]} for r in web_results]
                is_fallback = False
                print(f"[✓] Web Search Fallback: Đã tổng hợp câu trả lời từ {len(web_results)} kết quả web.")
            else:
                print(f"[!] Web Search Fallback: LLM không tổng hợp được từ kết quả web.")
        else:
            print(f"[!] Web Search Fallback: Không tìm thấy kết quả web.")

    if not web_searched:
        if not clean_answer:
            clean_answer = "Dựa trên cơ sở dữ liệu nội bộ hiện tại của Học viện Công nghệ Bưu chính Viễn thông (PTIT), hiện chưa có thông tin về nội dung bạn vừa tra cứu."
        clean_answer, sources_list = ensure_answer_citations(
            clean_answer, ptit_docs=ptit_docs, user_docs=user_docs, effective_scope=effective_scope, question=question
        )
        last_search_err = web_search.get_last_search_error()
        if last_search_err and effective_scope != "user_only" and _is_no_info_response(clean_answer):
            clean_answer += f"\n\n> ⚠️ **Lưu ý cấu hình Web Search:** {last_search_err}"
    else:
        sources_list = []

    referenced_files = _resolve_referenced_files(user_docs, user_files, clean_answer, effective_scope, is_referential)

    if not is_fallback and not web_searched and not _is_no_info_response(clean_answer) and cache_key:
        _store_response_cache(cache_key, clean_answer, model_used, referenced_files, sources=sources_list)

    return jsonify({
        "answer": clean_answer,
        "model_used": model_used,
        "scope_used": effective_scope,
        "referenced_files": referenced_files,
        "sources": sources_list,
        "web_searched": web_searched,
        "web_sources": web_sources
    })


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """
    TỐI ƯU 1: Endpoint Streaming Server-Sent Events (SSE).
    Hiển thị chữ ngay khi có token đầu tiên (~0.6s - 1.2s) hoặc tức thì (< 10ms) nếu trúng Cache.
    """
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

    def generate_sse():
        user_files = get_session_uploaded_files(session_id) if session_id else []
        has_user_files = len(user_files) > 0
        effective_scope = scope if has_user_files else "ptit_only"

        # 1. Kiểm tra Response Cache (< 5ms)
        cache_key = _get_response_cache_key(question, effective_scope, user_files, history)
        if cache_key and cache_key in _RESPONSE_CACHE:
            cached = _RESPONSE_CACHE[cache_key]
            yield f"data: {json.dumps({'type': 'meta', 'scope_used': effective_scope, 'referenced_files': cached['referenced_files'], 'sources': cached.get('sources', [])}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'chunk', 'delta': cached['answer']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'answer': cached['answer'], 'model_used': cached['model_used'] + ' (Cache)', 'scope_used': effective_scope, 'referenced_files': cached['referenced_files'], 'sources': cached.get('sources', []), 'cached': True}, ensure_ascii=False)}\n\n"
            return

        # 2. Truy xuất ngữ cảnh RAG siêu tốc (RAM Keyword + Vector)
        context_str, effective_scope, user_files, user_docs, ptit_docs, is_referential = _retrieve_rag_context(
            question, session_id, scope, top_k, custom_api_key, user_files=user_files, history=history
        )
        initial_refs = _resolve_referenced_files(user_docs, user_files, "", effective_scope, is_referential)
        yield f"data: {json.dumps({'type': 'meta', 'scope_used': effective_scope, 'referenced_files': initial_refs}, ensure_ascii=False)}\n\n"

        # 3. Gọi Gemini Streaming SSE (Bỏ qua nếu phát hiện thực thể được hỏi hoàn toàn không có trong ngữ cảnh nội bộ)
        active_key = custom_api_key.strip() if (custom_api_key and custom_api_key.strip()) else API_KEY
        models_to_try = _resolve_and_order_models(preferred_model)

        entity_missing = _is_queried_entity_missing_in_context(question, context_str)
        skip_local_llm = bool(entity_missing and effective_scope != "user_only" and web_search.is_web_search_available())

        accumulated = []
        model_used = None
        is_fallback = False
        raw_full = ""

        if not skip_local_llm:
            system_instruction = build_rag_prompt(question, context_str, history, bool(user_docs), user_files, effective_scope)
            start_time = time.time()

            for model_name in models_to_try:
                if time.time() - start_time > 18.0:
                    break
                try:
                    chunk_count = 0
                    for delta in stream_gemini_rest_api(system_instruction, model_name, api_key=active_key, timeout=8.5):
                        if delta:
                            accumulated.append(delta)
                            chunk_count += 1
                            yield f"data: {json.dumps({'type': 'chunk', 'delta': delta}, ensure_ascii=False)}\n\n"
                    if chunk_count > 0:
                        model_used = model_name
                        break
                except Exception as stream_err:
                    if accumulated:
                        model_used = model_name
                        break
                    continue

            raw_full = "".join(accumulated).strip()
            if not raw_full:
                raw_full = safe_fallback_answer(question, ptit_docs or user_docs)
                model_used = "PTIT Safe Engine (Dự phòng)"
                is_fallback = True
                yield f"data: {json.dumps({'type': 'chunk', 'delta': raw_full}, ensure_ascii=False)}\n\n"

        clean_answer = clean_llm_response(raw_full)

        # ===========================================================================
        # WEB SEARCH FALLBACK (Streaming): Tìm kiếm web khi tài liệu nội bộ không đủ
        # ===========================================================================
        web_searched = False
        web_sources = []
        web_results_for_cite = []
        needs_web_search = bool(
            (skip_local_llm or _is_no_info_response(clean_answer) or _has_missing_info_admission(clean_answer, question))
            and effective_scope != "user_only"
            and web_search.is_web_search_available()
        )
        if needs_web_search:
            yield f"data: {json.dumps({'type': 'web_search_start', 'message': '🔍 Đang tìm kiếm thông tin trên Internet...'}, ensure_ascii=False)}\n\n"
            print(f"[*] Web Search Fallback (Stream): Tìm kiếm web cho: '{question[:80]}'")
            web_results = web_search.search_web(question, num_results=3)
            if web_results:
                web_results_for_cite = web_results
                web_context = web_search.build_web_context(web_results)
                web_prompt = build_web_rag_prompt(question, web_context, history, internal_info=clean_answer)
                # Stream lại với kết quả web
                web_accumulated = []
                for wm in models_to_try:
                    try:
                        for delta in stream_gemini_rest_api(web_prompt, wm, api_key=active_key, timeout=8.5):
                            if delta:
                                web_accumulated.append(delta)
                                yield f"data: {json.dumps({'type': 'chunk', 'delta': delta}, ensure_ascii=False)}\n\n"
                        if web_accumulated:
                            raw_full = "".join(web_accumulated).strip()
                            model_used = wm
                            web_searched = True
                            web_sources = [{"title": r["title"], "url": r.get("highlight_url") or r["url"]} for r in web_results]
                            is_fallback = False
                            citation_delta = web_search.format_web_citations(web_results_for_cite, original_query=question)
                            if citation_delta:
                                yield f"data: {json.dumps({'type': 'chunk', 'delta': citation_delta}, ensure_ascii=False)}\n\n"
                            break
                    except Exception:
                        continue
                if not web_accumulated:
                    print(f"[!] Web Search Fallback (Stream): LLM không stream được từ kết quả web.")
            else:
                print(f"[!] Web Search Fallback (Stream): Không tìm thấy kết quả web.")

        clean_answer = clean_llm_response(raw_full)
        if web_searched and web_results_for_cite:
            clean_answer += web_search.format_web_citations(web_results_for_cite, original_query=question)
            sources_list = []
        else:
            if not clean_answer:
                clean_answer = "Dựa trên cơ sở dữ liệu nội bộ hiện tại của Học viện Công nghệ Bưu chính Viễn thông (PTIT), hiện chưa có thông tin về nội dung bạn vừa tra cứu."
                yield f"data: {json.dumps({'type': 'chunk', 'delta': clean_answer}, ensure_ascii=False)}\n\n"
            clean_answer, sources_list = ensure_answer_citations(
                clean_answer, ptit_docs=ptit_docs, user_docs=user_docs, effective_scope=effective_scope, question=question
            )
            last_search_err = web_search.get_last_search_error()
            if last_search_err and effective_scope != "user_only" and _is_no_info_response(clean_answer):
                err_notice = f"\n\n> ⚠️ **Lưu ý cấu hình Web Search:** {last_search_err}"
                clean_answer += err_notice
                yield f"data: {json.dumps({'type': 'chunk', 'delta': err_notice}, ensure_ascii=False)}\n\n"
        final_refs = _resolve_referenced_files(user_docs, user_files, clean_answer, effective_scope, is_referential)

        if not is_fallback and not web_searched and not _is_no_info_response(clean_answer) and cache_key:
            _store_response_cache(cache_key, clean_answer, model_used, final_refs, sources=sources_list)

        yield f"data: {json.dumps({'type': 'done', 'answer': clean_answer, 'model_used': model_used, 'scope_used': effective_scope, 'referenced_files': final_refs, 'sources': sources_list, 'web_searched': web_searched, 'web_sources': web_sources}, ensure_ascii=False)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive"
    }
    return Response(stream_with_context(generate_sse()), mimetype="text/event-stream", headers=headers)


@app.route("/api/reset", methods=["POST"])
def reset():
    data = request.get_json() or {}
    session_id = (data.get("session_id") or "").strip()
    if session_id:
        _SESSION_FILES_CACHE.pop(session_id, None)
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


# Khởi tạo sẵn chỉ mục Markdown trong RAM khi nạp module để câu hỏi đầu tiên đạt tốc độ tức thì (< 2ms)
try:
    ensure_processed_docs_in_ram()
except Exception:
    pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    free_port(port)
    try:
        ensure_processed_docs_in_ram()
        get_vector_db()
    except Exception:
        pass
    print(f"\n{'='*60}")
    print(f"🎓 CHATBOT PTIT ĐANG CHẠY TẠI:")
    print(f"👉 http://127.0.0.1:{port}")
    print(f"{'='*60}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
