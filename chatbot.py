import os
import sys
import io
import re
import glob
import time
import warnings
import cv2
import numpy as np
import base64
import requests

# Tắt cảnh báo thư viện
warnings.filterwarnings("ignore")

# Đảm bảo in tiếng Việt chuẩn trên Windows console
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pymupdf
from PIL import Image
from google import genai
from google.genai import types
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from dotenv import load_dotenv

# Tải biến môi trường từ file .env
load_dotenv()

# Cấu hình Google GenAI Client (dùng SDK mới nhất: google-genai)
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
if not API_KEY:
    print("[!] Cảnh báo: Chưa tìm thấy GEMINI_API_KEY trong file .env hoặc biến môi trường!")


def get_genai_client(api_key=None):
    """Khởi tạo Google GenAI Client."""
    key = api_key or os.environ.get("GEMINI_API_KEY", API_KEY)
    return genai.Client(api_key=key)


client = get_genai_client() if API_KEY else None

# Danh sách model Vision & Chat ưu tiên (các model nhanh, ổn định đưa lên đầu, loại bỏ model gây chậm/treo)
VISION_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.7-flash",
    "gemini-3.6-flash"
]


def is_blank_page(page):
    """Kiểm tra xem trang có phải trang trắng / không có nội dung không."""
    try:
        text = page.get_text().strip()
        if len(text) > 0:
            return False
        pix = page.get_pixmap(dpi=72)
        arr = np.frombuffer(pix.samples, dtype=np.uint8)
        # Nếu hơn 98.5% pixel màu trắng sáng (>240)
        if (arr > 240).mean() > 0.985:
            return True
    except Exception:
        pass
    return False


def call_gemini_vision_rest(img_bytes, prompt, model_name, api_key=API_KEY, timeout=20):
    """
    Gọi trực tiếp Google Gemini REST API với timeout nghiêm ngặt (20s).
    Tránh hoàn toàn lỗi treo/đóng băng mạng (ssl.read) và cảnh báo AFC của SDK.
    """
    clean_model = model_name.replace("models/", "").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(img_bytes).decode("utf-8")
                    }
                }
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096
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
            return "*(Trang ảnh không chứa văn bản hoặc bảng biểu)*", None
        elif resp.status_code == 429:
            return None, "QUOTA_EXCEEDED"
        elif resp.status_code == 404:
            return None, f"MODEL_NOT_FOUND ({clean_model})"
        else:
            return None, f"HTTP {resp.status_code}: {resp.text[:120]}"
    except requests.exceptions.Timeout:
        return None, f"TIMEOUT ({timeout}s)"
    except Exception as e:
        return None, str(e)


