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

# Circuit Breaker cho Edge-TTS
EDGE_TTS_TIMEOUT = 5.0  # Cho phép tới 5s để Edge-TTS Neural voice chất lượng cao hoàn tất
EDGE_TTS_COOLDOWN = 60  # Nếu lỗi kết nối, tạm nghỉ 60s rồi thử lại Edge-TTS
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
    (r"\bKT&ĐBCLGD\b|\bKT&ĐBCL\b", "Khảo thí và Đảm bảo chất lượng giáo dục"),
    (r"\bCTSV\b", "Công tác sinh viên"),
    (r"\bBCVT\b", "Bưu chính Viễn thông"),
    (r"\bĐRL\b", "Điểm rèn luyện"),
    (r"\bTBCMR\b", "Điểm trung bình chung mở rộng"),
    (r"\bKLTN\b", "Khóa luận tốt nghiệp"),
    (r"\bTTTN\b", "Thực tập tốt nghiệp"),
    (r"\bCN\b(?=\s+[A-ZÀ-Ỹ])", "Cử nhân"),
    (r"\bKS\b(?=\s+[A-ZÀ-Ỹ])", "Kỹ sư"),
]

DIGIT_MAP = {
    "0": "không", "1": "một", "2": "hai", "3": "ba", "4": "bốn",
    "5": "năm", "6": "sáu", "7": "bảy", "8": "tám", "9": "chín"
}

def digits_to_words(d_str: str) -> str:
    """Chuyển chuỗi số thành chữ số phát âm tiếng Việt."""
    return " ".join(DIGIT_MAP[ch] for ch in d_str if ch in DIGIT_MAP)


