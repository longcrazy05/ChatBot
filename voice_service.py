"""
Module Voice Service: Xử lý Text-to-Speech (TTS) với Edge-TTS Neural Voice,
dự phòng gTTS (Google Translate TTS) và Speech-to-Text (STT) Fallback với Google Gemini Audio API.
"""

import os
import re
import time
import uuid
import hashlib
import asyncio
import threading
import edge_tts
from gtts import gTTS
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_CACHE_DIR = os.path.join(BASE_DIR, "static", "audio_cache")
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

# Circuit Breaker cho Edge-TTS (Tránh bị treo chờ 15s-20s nếu Microsoft Bing ngắt kết nối)
EDGE_TTS_TIMEOUT = 2.0  # Giới hạn tối đa 2 giây cho Edge-TTS
EDGE_TTS_COOLDOWN = 180  # Nếu lỗi, tạm ngừng thử Edge-TTS trong 3 phút, chuyển thẳng gTTS siêu tốc
_edge_tts_disabled_until = 0.0

# Khóa theo từng file MP3 để các request trùng câu không ghi chồng lên nhau
_file_locks = {}
_file_locks_guard = threading.Lock()


def _get_file_lock(path):
    with _file_locks_guard:
        lock = _file_locks.get(path)
        if lock is None:
            lock = _file_locks[path] = threading.Lock()
        return lock

# Bảng tra từ viết tắt và thuật ngữ chuyên ngành PTIT sang văn bản phát âm tự nhiên
PTIT_ABBREVIATIONS = [
    (r"\bPTIT\b", "Học viện Bưu chính Viễn thông"),
    (r"\bCNTT\b", "Công nghệ thông tin"),
    (r"\bATTT\b", "An toàn thông tin"),
    (r"\bDTVT\b|\bĐTVT\b", "Điện tử viễn thông"),
    (r"\bKTPM\b", "Kỹ thuật phần mềm"),
    (r"\bKHMT\b", "Khoa học máy tính"),
    (r"\bTMĐT\b", "Thương mại điện tử"),
    (r"\bTKĐPT\b|\bĐPT\b", "Đa phương tiện"),
    (r"\bCLC\b", "Chất lượng cao"),
    (r"(\d+)\s*(TC|tc|tín chỉ)\b", r"\1 tín chỉ"),
    (r"\bTC\b", "tín chỉ"),
    (r"\bHK1\b|\bHK\s*1\b|\bHKI\b", "Học kỳ một"),
    (r"\bHK2\b|\bHK\s*2\b|\bHKII\b", "Học kỳ hai"),
    (r"\bHK3\b|\bHK\s*3\b|\bHKIII\b", "Học kỳ ba"),
    (r"\bĐTB\b|\bGPA\b", "Điểm trung bình"),
    (r"\bSV\b", "sinh viên"),
    (r"\bGV\b", "giảng viên"),
    (r"\bKHTN\b", "Khoa học tự nhiên"),
    (r"\bGDTC\b", "Giáo dục thể chất"),
    (r"\bGDQP\b|\bGDQP-AN\b", "Giáo dục quốc phòng an ninh"),
    (r"\bTHPT\b", "Trung học phổ thông"),
    (r"\bĐH\b", "Đại học"),
    (r"\bCĐ\b", "Cao đẳng"),
    (r"\bNCS\b", "Nghiên cứu sinh"),
    (r"\bThS\b", "Thạc sĩ"),
    (r"\bTS\b", "Tiến sĩ"),
    (r"\bPGS\b", "Phó giáo sư"),
    (r"\bGS\b", "Giáo sư"),
]

def format_currency_match(match):
    """Chuyển chuỗi tiền tệ dạng 12.500.000 VNĐ thành văn bản phát âm tiếng Việt."""
    num_str = match.group(1).replace(".", "").replace(",", "").strip()
    try:
        val = int(num_str)
        if val >= 1_000_000:
            trieu = val // 1_000_000
            du = val % 1_000_000
            nghin = du // 1_000
            if nghin > 0:
                return f"{trieu} triệu {nghin} nghìn đồng"
            return f"{trieu} triệu đồng"
        elif val >= 1_000:
            nghin = val // 1_000
            return f"{nghin} nghìn đồng"
        else:
            return f"{val} đồng"
    except Exception:
        return match.group(0)