def has_table_in_scan(page):
    """
    Sử dụng xử lý ảnh (OpenCV) nhận diện đường kẻ bảng và lưới ô trong trang scan.
    Trả về True nếu phát hiện cấu trúc bảng kẻ ô.
    """
    try:
        pix = page.get_pixmap(dpi=150)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Nhị phân hóa ảnh
        thresh = cv2.adaptiveThreshold(~gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, -2)

        # Tách các đường kẻ ngang và dọc
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (img.shape[1] // 30, 1))
        h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)

        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, img.shape[0] // 30))
        v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel)

        # Giao điểm tạo thành các góc ô bảng
        table_grid = cv2.bitwise_and(h_lines, v_lines)
        contours, _ = cv2.findContours(table_grid, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        # Có từ 4 giao điểm đường kẻ trở lên -> Có bảng biểu
        return len(contours) >= 4
    except Exception:
        return False


def classify_page(page):
    """
    Phân loại trang:
    - 'scan_table': Trang scan ảnh CÓ chứa bảng biểu
    - 'scan': Trang scan ảnh văn bản thông thường
    - 'table': Trang PDF số hóa có bảng biểu
    - 'text': Trang PDF số hóa văn bản thuần
    """
    text = page.get_text().strip()

    # 1. Trường hợp file PDF scan (ít hoặc không có text layer)
    if len(text) < 50:
        if has_table_in_scan(page):
            return "scan_table"
        return "scan"

    # 2. Trường hợp file PDF số hóa (Digital text)
    if len(page.find_tables().tables) > 0:
        return "table"

    keywords = ["bảng", "đơn vị", "địa chỉ", "học phí", "danh sách", "stt", "học phần", "tín chỉ"]
    if any(kw in text.lower() for kw in keywords):
        blocks = page.get_text("blocks")
        y_coords = [round(b[1], -1) for b in blocks]
        # Nhiều khối văn bản nằm cùng tọa độ hàng y -> Định dạng bảng
        if len(y_coords) - len(set(y_coords)) >= 3:
            return "table"

    # 3. Mặc định là văn bản thuần
    return "text"


def extract_with_vision(page, task="scan", max_retries=2):
    """Dùng Gemini Vision trích xuất nội dung từ ảnh, giữ nguyên cấu trúc bảng Markdown."""
    # 1. Kiểm tra nhanh nếu là trang trắng / không có nội dung
    if is_blank_page(page):
        return "*(Trang ảnh này hoàn toàn trắng và không chứa bất kỳ văn bản nào để trích xuất).*"

    # Nén trang sang JPEG chất lượng cao để truyền tải nhanh và ổn định
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("jpeg")

    # Chọn prompt chuyên dụng theo từng loại trang
    if task in ("scan_table", "table"):
        prompt = (
            "Bạn là chuyên gia trích xuất tài liệu tiếng Việt có bảng biểu.\n"
            "Hãy đọc và trích xuất ĐẦY ĐỦ, NGUYÊN VẸN toàn bộ nội dung trong trang tài liệu này:\n\n"
            "YÊU CẦU BẮT BUỘC:\n"
            "1. Giữ nguyên 100% tiếng Việt có dấu, tuyệt đối không sai hay mất dấu thanh.\n"
            "2. Trích xuất ĐẦY ĐỦ TẤT CẢ văn bản trong trang (tiêu đề, số hiệu, quốc hiệu tiêu ngữ, các câu/đoạn hành chính, thông tin sinh viên, lý do, cam đoan, chữ ký, ghi chú...).\n"
            "3. BẮT BUỘC CHUYỂN TOÀN BỘ BẢNG BIỂU THÀNH ĐỊNH DẠNG BẢNG MARKDOWN (Markdown table):\n"
            "   - Giữ nguyên tất cả các cột tiêu đề và hàng phân cấp.\n"
            "   - Giữ đúng từng ô dữ liệu, số tiền, đơn vị tính, không làm xáo trộn hay mất dòng.\n"
            "4. TUYỆT ĐỐI KHÔNG bỏ sót bất kỳ dòng văn bản nào ngoài bảng.\n"
            "5. Không tóm tắt, không thêm lời chào hay giải thích gì thêm."
        )
    else:  # scan văn bản thuần
        prompt = (
            "Bạn là hệ thống OCR tiếng Việt chuyên dụng. Hãy đọc và trích xuất toàn bộ văn bản trong ảnh scan này. "
            "Đảm bảo chính xác 100% tiếng Việt có dấu, giữ nguyên bố cục dòng. "
            "Nếu phát hiện bảng biểu, hãy giữ nguyên định dạng bảng Markdown. Không thêm lời giải thích."
        )

    # Thử lần lượt các model trong danh sách VISION_MODELS qua REST API với timeout nghiêm ngặt
    quota_exhausted_all = True
    for model_name in VISION_MODELS:
        for attempt in range(max_retries):
            text, err = call_gemini_vision_rest(img_bytes, prompt, model_name, api_key=API_KEY, timeout=20)
            if text:
                return text
            if err == "QUOTA_EXCEEDED":
                print(f"\n    [!] Model '{model_name}' chạm hạn mức (429), chuyển sang model tiếp theo...", end=" ", flush=True)
                break
            elif err and "TIMEOUT" in err:
                print(f"\n    [!] Model '{model_name}' phản hồi quá 20s (Timeout), chuyển model tiếp theo...", end=" ", flush=True)
                quota_exhausted_all = False
                break
            elif err and "MODEL_NOT_FOUND" in err:
                break
            else:
                quota_exhausted_all = False
                time.sleep(1)

    if quota_exhausted_all:
        print("\n    [!] Cảnh báo: Tất cả mô hình Gemini đều đã hết lượt dùng hôm nay.", end=" ", flush=True)
        return None

    # Nếu các model đều không nhận diện được chữ (ảnh đồ họa / trắng không chữ)
    return "*(Trang ảnh không chứa văn bản hoặc bảng biểu)*"


def process_page(page, page_num, page_type=None):
    """Xử lý từng trang: Text qua PyMuPDF, Bảng/Scan qua Vision LLM."""
    if page_type is None:
        page_type = classify_page(page)

    if page_type == "text":
        content = page.get_text().strip()
    else:
        # scan_table, table, scan đều dùng Vision LLM với prompt tối ưu tương ứng
        content = extract_with_vision(page, task=page_type)
        time.sleep(2)  # Nghỉ nhẹ tránh spam API

    return {
        "page": page_num,
        "type": page_type,
        "content": content
    }


def get_processed_pages(md_file):
    """Lấy tập hợp các số trang đã được xử lý và lưu trong file Markdown."""
    if not os.path.exists(md_file):
        return set()
    with open(md_file, "r", encoding="utf-8") as f:
        content = f.read()
    return set(map(int, re.findall(r"^## Trang (\d+)", content, re.MULTILINE)))


def is_file_processed(pdf_path, output_dir="processed_data"):
    """Kiểm tra file PDF đã được đọc và lưu đủ toàn bộ số trang hay chưa."""
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    md_file = os.path.join(output_dir, f"{base_name}.md")
    if not os.path.exists(md_file):
        return False
    try:
        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)
        doc.close()
        processed_pages = get_processed_pages(md_file)
        return len(processed_pages) >= total_pages
    except Exception:
        return False


