import os
import io
import re
import time
import requests
import pymupdf
import docx
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Cấu hình giới hạn tài liệu tải lên
MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_FILES_PER_SESSION = 3
MAX_PDF_PAGES = 25
MAX_TEXT_CHARS = 50000  # Tương đương ~25 trang A4 chuẩn (350-400 từ/trang)
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def is_allowed_file(filename):
    """Kiểm tra phần mở rộng file có hợp lệ hay không."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def parse_pdf(file_bytes, filename):
    """
    Trích xuất text từ file PDF.
    Kiểm tra giới hạn 25 trang và cảnh báo nếu là PDF dạng scan (không có text).
    """
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        raise ValueError(f"Không thể đọc file PDF '{filename}': {str(e)}")

    total_pages = len(doc)
    if total_pages > MAX_PDF_PAGES:
        raise ValueError(
            f"File '{filename}' có {total_pages} trang, vượt quá giới hạn tối đa {MAX_PDF_PAGES} trang cho phép."
        )

    pages_data = []
    total_chars = 0

    for page_idx in range(total_pages):
        page = doc[page_idx]
        text = page.get_text("text").strip()
        if text:
            pages_data.append({"page": page_idx + 1, "text": text})
            total_chars += len(text)

    if total_chars < 40:
        raise ValueError(
            f"File '{filename}' không chứa văn bản có thể trích xuất (có thể là file scan dạng ảnh hoặc trang trống). "
            f"Vui lòng sử dụng file có văn bản có thể bôi đen copy được."
        )

    return pages_data


def parse_docx(file_bytes, filename):
    """
    Trích xuất text và bảng biểu từ file DOCX.
    Kiểm tra giới hạn tương đương 25 trang (50.000 ký tự).
    """
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
    except Exception as e:
        raise ValueError(f"Không thể đọc file Word '{filename}': {str(e)}")

    full_text_parts = []

    # 1. Trích xuất các đoạn văn bản (paragraphs)
    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt:
            full_text_parts.append(txt)

    # 2. Trích xuất bảng biểu trong file DOCX
    for table in doc.tables:
        table_rows = []
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                table_rows.append(f"| {row_text} |")
        if table_rows:
            full_text_parts.append("\n".join(table_rows))

    combined_text = "\n\n".join(full_text_parts).strip()
    if not combined_text:
        raise ValueError(f"File Word '{filename}' không có nội dung văn bản.")

    if len(combined_text) > MAX_TEXT_CHARS:
        raise ValueError(
            f"File Word '{filename}' chứa {len(combined_text):,} ký tự, vượt quá giới hạn tương đương 25 trang "
            f"({MAX_TEXT_CHARS:,} ký tự)."
        )

    return [{"page": 1, "text": combined_text}]


def parse_plain_text(file_bytes, filename):
    """
    Trích xuất text từ file .txt hoặc .md.
    Hỗ trợ fallback encoding và kiểm tra giới hạn 50.000 ký tự.
    """
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "utf-16"]
    text = None
    for enc in encodings:
        try:
            text = file_bytes.decode(enc).strip()
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if text is None:
        raise ValueError(f"Không thể giải mã nội dung file văn bản '{filename}'. Vui lòng lưu file ở định dạng UTF-8.")

    if not text:
        raise ValueError(f"File văn bản '{filename}' rỗng, không có nội dung.")

    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(
            f"File '{filename}' chứa {len(text):,} ký tự, vượt quá giới hạn tương đương 25 trang "
            f"({MAX_TEXT_CHARS:,} ký tự)."
        )

    return [{"page": 1, "text": text}]


def extract_chunks_from_document(file_bytes, filename):
    """
    Hàm điều phối: Kiểm tra định dạng, trích xuất text và thực hiện chunking.
    Trả về danh sách các chunks kèm metadata.
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Định dạng '{ext}' không được hỗ trợ. Hệ thống chỉ hỗ trợ: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )

    if ext == ".pdf":
        pages = parse_pdf(file_bytes, filename)
    elif ext == ".docx":
        pages = parse_docx(file_bytes, filename)
    else:  # .txt, .md
        pages = parse_plain_text(file_bytes, filename)

    # Chunking: RecursiveCharacterTextSplitter 1000 ký tự, overlap 150
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    all_chunks = []
    chunk_index = 0

    for p in pages:
        page_num = p["page"]
        raw_text = p["text"]
        chunks = splitter.split_text(raw_text)
        for c in chunks:
            c_clean = c.strip()
            if len(c_clean) >= 20:  # Bỏ qua chunk rác quá ngắn
                all_chunks.append({
                    "chunk_id": f"{filename}_p{page_num}_c{chunk_index}",
                    "text": c_clean,
                    "filename": filename,
                    "page": page_num,
                    "chunk_index": chunk_index
                })
                chunk_index += 1

    if not all_chunks:
        raise ValueError(f"Không thể tạo đoạn trích xuất hợp lệ từ file '{filename}'.")

    return all_chunks


# ==============================================================================
# BATCH EMBEDDING GEMINI REST API (GỬI 50-100 CHUNKS / REQUEST)
# ==============================================================================

def batch_get_embeddings(texts, api_key, batch_size=50, timeout=20.0):
    """
    Gọi Gemini Batch Embedding API để mã hóa mảng các đoạn text.
    Tốc độ siêu nhanh: mã hóa 100-150 chunks chỉ trong 1-2 giây.
    """
    if not texts:
        return []

    clean_key = (api_key or "").strip()
    if not clean_key:
        clean_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents?key={clean_key}"
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        payload = {
            "requests": [
                {
                    "model": "models/gemini-embedding-001",
                    "content": {"parts": [{"text": t}]}
                }
                for t in batch
            ]
        }
        headers = {"Content-Type": "application/json"}

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                embeddings_data = data.get("embeddings", [])
                for item in embeddings_data:
                    values = item.get("values", [])
                    if values:
                        all_embeddings.append(values)
                    else:
                        all_embeddings.append(None)
            else:
                # Fallback: Gọi đơn lẻ nếu batch trả về lỗi
                for t in batch:
                    single_vec = _get_single_embedding(t, clean_key, timeout=5.0)
                    all_embeddings.append(single_vec)
        except Exception:
            for t in batch:
                single_vec = _get_single_embedding(t, clean_key, timeout=5.0)
                all_embeddings.append(single_vec)

    return all_embeddings


def _get_single_embedding(text, api_key, timeout=5.0):
    """Fallback gọi embedContent đơn lẻ khi batch gặp sự cố."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={api_key}"
    payload = {"content": {"parts": [{"text": text}]}}
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("embedding", {}).get("values")
    except Exception:
        pass
    return None