def clean_and_normalize_text(text: str) -> str:
    """
    Tiền xử lý văn bản:
    1. Lọc bỏ Markdown (tiêu đề, bảng biểu, danh sách, links, code, latex)
    2. Chuẩn hóa từ viết tắt PTIT
    3. Chuẩn hóa số tiền và các ký hiệu toán học
    """
    if not text:
        return ""

    s = text

    # Loại bỏ code blocks ```...``` và inline code `...`
    s = re.sub(r"```[\s\S]*?```", " ", s)
    s = re.sub(r"`[^`]*`", " ", s)

    # Loại bỏ bảng biểu markdown: | col1 | col2 |
    s = re.sub(r"\|[^\n]+\|", " ", s)
    s = re.sub(r"[-:]{2,}\s*\|\s*[-:]{2,}", " ", s)

    # Loại bỏ link markdown [text](url) -> text, link hình ảnh ![alt](url) -> ""
    s = re.sub(r"!\[.*?\]\(.*?\)", " ", s)
    s = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", s)
    s = re.sub(r"https?://\S+", " ", s)

    # Loại bỏ LaTeX math syntax $...$
    s = re.sub(r"\$\s*\\ge(q)?\s*([^$]+)\$", r"từ \2 trở lên", s)
    s = re.sub(r"\$\s*\\le(q)?\s*([^$]+)\$", r"dưới hoặc bằng \2", s)
    s = re.sub(r"\\ge(q)?\b", " lớn hơn hoặc bằng ", s)
    s = re.sub(r"\\le(q)?\b", " nhỏ hơn hoặc bằng ", s)
    s = re.sub(r"\$([^$]+)\$", r"\1", s)
    s = re.sub(r"\$", " ", s)

    # Loại bỏ tiêu đề markdown #, ##, ###, bullet points *, -, +
    s = re.sub(r"^#{1,6}\s*", " ", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*[-*+]\s+", " ", s, flags=re.MULTILINE)
    s = re.sub(r"[*_~><#]", " ", s)

    # Loại bỏ thẻ HTML thừa
    s = re.sub(r"<[^>]+>", " ", s)

    # Chuẩn hóa tiền tệ: ví dụ 15.000.000 VNĐ, 550.000 đ, 500,000 VND
    s = re.sub(r"(\d{1,3}(?:[.,]\d{3})+)\s*(?:VNĐ|VND|đ|dong|đồng)\b", format_currency_match, s, flags=re.IGNORECASE)

    # Mở rộng các từ viết tắt chuyên ngành PTIT
    for pattern, replacement in PTIT_ABBREVIATIONS:
        s = re.sub(pattern, replacement, s)

    # Thay thế một số ký hiệu thường gặp
    s = s.replace("/", " trên ")
    s = s.replace("%", " phần trăm ")
    s = s.replace("&", " và ")
    s = s.replace("@", " a còng ")
    s = re.sub(r"\s+", " ", s).strip()

    return s


async def _synthesize_edge_tts(text: str, voice: str, output_path: str):
    """Thực thi gọi Edge-TTS bất đồng bộ với giới hạn timeout ngắn để không làm treo hệ thống."""
    communicate = edge_tts.Communicate(text, voice)
    # Giới hạn timeout 2.0s: nếu Bing không phản hồi lập tức thì hủy để chuyển gTTS
    await asyncio.wait_for(communicate.save(output_path), timeout=EDGE_TTS_TIMEOUT)


def generate_speech(text: str, voice: str = "vi-VN-HoaiMyNeural") -> dict:
    """
    Tạo file giọng nói MP3:
    1. Ưu tiên: Microsoft Edge-TTS (Neural Voice tiếng Việt Bắc Bộ - Hoài My / Nam Minh).
    2. Dự phòng tức thì: Google Translate TTS (gTTS tiếng Việt) kèm Circuit Breaker.
    3. Bộ nhớ đệm (Cache MD5) để tái sử dụng ngay lập tức mà không gọi lại API.
    """
    global _edge_tts_disabled_until

    clean_text = clean_and_normalize_text(text)
    if not clean_text:
        return {"error": "Văn bản rỗng sau khi chuẩn hóa."}

    # Giới hạn giọng đọc tiếng Việt hợp lệ
    valid_voices = {
        "vi-VN-HoaiMyNeural": "Giọng Nữ (Hoài My - Bắc Bộ)",
        "vi-VN-NamMinhNeural": "Giọng Nam (Nam Minh - Bắc Bộ)"
    }
    # "google-vi": ép dùng giọng Google Tiếng Việt (gTTS) cho lựa chọn giọng Nữ trên Chrome
    force_gtts = (voice == "google-vi")
    if voice not in valid_voices and not force_gtts:
        voice = "vi-VN-HoaiMyNeural"

    # Tạo mã băm MD5 duy nhất cho nội dung và giọng đọc
    cache_key = f"{clean_text}_{voice}"
    md5_hash = hashlib.md5(cache_key.encode("utf-8")).hexdigest()
    filename = f"tts_{md5_hash}.mp3"
    filepath = os.path.join(AUDIO_CACHE_DIR, filename)
    audio_url = f"/static/audio_cache/{filename}"

    # Kiểm tra xem file MP3 đã có trong Cache chưa -> trả về ngay < 5ms
    def _cached_ok():
        return os.path.exists(filepath) and os.path.getsize(filepath) > 512

    if _cached_ok():
        return {
            "status": "success",
            "audio_url": audio_url,
            "cached": True,
            "provider": "cache",
            "normalized_text": clean_text
        }

    # Khóa theo từng file: tránh 2 request cùng câu ghi chồng lên nhau (file dở dang bị coi là cache hợp lệ)
    with _get_file_lock(filepath):
        if _cached_ok():
            return {
                "status": "success",
                "audio_url": audio_url,
                "cached": True,
                "provider": "cache",
                "normalized_text": clean_text
            }

        # Luôn ghi ra file tạm rồi đổi tên (atomic) -> file cache luôn đầy đủ, không bao giờ bị cắt dở
        tmp_path = f"{filepath}.{uuid.uuid4().hex[:8]}.tmp"

        def _finalize(provider):
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 512:
                os.replace(tmp_path, filepath)
                return {
                    "status": "success",
                    "audio_url": audio_url,
                    "cached": False,
                    "provider": provider,
                    "normalized_text": clean_text
                }
            return None

        def _cleanup_tmp():
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

        now = time.time()
        # 1. Thử nghiệm Edge-TTS nếu Circuit Breaker không bị ngắt
        if not force_gtts and now > _edge_tts_disabled_until:
            try:
                asyncio.run(_synthesize_edge_tts(clean_text, voice, tmp_path))
                result = _finalize("edge-tts")
                if result:
                    return result
                _cleanup_tmp()
            except Exception as edge_err:
                _cleanup_tmp()
                # Ngắt Circuit Breaker trong 3 phút để các câu sau đi thẳng vào gTTS siêu tốc mà không bị delay
                _edge_tts_disabled_until = now + EDGE_TTS_COOLDOWN
                print(f"[!] Edge-TTS Error / Timeout ({edge_err}). Circuit breaker active for 180s -> Chuyển thẳng gTTS siêu tốc.")

        # 2. Dự phòng: Dùng gTTS (Google Translate TTS) - cực nhanh cho câu ngắn (~0.4s - 0.6s)
        try:
            tts = gTTS(text=clean_text, lang="vi", slow=False, timeout=(3.0, 4.0))
            tts.save(tmp_path)
            result = _finalize("gtts")
            if result:
                return result
            _cleanup_tmp()
        except Exception as gtts_err:
            _cleanup_tmp()
            print(f"[!] gTTS Fallback Error: {gtts_err}")
            return {"error": f"Không thể tạo âm thanh: Edge-TTS và gTTS đều gặp sự cố ({gtts_err})"}

    return {"error": "Lỗi không xác định khi tạo file âm thanh."}


def transcribe_audio_gemini(audio_bytes: bytes, mime_type: str = "audio/webm", api_key: str = None) -> str:
    """
    Nhận diện giọng nói tiếng Việt bằng Google Gemini Audio API (STT Fallback).
    Dành cho các trình duyệt không hỗ trợ Web Speech API (Firefox, Safari cũ).
    """
    from google import genai
    from google.genai import types

    active_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not active_key:
        raise ValueError("Chưa cấu hình GEMINI_API_KEY để sử dụng Gemini Audio STT.")

    client = genai.Client(api_key=active_key)
    prompt = (
        "Bạn là trợ lý nhận diện giọng nói tiếng Việt chuyên cho sinh viên Học viện Công nghệ Bưu chính Viễn thông (PTIT). "
        "Hãy nghe kỹ đoạn âm thanh sau và chuyển đổi thành văn bản tiếng Việt chính xác nhất. "
        "Nếu người nói nhắc đến các thuật ngữ như PTIT, CNTT, ATTT, tín chỉ, học phí, điểm chuẩn, hãy viết đúng chính tả. "
        "Chỉ trả về văn bản nhận diện được, không thêm bất kỳ lời bình luận hay giải thích nào."
    )

    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

    for stt_model in ["gemini-3.5-flash-lite", "gemini-3.6-flash"]:
        try:
            response = client.models.generate_content(
                model=stt_model,
                contents=[prompt, audio_part]
            )
            transcript = (response.text or "").strip()
            if transcript:
                return transcript
        except Exception:
            continue

    return ""