def process_pdf(pdf_path, output_dir="processed_data", batch_size=5, max_pages=None, file_idx=1, total_files=1):
    """
    Xử lý file PDF theo batch 3-5 trang, xử lý xong đến đâu lưu ngay đến đấy, có log chi tiết.
    Chỉ lưu các trang đọc thành công, không lưu trang rỗng do lỗi API.
    """
    file_name = os.path.basename(pdf_path)
    base_name = os.path.splitext(file_name)[0]
    md_file = os.path.join(output_dir, f"{base_name}.md")

    doc = pymupdf.open(pdf_path)
    total_pages = min(len(doc), max_pages) if max_pages else len(doc)

    # Lấy các trang chưa được xử lý để không đọc lại
    processed_pages = get_processed_pages(md_file)
    remaining_pages = [p for p in range(1, total_pages + 1) if p not in processed_pages]

    if not remaining_pages:
        print(f"[{file_idx}/{total_files}] File: {file_name} -> Đã hoàn thành 100% ({total_pages}/{total_pages} trang), bỏ qua.")
        doc.close()
        return

    # Khởi tạo header tài liệu nếu file Markdown chưa có
    if not os.path.exists(md_file):
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(f"# Tài liệu: {file_name}\n\n")

    print(f"\n{'='*60}")
    print(f"[{file_idx}/{total_files}] ĐANG XỬ LÝ FILE: {file_name} ({total_pages} trang)")
    if processed_pages:
        print(f"[*] Tiếp tục từ các trang còn thiếu: {len(remaining_pages)}/{total_pages} trang")
    print(f"{'='*60}")

    total_batches = (len(remaining_pages) + batch_size - 1) // batch_size
    consecutive_failures = 0

    for b_idx in range(0, len(remaining_pages), batch_size):
        batch = remaining_pages[b_idx : b_idx + batch_size]
        batch_num = (b_idx // batch_size) + 1

        print(f"\n-> [Batch {batch_num}/{total_batches}] Xử lý các trang: {batch}")
        batch_results = []

        for page_num in batch:
            page = doc[page_num - 1]
            page_type = classify_page(page)
            print(f"   [{file_name}] Đang đọc Trang {page_num:2d}/{total_pages} [{page_type.upper():10s}]...", end=" ", flush=True)

            res = process_page(page, page_num, page_type=page_type)

            # Kiểm tra kết quả: chỉ chấp nhận khi đọc thành công (không phải None)
            if res["content"] is not None and len(res["content"]) > 0:
                batch_results.append(res)
                consecutive_failures = 0
                print(f"Xong ({len(res['content'])} ký tự)")
            else:
                consecutive_failures += 1
                print(f"Thất bại (Không đọc được ký tự do lỗi API/hạn mức)")

                # Nếu liên tiếp 2 trang đều lỗi hết quota -> Tạm dừng file để tránh spam API
                if consecutive_failures >= 2:
                    print(f"\n[!] Tạm dừng file {file_name}: API đã hết hạn mức. Hãy thử lại sau hoặc đổi API Key.")
                    break

        # Chỉ ghi đĩa nếu có ít nhất 1 trang đọc thành công trong batch
        if batch_results:
            with open(md_file, "a", encoding="utf-8") as f:
                for r in batch_results:
                    f.write(f"## Trang {r['page']} - [{r['type'].upper()}]\n\n")
                    f.write(r["content"] + "\n\n---\n\n")

            saved_pages = [r["page"] for r in batch_results]
            print(f"   => [ĐÃ LƯU] Thành công {len(saved_pages)} trang: {saved_pages} vào: {md_file}")

        if consecutive_failures >= 2:
            break

    doc.close()
    print(f"\n[✓] Kết thúc lượt xử lý file: {file_name}")


def process_data_folder(data_dir="data", output_dir="processed_data", batch_size=5, max_pages_per_file=None, force=False):
    """Xử lý toàn bộ các file PDF trong thư mục data theo batch và lưu kết quả Markdown."""
    os.makedirs(output_dir, exist_ok=True)
    pdf_files = glob.glob(os.path.join(data_dir, "*.pdf"))

    if not pdf_files:
        print(f"[!] Không tìm thấy file PDF trong: {data_dir}")
        return

    total_files = len(pdf_files)
    print(f"[*] Tìm thấy {total_files} file PDF trong thư mục '{data_dir}'. Bắt đầu xử lý...")

    for idx, pdf_path in enumerate(pdf_files, start=1):
        if not force and is_file_processed(pdf_path, output_dir):
            print(f"\n[i] [{idx}/{total_files}] Bỏ qua file đã hoàn thành: {os.path.basename(pdf_path)}")
            continue

        process_pdf(
            pdf_path=pdf_path,
            output_dir=output_dir,
            batch_size=batch_size,
            max_pages=max_pages_per_file,
            file_idx=idx,
            total_files=total_files
        )

    print(f"\n{'='*60}")
    print(f"[✓] ĐÃ HOÀN TẤT LƯỢT XỬ LÝ DỮ LIỆU!")
    print(f"{'='*60}")


# ==============================================================================
# PHẦN 2: CHUNKING, EMBEDDING VÀ VECTOR DATABASE (CHROMADB)
# ==============================================================================

CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "httm_knowledge_base"
EMBEDDING_MODEL_NAME = "models/gemini-embedding-001"


def get_vector_db():
    """Khởi tạo hoặc kết nối tới ChromaDB collection lưu trữ vector trên ổ đĩa."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    return collection


def get_embedding_model():
    """Khởi tạo mô hình Google Generative AI Embeddings."""
    return GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL_NAME,
        google_api_key=API_KEY
    )


def chunk_markdown_file(md_file_path, chunk_size=1000, chunk_overlap=150):
    """
    Băm nhỏ file Markdown thành các chunk có kích thước phù hợp cho RAG.
    Giữ nguyên ngữ cảnh tên file, số trang và loại trang trong từng chunk.
    Đảm bảo 100% ID chunk là duy nhất và không bị trùng lặp.
    """
    with open(md_file_path, "r", encoding="utf-8") as f:
        content = f.read()

    base_name = os.path.basename(md_file_path)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = []

    # Tìm tất cả các phân đoạn trang bắt đầu bằng ## Trang X - [LOẠI_TRANG]
    page_matches = list(re.finditer(r"^## Trang (\d+) - \[([^\]]+)\]", content, flags=re.MULTILINE))

    if page_matches:
        for i, match in enumerate(page_matches):
            page_num = int(match.group(1))
            page_type = match.group(2)
            start_pos = match.end()
            end_pos = page_matches[i + 1].start() if i + 1 < len(page_matches) else len(content)

            body = content[start_pos:end_pos].strip()
            body = re.sub(r"---\s*$", "", body).strip()
            if not body:
                continue

            sub_chunks = splitter.split_text(body)
            for c_idx, sc in enumerate(sub_chunks, start=1):
                chunk_id = f"{base_name}_p{page_num}_c{c_idx}"
                doc_text = f"[{base_name} | Trang {page_num} | {page_type}]\n{sc}"
                chunks.append({
                    "id": chunk_id,
                    "document": doc_text,
                    "metadata": {
                        "source": base_name,
                        "page": page_num,
                        "type": page_type,
                        "chunk_id": chunk_id
                    }
                })
    else:
        # File không có phân trang ## Trang, băm toàn bộ file
        sub_chunks = splitter.split_text(content.strip())
        for c_idx, sc in enumerate(sub_chunks, start=1):
            chunk_id = f"{base_name}_p1_c{c_idx}"
            doc_text = f"[{base_name} | Trang 1 | TEXT]\n{sc}"
            chunks.append({
                "id": chunk_id,
                "document": doc_text,
                "metadata": {
                    "source": base_name,
                    "page": 1,
                    "type": "TEXT",
                    "chunk_id": chunk_id
                }
            })

    return chunks


def embed_markdown_files(processed_dir="processed_data", batch_size=15, force_reembed_file=None):
    """
    Xử lý các file .md trong thư mục processed_data:
    - Băm nhỏ (chunking)
    - Tạo vector embedding
    - Lưu vào ChromaDB
    - Tự động bỏ qua các file hoặc chunk đã được nhúng trước đó để tránh trùng lặp.
    - Hỗ trợ xóa và nhúng lại nếu truyền force_reembed_file.
    """
    md_files = sorted(glob.glob(os.path.join(processed_dir, "*.md")))
    if not md_files:
        print(f"[!] Không tìm thấy file Markdown nào trong: {processed_dir}")
        return

    print(f"\n{'='*60}")
    print(f"[*] BẮT ĐẦU QUÁ TRÌNH CHUNKING & EMBEDDING VÀO CHROMADB")
    print(f"{'='*60}")

    collection = get_vector_db()
    embedding_model = get_embedding_model()

    if force_reembed_file:
        target_name = os.path.basename(force_reembed_file)
        try:
            collection.delete(where={"source": target_name})
            print(f"[*] Đã xóa các vector chunks cũ của '{target_name}' để cập nhật nội dung mới.")
        except Exception as e:
            print(f"[!] Lỗi khi xóa chunk cũ của {target_name}: {e}")

    # Lấy toàn bộ ID đã có trong ChromaDB để tránh xử lý lại
    existing_ids = set(collection.get()["ids"])
    print(f"[*] Hiện có {len(existing_ids)} chunks đã lưu trong ChromaDB.")

    total_files = len(md_files)
    for idx, md_path in enumerate(md_files, start=1):
        base_name = os.path.basename(md_path)
        all_chunks = chunk_markdown_file(md_path)

        # Lọc ra các chunk chưa có trong database
        new_chunks = [c for c in all_chunks if c["id"] not in existing_ids]

        if not new_chunks:
            print(f"\n[i] [{idx}/{total_files}] File '{base_name}': Đã nhúng đủ {len(all_chunks)}/{len(all_chunks)} chunks -> BỎ QUA.")
            continue

        print(f"\n[*] [{idx}/{total_files}] File '{base_name}': Cần nhúng {len(new_chunks)}/{len(all_chunks)} chunks mới.")

        # Xử lý theo từng batch nhỏ (tránh chạm giới hạn rate limit 100-150 req/phút)
        total_batches = (len(new_chunks) + batch_size - 1) // batch_size
        for b_idx in range(0, len(new_chunks), batch_size):
            batch = new_chunks[b_idx : b_idx + batch_size]
            batch_num = (b_idx // batch_size) + 1

            batch_ids = [c["id"] for c in batch]
            batch_texts = [c["document"] for c in batch]
            batch_metas = [c["metadata"] for c in batch]

            # Nhúng vector với cơ chế retry nếu gặp 429
            for attempt in range(3):
                try:
                    embeddings = embedding_model.embed_documents(batch_texts)
                    collection.add(
                        ids=batch_ids,
                        documents=batch_texts,
                        embeddings=embeddings,
                        metadatas=batch_metas
                    )
                    existing_ids.update(batch_ids)
                    print(f"    + [Batch {batch_num}/{total_batches}] Đã nhúng & lưu chunks {b_idx + 1} - {b_idx + len(batch)} / {len(new_chunks)}")
                    time.sleep(1)  # Nghỉ nhẹ giữa các batch
                    break
                except Exception as e:
                    err_msg = str(e)
                    if "429" in err_msg or "quota" in err_msg.lower():
                        wait_time = 20 * (attempt + 1)
                        print(f"    [!] Chạm giới hạn Embedding API, đợi {wait_time}s rồi tiếp tục...")
                        time.sleep(wait_time)
                    else:
                        print(f"    [!] Lỗi khi nhúng batch: {e}")
                        break

        print(f"[✓] Đã hoàn thành nhúng file: '{base_name}'")

    print(f"\n{'='*60}")
    print(f"[✓] HOÀN TẤT TẤT CẢ FILE MARKDOWN VÀO VECTOR DB! (Tổng chunks hiện tại: {collection.count()})")
    print(f"{'='*60}")


# ==============================================================================
# PHẦN 3: HỎI ĐÁP / TRUY VẤN RAG (CHATBOT ENGINE)
# ==============================================================================

def query_knowledge_base(query, n_results=4):
    """Tìm kiếm các đoạn văn bản liên quan nhất từ Vector DB theo câu hỏi."""
    collection = get_vector_db()
    embedding_model = get_embedding_model()

    q_vec = embedding_model.embed_query(query)
    results = collection.query(
        query_embeddings=[q_vec],
        n_results=n_results
    )

    matched_docs = []
    if results and results["documents"]:
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            matched_docs.append({
                "content": doc,
                "source": meta.get("source"),
                "page": meta.get("page"),
                "type": meta.get("type")
            })
    return matched_docs


def call_gemini_text_rest(prompt, model_name, api_key=API_KEY, timeout=10):
    """Gọi trực tiếp Google Gemini REST API cho text với timeout 10s."""
    clean_model = model_name.replace("models/", "").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048}
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
            return None, "Empty response"
        return None, f"HTTP {resp.status_code}"
    except Exception as e:
        return None, str(e)


def ask_chatbot(question, n_results=4):
    """Trả lời câu hỏi bằng cách kết hợp Vector Search (RAG) và Gemini LLM."""
    print(f"\n[?] Câu hỏi: {question}")

    try:
        from app import safe_query_knowledge_base, expand_context_for_tables
        docs = safe_query_knowledge_base(question, n_results=n_results)
        docs = expand_context_for_tables(question, docs)
    except Exception:
        docs = query_knowledge_base(question, n_results=n_results)

    if not docs:
        print("[!] Không tìm thấy thông tin phù hợp trong cơ sở tri thức.")
        return ""

    # Ghép ngữ cảnh từ các đoạn tìm được
    context_parts = []
    for i, d in enumerate(docs, start=1):
        context_parts.append(f"--- [TÀI LIỆU {i}: {d['source']} (Trang {d['page']})] ---\n{d['content']}")
    context_str = "\n\n".join(context_parts)

    prompt = f"""
Bạn là Trợ lý Ảo Thông Minh của Học viện Công nghệ Bưu chính Viễn thông (PTIT).
Dưới đây là thông tin trích xuất từ tài liệu chính thức của Học viện:

{context_str}

CÂU HỎI CỦA NGƯỜI DÙNG: {question}

CÁC NGUYÊN TẮC BẮT BUỘC KHI TRẢ LỜI:
1. TRẢ LỜI ĐÚNG TRỌNG TÂM - TUYỆT ĐỐI KHÔNG LẠC ĐỀ:
   - Nếu câu hỏi về MÔN HỌC / HỌC PHẦN / CHƯƠNG TRÌNH ĐÀO TẠO: TUYỆT ĐỐI KHÔNG ĐƯA BẢNG MỨC THU HỌC PHÍ hay số tiền học phí.
   - Nếu câu hỏi về HỌC PHÍ / MỨC THU: Trả lời về biểu phí, số tiền, khóa học theo quy định học phí.
   - Nếu câu hỏi về HỌC BỔNG / ĐIỂM CHUẨN HỌC BỔNG: Trả lời về điểm TBCMR (GPA), điểm rèn luyện (ĐRL) và số tiền học bổng theo đúng ngành, khóa và cơ sở đào tạo.

2. KHI TRẢ LỜI VỀ MÔN HỌC / HỌC PHẦN / KẾ HOẠCH HỌC TẬP:
   - Cung cấp đầy đủ, chính xác các thông tin có trong tài liệu:
     + Tên môn học chính xác
     + Mã môn học (Mã HP, ví dụ: INT14151, INT1404...)
     + Số tín chỉ (TC)
     + Học kỳ giảng dạy (HK)
     + Môn học tiên quyết (nếu có trong tài liệu, ví dụ: INT1340)
     + Số tiết: Lý thuyết, Bài tập/Thảo luận, Tự học
     + Thuộc chuyên ngành / hướng chuyên sâu nào (ví dụ: Công nghệ phần mềm, Hệ thống thông tin...)
   - Khi người dùng hỏi về một môn cụ thể (ví dụ: "Phát triển các hệ thống thông minh"): Hãy trả lời trực tiếp và đầy đủ các thông số của môn học đó. Nếu có các môn học tương tự hoặc cùng nhóm liên quan trong khung đào tạo, có thể liệt kê thêm bên dưới để hỗ trợ sinh viên.

3. KHI TRẢ LỜI VỀ HỌC PHÍ:
   - Khi hỏi về học phí trong một năm học mà không chỉ rõ khóa: Liệt kê đầy đủ từng khóa (Khóa 2021, 2022, 2023, 2024, 2025...) và tất cả các chương trình đào tạo có trong tài liệu.
   - Bảng Markdown chuẩn gồm các cột:
     | STT | Chương trình đào tạo | Ngành / Chuyên ngành | Khóa tuyển sinh | Đơn vị tính | Mức thu học phí |
   - Cột STT bắt buộc phải đánh số liên tục: 1, 2, 3...

4. KHI TRẢ LỜI VỀ HỌC BỔNG KHUYẾN KHÍCH HỌC TẬP (HK1 NĂM HỌC 2025 - 2026):
   - Phân biệt rõ ràng giữa 2 cơ sở đào tạo:
     + Cơ sở Hà Nội (Phía Bắc): Điểm chuẩn TBCMR (GPA hệ 4) và Điểm Rèn luyện (ĐRL) cho từng loại (Xuất sắc, Giỏi, Khá).
     + Cơ sở TP. Hồ Chí Minh (Phía Nam): Điểm chuẩn TBCMR (GPA hệ 4) và Điểm Rèn luyện (ĐRL) cho từng loại (Xuất sắc, Giỏi, Khá).
   - Nếu trong bảng có dấu gạch ngang (-) cho một mức học bổng (ví dụ mức Khá), nêu rõ cơ sở đó không xét / không có mức điểm chuẩn cho loại học bổng này.
   - Nêu rõ số tiền học bổng tương ứng từng loại (Xuất sắc, Giỏi, Khá) bằng đơn vị VNĐ (Ví dụ: 17.480 nghìn đồng = 17.480.000 đ, 19.228 nghìn đồng = 19.228.000 đ, 20.976 nghìn đồng = 20.976.000 đ).

5. TUYỆT ĐỐI KHÔNG TRÍCH DẪN NGUỒN TÊN FILE TRONG VĂN BẢN:
   - KHÔNG nhắc đến tên file nội bộ (hp_2025.md, mon_hoc.md, ct_cntt.md, HB_HK1_25-26.md...), KHÔNG nhắc số trang tài liệu, KHÔNG tạo mục "Nguồn tài liệu tham khảo".

6. ĐỊNH DẠNG VĂN BẢN VÀ KÝ HIỆU TOÁN HỌC (RẤT QUAN TRỌNG):
   - TUYỆT ĐỐI KHÔNG sử dụng ký hiệu LaTeX toán học như $\ge$, $\le$, $\times$ hay bao bọc bởi dấu $.
   - Hãy viết tự nhiên bằng tiếng Việt: "từ 3,60 trở lên", "từ 90 trở lên" hoặc dùng ký hiệu phổ thông ">= 3,60", ">= 90".

7. KHI TRẢ LỜI VỀ MẪU ĐƠN SINH VIÊN (VẮNG THI, NGHỈ HỌC, THÔI HỌC, XIN ĐỔI CA THI, XIN HOÃN THI...):
   - Cung cấp toàn bộ mẫu đơn nguyên vẹn, chi tiết, đầy đủ từng phần: Quốc hiệu tiêu ngữ, Kính gửi, Thông tin sinh viên (Họ tên, Mã SV, Lớp, SĐT...), Bảng danh sách học phần/môn học (nếu có), Lý do chi tiết, Lời cam đoan, phần Chữ ký của sinh viên và phần Xác nhận/Duyệt của các phòng ban liên quan (Khoa, Phòng Đào tạo, Trung tâm KT&ĐBCLGD...).
   - TUYỆT ĐỐI KHÔNG chỉ trích xuất vài dòng kẻ bảng cụt lủn hoặc bỏ sót nội dung mẫu đơn. Trình bày biểu mẫu rõ ràng, cân đối bằng văn bản hoặc bảng Markdown để sinh viên có thể sao chép hoặc in ra sử dụng ngay.

8. VĂN PHONG RÕ RÀNG, CHUẨN XÁC, THÂN THIỆN:
   - Đi thẳng vào nội dung cần trả lời.
"""

    for m_name in VISION_MODELS:
        answer, err = call_gemini_text_rest(prompt, m_name, API_KEY, timeout=10)
        if answer:
            try:
                from app import clean_llm_response
                answer = clean_llm_response(answer)
            except Exception:
                pass
            print(f"\n[Chatbot Trả lời]:\n{answer}\n")
            return answer

    # Fallback nếu LLM bận hoặc hết quota
    try:
        from app import synthesize_targeted_answer
        fallback_ans = synthesize_targeted_answer(question, docs)
        if fallback_ans:
            print(f"\n[Chatbot Trả lời (Fallback)]:\n{fallback_ans}\n")
            return fallback_ans
    except Exception:
        pass

    print("[!] Không thể tạo câu trả lời do hết hạn mức API.")
    return ""


if __name__ == "__main__":
    # Kiểm tra nếu người dùng muốn khởi chạy giao diện Web
    if "--web" in sys.argv or "--ui" in sys.argv or "-w" in sys.argv:
        from app import app
        port = int(os.environ.get("PORT", 5000))
        print(f"\n{'='*60}")
        print(f"🎓 ĐANG KHỞI CHẠY GIAO DIỆN WEB PTIT ASSISTANT...")
        print(f"👉 Mở trình duyệt tại: http://127.0.0.1:{port}")
        print(f"{'='*60}\n")
        app.run(host="0.0.0.0", port=port, debug=False)
        sys.exit(0)

    process_data_folder(
        data_dir="data",
        output_dir="processed_data",
        batch_size=5,
        max_pages_per_file=None
    )
    # 1. Đọc và nhúng các file Markdown trong processed_data vào Vector DB
    # Tự động bỏ qua các file hoặc chunk đã nhúng trước đó
    embed_markdown_files(processed_dir="processed_data", batch_size=15)

    print("\n" + "="*60)
    print("✅ ĐÃ HOÀN TẤT XỬ LÝ VÀ NHÚNG TÀI LIỆU VÀO CƠ SỞ TRI THỨC!")
    print("💡 Khởi chạy giao diện Web bằng lệnh: python app.py")
    print("="*60 + "\n")