def normalize_phone_numbers(text: str) -> str:
    """
    Chuẩn hóa số điện thoại di động, cố định, hotline tổng đài thành từng cụm chữ số tiếng Việt tự nhiên.
    Giúp giọng đọc ngắt nhịp mượt mà (VD: 024.3756.2186 -> không hai bốn, ba bảy năm sáu, hai một tám sáu),
    đồng thời ngăn chặn bộ đọc TTS đọc nhầm số điện thoại thành số học lũy kế (như '24 triệu...').
    """
    if not text:
        return text

    t = text

    # Chuẩn hóa tiền tố liên hệ để giọng đọc phát âm rõ ràng
    t = re.sub(r"\b(?:SĐT|Sđt|sđt|ĐT|Đt)\s*:\s*", "số điện thoại: ", t)
    t = re.sub(r"\b(?:SĐT|Sđt|sđt)\b", "số điện thoại", t)
    t = re.sub(r"\b(?:Hotline|hotline)\s*:\s*", "hotline: ", t)
    t = re.sub(r"\b(?:Tel|tel)\s*:\s*", "điện thoại: ", t)
    t = re.sub(r"\b(?:Fax|fax)\s*:\s*", "fax: ", t)

    # 1. Tổng đài Hotline 1800/1900 xxxx (4 số đầu + 4 số cuối)
    def repl_1800_1900(m):
        return f"{digits_to_words(m.group(1))}, {digits_to_words(m.group(2))}"

    t = re.sub(r"\b(1[89]00)[\s.-]?(\d{4})\b", repl_1800_1900, t)

    # 2. Số điện thoại có mã quốc gia (+84 hoặc 84)
    def repl_vn_intl(m):
        lead = "cộng tám bốn" if "+" in m.group(1) else "tám bốn"
        raw = m.group(2)
        digits = re.sub(r"[^\d]", "", raw)
        chunks = []
        if len(digits) == 9:
            chunks.append(digits_to_words(digits[:2]))
            chunks.append(digits_to_words(digits[2:5]))
            chunks.append(digits_to_words(digits[5:]))
        elif len(digits) == 10:
            chunks.append(digits_to_words(digits[:2]))
            chunks.append(digits_to_words(digits[2:6]))
            chunks.append(digits_to_words(digits[6:]))
        else:
            return m.group(0)
        return lead + ", " + ", ".join(chunks)

    t = re.sub(r"(\+?84|\(\+?84\))[\s.-]?([0-9][0-9\s.-]{7,13}[0-9])\b", repl_vn_intl, t)

    # 3. Số điện thoại di động & cố định trong nước (bắt đầu bằng 0, tổng cộng 10 hoặc 11 chữ số)
    # Ví dụ: 024.3756.2186, (024) 3756 2186, 0988.123.456, 0912 345 678, 0988123456, 02437562186
    def repl_domestic_phone(m):
        full = m.group(0)
        digits = re.sub(r"[^\d]", "", full)

        if not (digits.startswith("0") and len(digits) in (10, 11)):
            return full

        # Bỏ qua ngày tháng hoặc số thập phân như 0.05%
        if "/" in full or full.startswith("0.0") or full.startswith("0,0"):
            return full

        chunks = []
        if len(digits) == 10:
            # Di động 10 số: 4 số đầu, 3 số giữa, 3 số cuối (0988, 123, 456)
            if digits.startswith(("03", "05", "07", "08", "09")):
                chunks.append(digits_to_words(digits[:4]))
                chunks.append(digits_to_words(digits[4:7]))
                chunks.append(digits_to_words(digits[7:]))
            elif digits.startswith(("024", "028")):
                chunks.append(digits_to_words(digits[:3]))
                chunks.append(digits_to_words(digits[3:6]))
                chunks.append(digits_to_words(digits[6:]))
            else:
                chunks.append(digits_to_words(digits[:4]))
                chunks.append(digits_to_words(digits[4:7]))
                chunks.append(digits_to_words(digits[7:]))
        elif len(digits) == 11:
            # Cố định Hà Nội (024) / TP.HCM (028): 3 số mã vùng, 4 số giữa, 4 số cuối
            # Ví dụ: 024.33820854 -> không hai bốn, ba ba tám hai, không tám năm bốn
            if digits.startswith(("024", "028")):
                chunks.append(digits_to_words(digits[:3]))
                chunks.append(digits_to_words(digits[3:7]))
                chunks.append(digits_to_words(digits[7:]))
            else:
                # Tỉnh thành khác mã vùng 4 số (ví dụ 0236...)
                chunks.append(digits_to_words(digits[:4]))
                chunks.append(digits_to_words(digits[4:7]))
                chunks.append(digits_to_words(digits[7:]))

        return ", ".join(chunks)

    # Bắt mọi dạng số điện thoại di động & cố định trong nước (10 hoặc 11 chữ số):
    # Bao gồm dạng 1 dấu chấm (024.33820854), 2 dấu chấm (024.3756.2186), dấu cách (024 33820854),
    # ngoặc đơn ((024) 33820854), gạch nối (024-33820854), hoặc viết liền (02433820854)
    t = re.sub(r"(?:\(0\d{2,3}\)|0[1-9])(?:[\s.-]?\d){8,10}\b", repl_domestic_phone, t)

    return t


def strip_english_subtitles(text: str) -> str:
    """
    Loại bỏ phụ đề tiếng Anh trong ngoặc đơn (VD: Introduction to Artificial Intelligence)
    để bộ đọc tiếng Việt không bị phát âm lẫn tiếng Anh (như từ 'to' bị đọc thành tiếng Việt),
    đồng thời bảo tồn nguyên vẹn tên miền website (VD: clc.ptit.edu.vn) và từ viết tắt PTIT.
    """
    def repl_paren(m):
        content = m.group(1).strip()
        # Nếu chứa đuôi tên miền, liên kết web hoặc email -> giữ nguyên
        if re.search(r"\b(?:edu|vn|com|org|net|http|www)\b", content, re.IGNORECASE) or "@" in content:
            return m.group(0)
        # Nếu là từ viết tắt thương hiệu như (PTIT) hoặc (BCVT) -> giữ nguyên để các bước sau xử lý
        if re.match(r"^(?:PTIT|BCVT)$", content, re.IGNORECASE):
            return m.group(0)
        # Nếu là cụm từ tiếng Anh trong ngoặc (chữ cái La-tinh không dấu, khoảng trắng, gạch nối)
        if re.match(r"^[A-Za-z\s,.\'\-–—]+$", content):
            words = content.split()
            if len(words) >= 2 or len(content) >= 7:
                return ""
        return m.group(0)

    return re.sub(r"\s*\(([^)]+)\)", repl_paren, text)


def normalize_dates(text: str) -> str:
    """
    Chuẩn hóa các định dạng ngày tháng năm:
    - 01/11/2026 -> ngày 1 tháng 11 năm 2026
    - từ 01/11/2026 đến 15/11/2026 -> từ ngày 1 tháng 11 năm 2026 đến ngày 15 tháng 11 năm 2026
    - tháng 11/2026 -> tháng 11 năm 2026
    - 2025/2026 -> 2025 đến 2026
    - ngày 15/10 -> ngày 15 tháng 10
    Ngăn chặn triệt để việc đọc dấu '/' thành 'trên' hoặc 'hoặc' (như '01 trên 11 hoặc 2026').
    """
    if not text:
        return text

    t = text

    # 1. dd/mm/yyyy hoặc d/m/yyyy hoặc dd-mm-yyyy hoặc dd.mm.yyyy (có tiền tố hoặc đứng độc lập)
    def repl_full_date(m):
        prefix = m.group(1) or ""
        d = int(m.group(2))
        m_val = int(m.group(3))
        y = m.group(4)
        if 1 <= d <= 31 and 1 <= m_val <= 12 and len(y) == 4:
            has_ngay = bool(re.search(r"ngày\s*$", prefix, re.IGNORECASE))
            if has_ngay:
                return f"{prefix}{d} tháng {m_val} năm {y}"
            return f"{prefix}ngày {d} tháng {m_val} năm {y}"
        return m.group(0)

    # Có tiền tố như từ, đến, ngày, hạn... hoặc độc lập
    t = re.sub(r"((?:từ|đến|vào|trước|sau|hạn|ngày)\s+)?\b([0-2]?[1-9]|3[01])[/.-](0?[1-9]|1[0-2])[/.-]((?:19|20)\d{2})\b", repl_full_date, t, flags=re.IGNORECASE)
    t = re.sub(r"\b([0-2]?[1-9]|3[01])/(0?[1-9]|1[0-2])/((?:19|20)\d{2})\b", repl_full_date, t)

    # 2. mm/yyyy (tháng 11/2026, kỳ 1/2026)
    def repl_month_year(m):
        prefix = m.group(1) or ""
        m_val = int(m.group(2))
        y = m.group(3)
        if 1 <= m_val <= 12:
            if "tháng" in prefix.lower():
                return f"{prefix}{m_val} năm {y}"
            return f"{prefix}tháng {m_val} năm {y}"
        return m.group(0)

    t = re.sub(r"((?:trong|vào|từ|đến|tháng)\s+)?\b(0?[1-9]|1[0-2])/((?:19|20)\d{2})\b", repl_month_year, t, flags=re.IGNORECASE)

    # 3. Năm học / niên khóa: 2025/2026
    t = re.sub(r"\b((?:19|20)\d{2})\s*/\s*((?:19|20)\d{2})\b", r"\1 đến \2", t)

    # 4. Ngày/tháng (có từ ngày, từ, đến đứng trước): ngày 01/11, từ 01/11 đến 15/11
    def repl_day_month(m):
        prefix = m.group(1) or ""
        d = int(m.group(2))
        m_val = int(m.group(3))
        if 1 <= d <= 31 and 1 <= m_val <= 12:
            if "ngày" in prefix.lower():
                return f"{prefix}{d} tháng {m_val}"
            return f"{prefix}ngày {d} tháng {m_val}"
        return m.group(0)

    t = re.sub(r"((?:từ|đến|vào|trước|sau|ngày)\s+)\b([0-2]?[1-9]|3[01])/(0?[1-9]|1[0-2])\b", repl_day_month, t, flags=re.IGNORECASE)

    return t


def normalize_decimals_and_units(text: str) -> str:
    """
    Chuẩn hóa số thập phân và các đơn vị đo lường, ký hiệu so sánh:
    - 1,8 tỷ VNĐ -> 1 phẩy 8 tỷ đồng (loại bỏ dấu phẩy để không bị ngắt mệnh đề thành 'ngân sách 1' và '8 tỷ')
    - 2,5 triệu -> 2 phẩy 5 triệu đồng
    - < 2s, < 5s -> dưới 2 giây, dưới 5 giây
    - <=, >=, <, > kèm số
    """
    if not text:
        return text

    t = text

    # 1. Số thập phân đi kèm đơn vị tiền tệ: 1,8 tỷ VNĐ, 2,5 triệu đ, 1.8 tỷ đồng
    def repl_dec_currency(m):
        int_part = m.group(1)
        dec_part = m.group(2)
        unit = m.group(3)
        cur = m.group(4) or ""
        cur_word = " đồng" if (cur or unit.lower() in ("tỷ", "triệu")) else ""
        return f"{int_part} phẩy {dec_part} {unit}{cur_word}"

    t = re.sub(r"\b(\d+)[,.](\d+)\s*(tỷ|triệu|nghìn|tr)(?:\s*(VNĐ|VND|đ|dong|đồng))?(?=[\s,.)!?;:]|$)", repl_dec_currency, t, flags=re.IGNORECASE)

    # 2. Tiền tệ viết dạng: 1 tỷ 8, 2 triệu 5
    t = re.sub(r"\b(\d+)\s*(tỷ|triệu)\s*(\d+)(?:\s*(?:VNĐ|VND|đ|dong|đồng))?(?=[\s,.)!?;:]|$)", r"\1 \2 \3 đồng", t, flags=re.IGNORECASE)

    # 3. Ký hiệu so sánh và đơn vị thời gian kỹ thuật (< 2s, <= 5s, > 100ms)
    t = re.sub(r"<=\s*(\d+)\s*s\b", r"dưới hoặc bằng \1 giây", t, flags=re.IGNORECASE)
    t = re.sub(r">=\s*(\d+)\s*s\b", r"từ \1 giây trở lên", t, flags=re.IGNORECASE)
    t = re.sub(r"<\s*(\d+)\s*s\b", r"dưới \1 giây", t, flags=re.IGNORECASE)
    t = re.sub(r">\s*(\d+)\s*s\b", r"trên \1 giây", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(\d+)\s*s\b(?=[\s,.)])", r"\1 giây", t, flags=re.IGNORECASE)

    t = re.sub(r"<\s*(\d+)\s*ms\b", r"dưới \1 mili giây", t, flags=re.IGNORECASE)
    t = re.sub(r">\s*(\d+)\s*ms\b", r"trên \1 mili giây", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(\d+)\s*ms\b", r"\1 mili giây", t, flags=re.IGNORECASE)

    # Các phép so sánh còn lại: <= 2, >= 5, < 2, > 5
    t = re.sub(r"<=\s*(\d+)", r"dưới hoặc bằng \1", t)
    t = re.sub(r">=\s*(\d+)", r"từ \1 trở lên", t)
    t = re.sub(r"<\s*(\d+)", r"dưới \1", t)
    t = re.sub(r">\s*(\d+)", r"trên \1", t)

    # 4. Số thập phân thông thường có dấu phẩy: 1,8 -> 1 phẩy 8 (tránh dấu phẩy tách mệnh đề)
    t = re.sub(r"\b(\d+),(\d{1,2})\b", r"\1 phẩy \2", t)

    return t


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
    2. Chuẩn hóa số điện thoại thành chữ số tự nhiên ngắt nhịp (chống đọc nhầm thành số triệu)
    3. Chuẩn hóa từ viết tắt PTIT và tên trường (không lặp từ, đọc đúng 'Bưu chính Viễn thông', không bị đọc thành 'viễn đông')
    4. Chuẩn hóa số tiền và các ký hiệu toán học, tên miền website
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

    # 0.1. Chuẩn hóa ngày tháng năm TRƯỚC TIÊN (01/11/2026 -> ngày 1 tháng 11 năm 2026) để tránh bị dấu gạch chéo '/' biến thành 'trên'/'hoặc'
    s = normalize_dates(s)

    # 0.2. Chuẩn hóa số thập phân và đơn vị so sánh (1,8 tỷ VNĐ -> 1 phẩy 8 tỷ đồng, < 2s -> dưới 2 giây) TRƯỚC KHI ký tự <, > bị lọc
    s = normalize_decimals_and_units(s)

    s = re.sub(r"[*_~><#]", " ", s)

    # Loại bỏ thẻ HTML thừa
    s = re.sub(r"<[^>]+>", " ", s)

    # 0.3. Loại bỏ phụ đề tiếng Anh trong ngoặc (không xóa tên miền website hoặc PTIT)
    s = strip_english_subtitles(s)

    # 1. Chuẩn hóa số điện thoại thành từng cụm chữ số tự nhiên ngắt nhịp TRƯỚC KHI regex tiền tệ quét qua
    s = normalize_phone_numbers(s)

    # 2. Tránh lặp và chuẩn hóa cách phát âm tên Học viện PTIT:
    # 'Học viện Công nghệ Bưu chính Viễn thông (PTIT)' -> đọc gọn, không lặp
    s = re.sub(r"Học\s+viện\s+(?:Công\s+nghệ\s+)?Bưu\s+chính\s+Viễn\s+thông\s*\(\s*PTIT\s*\)", "Học viện Công nghệ Bưu chính Viễn thông", s, flags=re.IGNORECASE)
    s = re.sub(r"Cổng\s+thông\s+tin\s+(?:Học\s+viện\s+)?PTIT\b", "Cổng thông tin Bưu chính Viễn thông", s, flags=re.IGNORECASE)
    s = re.sub(r"Học\s+viện\s+PTIT\b", "Học viện Bưu chính Viễn thông", s, flags=re.IGNORECASE)
    # PTIT đứng riêng -> đọc là 'Bưu chính Viễn thông' để phát âm liền mạch, mượt mà, không bị ngắt P...TIT
    s = re.sub(r"\bPTIT\b", "Bưu chính Viễn thông", s)

    # Đảm bảo 'Bưu chính' và 'Viễn thông' luôn viết chuẩn bằng dấu cách tự nhiên,
    # tuyệt đối không có dấu gạch ngang '-' để tránh bộ đọc Google/Edge nhận nhầm thành 'viễn đông'
    s = re.sub(r"\bBưu[\s-]+chính\b", "Bưu chính", s, flags=re.IGNORECASE)
    s = re.sub(r"\bViễn[\s-]+thông\b", "Viễn thông", s, flags=re.IGNORECASE)

    # 3. Xử lý ngắt dòng, bullet points để giọng nói dừng nghỉ dứt khoát giữa các mục:
    s = re.sub(r"(?<![.!?;:])\s*\n\s*[-*•+]\s*", ". ", s)
    s = re.sub(r"^\s*[-*•+]\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"(?<![.!?;:,])\s*\n", ". ", s)

    # Chuẩn hóa tiền tệ: ví dụ 15.000.000 VNĐ, 550.000 đ, 500,000 VND
    s = re.sub(r"(\d{1,3}(?:[.,]\d{3})+)\s*(?:VNĐ|VND|đ|dong|đồng)\b", format_currency_match, s, flags=re.IGNORECASE)

    # Mở rộng các từ viết tắt chuyên ngành PTIT
    for pattern, replacement in PTIT_ABBREVIATIONS:
        s = re.sub(pattern, replacement, s)

    # Đảm bảo lại một lần nữa 'Bưu chính' và 'Viễn thông' không bị dính dấu gạch ngang
    s = re.sub(r"\bBưu[\s-]+chính\b", "Bưu chính", s, flags=re.IGNORECASE)
    s = re.sub(r"\bViễn[\s-]+thông\b", "Viễn thông", s, flags=re.IGNORECASE)

    # Xử lý dấu gạch chéo '/' theo ngữ cảnh đơn vị tính & tiền tệ trước
    s = re.sub(r"(?:đ|VNĐ|VND|đồng)\s*/\s*([a-zA-ZÀ-ỹ]+)", r" đồng trên mỗi \1", s, flags=re.IGNORECASE)
    s = re.sub(r"(\d+)\s*/\s*(\d+)", r"\1 trên \2", s)
    s = re.sub(r"/\s*(?:tín\s+chỉ|tháng|kỳ|học\s+kỳ|năm|người|sinh\s+viên|môn|buổi)\b", r" trên mỗi \g<0>", s, flags=re.IGNORECASE)
    s = s.replace(" trên mỗi /", " trên mỗi ")

    # Đọc tên miền website mượt mà theo phát âm chuẩn tiếng Việt
    def _format_domain(match):
        dom = match.group(0).lower()
        dom = dom.replace("ptit.edu.vn", "p tit chấm edu chấm vn")
        dom = dom.replace("ptit.vn", "p tit chấm vn")
        dom = dom.replace("edu.vn", "edu chấm vn")
        dom = re.sub(r"\bclc\b", "c l c", dom)
        dom = re.sub(r"\bit\b", "i t", dom)
        dom = re.sub(r"\bsdh\b", "s d h", dom)
        dom = re.sub(r"\bdaotao\b", "đào tạo", dom)
        dom = re.sub(r"\bgiaovu\b", "giáo vụ", dom)
        dom = re.sub(r"\bstudent\b", "sinh viên", dom)
        dom = re.sub(r"\btuyensinh\b", "tuyển sinh", dom)
        dom = dom.replace(".", " chấm ")
        return dom

    s = re.sub(r"\b(?:[a-zA-Z0-9-]+\.)+(?:ptit\.edu\.vn|edu\.vn|ptit\.vn|vn|com)\b", _format_domain, s, flags=re.IGNORECASE)

    # Dấu gạch chéo '/' còn lại: giữa 2 tên miền, 2 tùy chọn -> đọc là 'hoặc' (thay vì 'phần' hay 'trên')
    s = re.sub(r"([a-zA-ZÀ-ỹ0-9.-]+)\s*/\s*([a-zA-ZÀ-ỹ0-9.-]+)", r"\1 hoặc \2", s)
    s = s.replace("/", " hoặc ")
    s = s.replace("%", " phần trăm ")
    s = s.replace("&", " và ")
    s = s.replace("@", " a còng ")
    s = re.sub(r"\s+", " ", s).strip()

    return s


async def _synthesize_edge_tts(text: str, voice: str, output_path: str):
    """Thực thi gọi Edge-TTS bất đồng bộ."""
    communicate = edge_tts.Communicate(text, voice)
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

    # Khóa theo từng file: tránh 2 request cùng câu ghi chồng lên nhau
    with _get_file_lock(filepath):
        if _cached_ok():
            return {
                "status": "success",
                "audio_url": audio_url,
                "cached": True,
                "provider": "cache",
                "normalized_text": clean_text
            }

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
        # 1. Thử nghiệm Edge-TTS Neural Voice chuẩn tự nhiên
        if not force_gtts and now > _edge_tts_disabled_until:
            try:
                asyncio.run(_synthesize_edge_tts(clean_text, voice, tmp_path))
                result = _finalize("edge-tts")
                if result:
                    return result
                _cleanup_tmp()
            except Exception as edge_err:
                _cleanup_tmp()
                _edge_tts_disabled_until = now + EDGE_TTS_COOLDOWN
                print(f"[!] Edge-TTS Error / Timeout ({edge_err}). Circuit breaker active for 60s -> Chuyển thẳng gTTS.")

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
