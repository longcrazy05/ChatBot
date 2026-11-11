"""
web_search.py — Module tìm kiếm web (Fallback khi tài liệu nội bộ không có dữ liệu).

Hỗ trợ các nhà cung cấp Search API:
1. Tavily AI Search (Khuyên dùng hàng đầu cho LLM/RAG — Đăng ký miễn phí tại https://tavily.com)
2. Serper.dev (Google Search API chính thức)
3. Google Custom Search JSON API

Hỗ trợ giới hạn tìm kiếm trong danh sách các tên miền được chỉ định từ file
(mặc định: allowed_domains.txt).

Cấu hình trong file .env:
    TAVILY_API_KEY=<your-tavily-api-key>
    # Hoặc:
    SERPER_API_KEY=<your-serper-api-key>
    # Hoặc:
    GOOGLE_CSE_API_KEY=<your-google-api-key>
    GOOGLE_CSE_CX=<your-custom-search-engine-id>
    ALLOWED_DOMAINS_FILE=allowed_domains.txt  (tùy chọn)
"""

import os
import re
from urllib.parse import urlparse, quote
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_FILE, override=True)


def _get_api_credentials():
    """Luôn đọc tươi từ file .env để nhận key mới ngay khi người dùng cập nhật."""
    if os.path.isfile(ENV_FILE):
        load_dotenv(ENV_FILE, override=True)
    tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
    serper_key = os.environ.get("SERPER_API_KEY", "").strip()
    cse_key = os.environ.get("GOOGLE_CSE_API_KEY", "").strip()
    cse_cx = os.environ.get("GOOGLE_CSE_CX", "").strip()
    return {
        "tavily_key": tavily_key,
        "serper_key": serper_key,
        "cse_key": cse_key,
        "cse_cx": cse_cx
    }


_DOMAINS_FILE = os.environ.get("ALLOWED_DOMAINS_FILE", "allowed_domains.txt").strip()

# Giới hạn an toàn dưới ngưỡng quota
_daily_call_count = 0
_MAX_DAILY_CALLS = 90
_last_search_error = ""


def get_last_search_error() -> str:
    """Trả về thông báo lỗi của lần tìm kiếm gần nhất (nếu có)."""
    return _last_search_error


def get_allowed_domains_file_path() -> str:
    """Trả về đường dẫn tuyệt đối của file chứa danh sách tên miền cho phép."""
    if os.path.isabs(_DOMAINS_FILE):
        return _DOMAINS_FILE
    return os.path.join(BASE_DIR, _DOMAINS_FILE)


def load_allowed_domains(filepath: str = None) -> list:
    """
    Đọc và chuẩn hóa danh sách tên miền được phép tìm kiếm từ file.
    
    Hỗ trợ:
    - Bỏ dòng trống, bỏ ghi chú bắt đầu bằng '#'
    - Tự động lược bỏ 'http://', 'https://', 'www.', đường dẫn phía sau dấu '/'
    - Chuyển về chữ thường và loại bỏ trùng lặp
    """
    target_path = filepath or get_allowed_domains_file_path()
    if not os.path.isfile(target_path):
        return []

    domains = []
    seen = set()

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue

                if "#" in s:
                    s = s.split("#", 1)[0].strip()
                if not s:
                    continue

                clean = s.lower()
                clean = re.sub(r"^https?://", "", clean)
                clean = re.sub(r"^www\.", "", clean)
                clean = re.sub(r"^\*\.", "", clean)  # Hỗ trợ cú pháp wildcard *.ptit.edu.vn
                clean = clean.lstrip(".")            # Hỗ trợ cú pháp đuôi .ptit.edu.vn
                clean = clean.split("/")[0].split(":")[0].strip()

                if clean and clean not in seen:
                    seen.add(clean)
                    domains.append(clean)
    except Exception as e:
        print(f"[!] Web Search: Lỗi đọc file danh sách tên miền ({target_path}): {e}")

    return domains


def is_url_in_allowed_domains(url: str, allowed_domains: list) -> bool:
    """
    Kiểm tra xem URL có thuộc một trong các tên miền cho phép hay không.
    (Ví dụ: 'daotao.ptit.edu.vn' khớp với 'ptit.edu.vn').
    """
    if not allowed_domains:
        return True

    if not url:
        return False

    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]

        for dom in allowed_domains:
            dom_clean = dom.lower()
            if hostname == dom_clean or hostname.endswith("." + dom_clean):
                return True
        return False
    except Exception:
        return False


def is_web_search_available() -> bool:
    """
    Kiểm tra xem người dùng đã cấu hình ít nhất một Search API key hay chưa.
    Nếu chưa cấu hình key nào, trả về False (hệ thống sẽ không gọi web search).
    """
    creds = _get_api_credentials()
    return bool(creds["tavily_key"] or creds["serper_key"] or (creds["cse_key"] and creds["cse_cx"]))


def _search_tavily(query: str, allowed_domains: list, num_results: int = 3, api_key: str = None) -> list:
    """
    Tìm kiếm qua Tavily AI Search API (chuyên dụng cho RAG & LLM).
    Hỗ trợ trực tiếp tham số 'include_domains' từ danh sách tên miền cho phép.
    Lấy dư số lượng kết quả (tối소 8) để bộ lọc hậu kiểm loại bỏ các link rác không chứa đúng thực thể.
    """
    global _last_search_error
    url = "https://api.tavily.com/search"
    headers = {"Content-Type": "application/json"}
    fetch_count = min(max(num_results * 3, 8), 10)
    payload = {
        "api_key": api_key,
        "query": query.strip(),
        "search_depth": "basic",
        "max_results": fetch_count,
    }

    # Tavily hỗ trợ trực tiếp lọc tên miền qua include_domains
    if allowed_domains:
        payload["include_domains"] = allowed_domains
        print(f"[*] Tavily Search: Giới hạn trong {len(allowed_domains)} tên miền: {allowed_domains}")

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("results", [])
            results = []
            for item in items:
                item_url = item.get("url", "")
                if allowed_domains and not is_url_in_allowed_domains(item_url, allowed_domains):
                    continue
                snippet = (item.get("content") or item.get("snippet") or "").replace("\n", " ").strip()
                results.append({
                    "title": item.get("title", ""),
                    "snippet": snippet,
                    "url": item_url
                })
            return results
        else:
            _last_search_error = f"Tavily HTTP {resp.status_code}: {resp.text[:120]}"
            print(f"[!] Tavily Error: {_last_search_error}")
            return []
    except Exception as e:
        _last_search_error = f"Tavily Error: {e}"
        print(f"[!] Tavily Error: {e}")
        return []


def _search_serper(query: str, allowed_domains: list, num_results: int = 3, api_key: str = None) -> list:
    """Tìm kiếm Google qua Serper.dev."""
    global _last_search_error
    final_query = query.strip()
    if allowed_domains:
        if len(allowed_domains) == 1:
            site_filter = f"site:{allowed_domains[0]}"
        else:
            site_filter = "(" + " OR ".join(f"site:{d}" for d in allowed_domains) + ")"
        final_query = f"{final_query} {site_filter}"

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "q": final_query,
        "gl": "vn",
        "hl": "vi",
        "num": min(max(1, num_results * 2 if allowed_domains else num_results), 10)
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("organic", [])
            results = []
            for item in items:
                item_url = item.get("link", "")
                if allowed_domains and not is_url_in_allowed_domains(item_url, allowed_domains):
                    continue
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", "").replace("\n", " ").strip(),
                    "url": item_url
                })
                if len(results) >= num_results:
                    break
            return results
        else:
            _last_search_error = f"Serper HTTP {resp.status_code}: {resp.text[:120]}"
            print(f"[!] Serper Error: {_last_search_error}")
            return []
    except Exception as e:
        _last_search_error = f"Serper Error: {e}"
        print(f"[!] Serper Error: {e}")
        return []


_NAME_STOP_WORDS = {
    "dạy", "ở", "là", "và", "của", "cho", "với", "thuộc", "khoa", "bộ", "môn",
    "thông", "tin", "cá", "nhân", "ntn", "như", "thế", "nào", "ra", "sao",
    "gì", "ai", "đâu", "có", "làm", "nhé", "ạ", "ơi", "vậy", "nhỉ", "hiện",
    "đang", "tại", "trường", "viện", "ngành", "lớp", "email", "sđt", "liên", "hệ"
}

_FILE_EXTENSIONS = {"pdf", "doc", "docx", "txt", "md", "png", "jpg", "jpeg", "xls", "xlsx", "ppt", "pptx", "csv", "zip", "rar"}


def extract_queried_lecturer_name(q: str) -> str:
    """
    Trích xuất họ tên giảng viên/cán bộ nếu câu hỏi đang hỏi về một thầy/cô cụ thể.
    Dừng ngay lập tức khi gặp từ nối/từ để hỏi (tránh lấy nhầm 'ntn', 'ai', 'như thế nào' vào tên).
    """
    if not q:
        return ""
    s = re.sub(r"[?,!:;\"'()]+", " ", q.strip())
    teacher_match = re.search(
        r"\b(?:thầy|cô|ts\.?|th\.?s|pgs\.?|gs\.?|giảng\s+viên|tiến\s+sĩ|thạc\s+sĩ|giáo\s+sư)\s+([A-Za-zÀ-ỹ]+(?:\s+[A-Za-zÀ-ỹ]+){1,5})",
        s,
        flags=re.IGNORECASE
    )
    if not teacher_match:
        return ""

    raw_tokens = teacher_match.group(1).strip().split()
    name_words = []
    for w in raw_tokens:
        w_clean = w.strip(".,;:!?\"'").lower()
        if not w_clean or w_clean in _NAME_STOP_WORDS:
            break
        # Bỏ qua học hàm/học vị lồng nhau (vd: "thầy TS Hoàng Mạnh Cường")
        if w_clean in {"ts", "ths", "pgs", "gs", "thầy", "cô"}:
            continue
        name_words.append(w)
        if len(name_words) >= 4:
            break

    if len(name_words) >= 2:
        return " ".join(name_words).title()
    return ""


def extract_queried_domains(q: str) -> list:
    """Trích xuất các tên miền web (ví dụ: it.ptit.edu.vn) xuất hiện trong câu hỏi."""
    if not q:
        return []
    candidates = re.findall(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", q.lower())
    domains = []
    for c in candidates:
        tld = c.rsplit(".", 1)[-1]
        if tld in _FILE_EXTENSIONS:
            continue
        if c not in domains:
            domains.append(c)
    return domains


def refine_search_query(q: str) -> str:
    """
    Chuẩn hóa và trích xuất thực thể tìm kiếm cốt lõi từ câu hỏi của người dùng.
    Loại bỏ các từ đệm hội thoại (dạy môn gì, thông tin cá nhân, ntn, cho em hỏi...),
    loại bỏ các lời than phiền hoặc yêu cầu tra internet, đồng thời định hướng truy vấn
    chính xác đến cổng thông tin phù hợp của PTIT (giáo vụ, tuyển sinh, đào tạo).
    """
    if not q:
        return ""
    s = q.strip()

    # 0. Loại bỏ các mẫu câu hội thoại mang tính than phiền, chỉ dẫn hoặc yêu cầu tra internet
    meta_patterns = [
        r"\btôi\s+hỏi\s+",
        r"\bnhưng\s+(?:kết\s+quả\s+)?(?:lại\s+)?(?:ra|là|thành)\s+[^,.;]*",
        r"\bở\s+đây\s+tôi\s+cần\s+tra\s+(?:cứu\s+)?(?:trên\s+|qua\s+)?(?:internet|mạng|google|web)\b",
        r"\bkiểm\s+tra\s+lại\s+(?:việc\s+)?tra\s+tài\s+liệu\s+và\s+tra\s+internet\b",
        r"\b(?:hãy\s+)?(?:tra\s+(?:cứu\s+)?(?:trên\s+|qua\s+)?(?:internet|mạng|google|web)|tìm\s+(?:kiếm\s+)?(?:trên\s+|qua\s+)?(?:internet|mạng|google|web)|search\s+web)\b",
    ]
    for pat in meta_patterns:
        s = re.sub(pat, " ", s, flags=re.IGNORECASE)

    # 1. Phát hiện câu hỏi về giảng viên / thầy / cô / cán bộ
    lecturer_name = extract_queried_lecturer_name(s)
    if lecturer_name:
        return f'"{lecturer_name}" giảng viên'

    # 2. Phát hiện câu hỏi hỏi về tên miền / website cụ thể (ví dụ: "it.ptit.edu.vn là gì")
    queried_domains = extract_queried_domains(s)
    if queried_domains:
        dom = queried_domains[0]
        return f"Giới thiệu trang chủ {dom}"

    # 3. Phát hiện câu hỏi thủ tục sinh viên / hành chính / giấy tờ / xác nhận (cả có dấu và không dấu)
    # Tránh để Search API trỏ sang cổng tuyển sinh thí sinh mới hoặc đề án tuyển sinh
    student_admin_keywords = [
        "giấy xác nhận", "giay xac nhan", "xác nhận sinh viên", "xac nhan sinh vien",
        "kết quả học tập", "ket qua hoc tap", "bảng điểm", "bang diem",
        "hoãn thi", "hoan thi", "vắng thi", "vang thi", "nghỉ học", "nghi hoc",
        "thôi học", "thoi hoc", "chuyển ngành", "chuyen nganh",
        "phúc khảo", "phuc khao", "đổi ca thi", "doi ca thi", "học lại", "hoc lai",
        "miễn học", "mien hoc", "bảo lưu", "bao luu", "đăng ký môn", "dang ky mon",
        "chứng nhận tốt nghiệp", "chung nhan tot nghiep", "hồ sơ sinh viên", "ho so sinh vien",
        "sổ tay sinh viên", "so tay sinh vien"
    ]
    if any(k in s.lower() for k in student_admin_keywords):
        core_terms = []
        for k in student_admin_keywords:
            if k in s.lower():
                core_terms.append(k)
        term_str = " ".join(core_terms) if core_terms else s
        return f"{term_str} thủ tục sinh viên giáo vụ ptit"

    # 4. Phát hiện câu hỏi tuyển sinh / chỉ tiêu / điểm chuẩn / xét tuyển
    tuyensinh_keywords = [
        "tuyển sinh", "tuyen sinh", "chỉ tiêu", "chi tieu", "điểm chuẩn", "diem chuan",
        "xét tuyển", "xet tuyen", "phương thức tuyển", "phuong thuc tuyen", "đề án tuyển sinh"
    ]
    if any(k in s.lower() for k in tuyensinh_keywords):
        is_postgrad = any(k in s.lower() for k in ["thạc sĩ", "thạc sỹ", "sau đại học", "cao học", "tiến sĩ", "tiến sỹ"])
        target_major = ""
        major_patterns = [
            (r"\b(?:ngành\s+)?(?:cntt|công\s+nghệ\s+thông\s+tin)\b", "Công nghệ thông tin"),
            (r"\b(?:ngành\s+)?(?:attt|an\s+toàn\s+thông\s+tin)\b", "An toàn thông tin"),
            (r"\b(?:ngành\s+)?(?:khoa\s+học\s+máy\s+tính)\b", "Khoa học máy tính"),
            (r"\b(?:ngành\s+)?(?:trí\s+tuệ\s+nhân\s+tạo|ai)\b", "Trí tuệ nhân tạo"),
            (r"\b(?:ngành\s+)?(?:kỹ\s+thuật\s+điện\s+tử\s+viễn\s+thông|đtvt|điện\s+tử\s+viễn\s+thông)\b", "Điện tử viễn thông"),
            (r"\b(?:ngành\s+)?(?:marketing)\b", "Marketing"),
            (r"\b(?:ngành\s+)?(?:truyền\s+thông\s+đa\s+phương\s+tiện)\b", "Truyền thông đa phương tiện"),
            (r"\b(?:ngành\s+)?(?:thương\s+mại\s+điện\s+tử)\b", "Thương mại điện tử"),
        ]
        for pat, major_name in major_patterns:
            if re.search(pat, s, re.IGNORECASE):
                target_major = major_name
                break

        if is_postgrad:
            major_suffix = f"ngành {target_major}" if target_major else ""
            return f"chỉ tiêu tuyển sinh thạc sĩ {major_suffix} ptit".strip()
        else:
            major_suffix = f"ngành {target_major}" if target_major else ""
            return f"chỉ tiêu tuyển sinh đại học chính quy {major_suffix} ptit tuyensinh".strip()

    # 5. Xóa các cụm từ đệm hội thoại
    fillers = [
        r"\b(?:cho\s+(?:em|mình|tôi)\s+hỏi|hỏi\s+chút|bạn\s+ơi|ad\s+ơi|bot\s+ơi)\b",
        r"\b(?:thông\s+tin\s+cá\s+nhân|thông\s+tin\s+liên\s+hệ|tiểu\s+sử|profile)\b",
        r"\b(?:dạy\s+môn\s+gì|dạy\s+những\s+môn\s+nào|dạy\s+môn\s+nào)\b",
        r"\b(?:như\s+thế\s+nào|thế\s+nào|ra\s+sao|ntn|nhỉ|nhé|ạ|ơi)\b",
        r"\b(?:có\s+được\s+không|được\s+không|phải\s+không|hở\s+bạn)\b",
        r"\b(?:bao\s+nhiêu|khi\s+nào|ở\s+đâu|là\s+gì)\b",
    ]
    for pat in fillers:
        s = re.sub(pat, " ", s, flags=re.IGNORECASE)

    # Giữ nguyên dấu chấm nếu nằm giữa các ký tự tên miền, chỉ xóa dấu câu ở rìa
    s = re.sub(r"[?,!:;]+|(?<!\w)\.|(?<=\w)\.(?!\w)", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) >= 3 else q.strip()


def _filter_relevant_results(results: list, original_query: str, num_results: int = 3) -> list:
    """
    Hậu kiểm và lọc bỏ các kết quả web không liên quan (rác):
    1. Nếu hỏi về một giảng viên/cán bộ cụ thể (vd: "Bùi Văn Kiên", "Hoàng Mạnh Cường"):
       Chỉ giữ lại những trang thực sự xuất hiện đầy đủ họ tên đó trong tiêu đề hoặc nội dung trích dẫn.
       Loại bỏ hoàn toàn các trang chỉ trùng từ "giảng viên" hoặc trùng 1 từ đơn lẻ (như "Thầy Kiên" khác, "Bùi Thị Dân"...).
    2. Nếu hỏi về tên miền cụ thể (vd: "it.ptit.edu.vn"):
       Ưu tiên trang chủ và trang giới thiệu của tên miền đó, loại bỏ các bài viết lẻ không liên quan nếu đã có trang giới thiệu.
    3. Với câu hỏi chung:
       Chấm điểm độ khớp từ khóa trọng tâm và loại bỏ các trang không chứa từ khóa trọng tâm.
    """
    if not results:
        return []

    lecturer_name = extract_queried_lecturer_name(original_query)
    if lecturer_name:
        name_lower = lecturer_name.lower()
        tolerant_tokens = []
        for tok in name_lower.split():
            tok_pat = re.escape(tok)
            tok_pat = re.sub(r"[ăâ]", "[ăâa]?", tok_pat)
            tolerant_tokens.append(tok_pat)
        name_regex = re.compile(r"\b" + r"\s+".join(tolerant_tokens) + r"\b", flags=re.IGNORECASE)

        exact_matches = []
        for r in results:
            combined = f"{r.get('title', '')} {r.get('snippet', '')}"
            if name_lower in combined.lower() or name_regex.search(combined):
                exact_matches.append(r)

        if exact_matches:
            def _match_score(item):
                comb = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
                url_lower = (item.get("url") or "").lower()
                score = 0
                if name_lower in comb:
                    score += 10
                # Nếu câu hỏi hỏi về môn học / giảng dạy, ưu tiên các trang có danh sách môn cụ thể
                if any(w in original_query.lower() for w in ["môn", "học phần", "dạy", "giảng dạy"]):
                    if any(w in comb for w in ["môn", "học phần", "giảng dạy", "c++", "giải thuật", "hệ điều hành"]):
                        score += 8
                # Trừ điểm biểu mẫu / quyết định PDF hành chính nếu có bài viết web
                if any(bad in url_lower for bad in ["bieu-mau", "bieu_mau", "lats", "luan-an", "4.-bieu-mau", "4.bieu-mau"]):
                    score -= 5
                elif url_lower.endswith(".pdf"):
                    score -= 3
                return score

            exact_matches.sort(key=_match_score, reverse=True)
            return exact_matches[:num_results]

    queried_domains = extract_queried_domains(original_query)
    if queried_domains:
        dom = queried_domains[0].lower()
        intro_matches = []
        other_dom_matches = []
        for r in results:
            u = (r.get("url") or "").lower()
            t = (r.get("title") or "").lower()
            parsed_path = urlparse(u).path.strip("/")
            if not parsed_path or "gioi-thieu" in u or "trang-chu" in u or "giới thiệu" in t:
                intro_matches.append(r)
            elif dom in u:
                other_dom_matches.append(r)
        if intro_matches:
            return intro_matches[:num_results]
        if other_dom_matches:
            return other_dom_matches[:num_results]

    # 3. Phân loại theo ngữ cảnh câu hỏi sinh viên vs tuyển sinh
    q_lower = original_query.lower()
    is_student_admin = any(k in q_lower for k in [
        "giấy xác nhận", "xác nhận", "kết quả học tập", "bảng điểm",
        "hoãn thi", "vắng thi", "nghỉ học", "thôi học", "chuyển ngành",
        "phúc khảo", "học lại", "miễn học", "bảo lưu", "đăng ký môn",
        "chứng nhận tốt nghiệp", "hồ sơ sinh viên", "giáo vụ", "sinh viên"
    ])
    is_tuyensinh_query = any(k in q_lower for k in [
        "tuyển sinh", "xét tuyển", "chỉ tiêu", "phương thức tuyển",
        "điểm chuẩn vào", "thí sinh", "nguyện vọng", "học bạ"
    ])

    generic_words = {
        "ptit", "học", "viện", "công", "nghệ", "bưu", "chính", "viễn", "thông",
        "sinh", "viên", "giảng", "thầy", "cô", "trường", "đại", "khoa", "ngành",
        "cho", "hỏi", "tin", "như", "thế", "nào", "ntn", "bao", "nhiêu",
        "của", "tại", "năm", "hiện", "nay", "các", "những", "trong", "với", "thủ", "tục"
    }
    q_clean = refine_search_query(original_query).lower()
    core_words = [w for w in re.findall(r"[a-zA-ZÀ-ỹ0-9]{2,}", q_clean) if w not in generic_words]

    scored = []
    for r in results:
        u_lower = (r.get("url") or "").lower()
        comb = f"{r.get('title', '')} {r.get('snippet', '')}".lower()
        score = 0

        # Nếu người dùng hỏi thủ tục sinh viên / kết quả học tập nhưng kết quả lại từ cổng tuyển sinh -> trừ điểm nặng hoặc loại bỏ
        if is_student_admin and not is_tuyensinh_query:
            if "tuyensinh.ptit.edu.vn" in u_lower or "/tuyen-sinh" in u_lower or "đkxt" in u_lower:
                score -= 15
            if any(k in comb for k in ["cam nang huong dan dkxt", "đề án tuyển sinh", "thông báo phương thức tuyển sinh"]):
                score -= 20
            # Ưu tiên các trang giáo vụ, sinh viên, thủ tục
            if any(good in u_lower for good in ["giaovu.ptit.edu.vn", "student.ptit.edu.vn", "daotao.ptit.edu.vn", "co-cau-to-chuc/phong-giao-vu"]):
                score += 15
            if any(kw in comb for kw in ["giáo vụ", "mẫu biểu", "thủ tục hành chính", "kết quả học tập", "xác nhận"]):
                score += 8

        # Nếu là câu hỏi tuyển sinh: Ưu tiên trang tuyensinh.ptit.edu.vn và các đề án tuyển sinh mới nhất (2025, 2026)
        if is_tuyensinh_query:
            if "tuyensinh.ptit.edu.vn" in u_lower or "/tuyen-sinh" in u_lower or "thong-tin-tuyen-sinh" in u_lower or "de-an-tuyen-sinh" in u_lower:
                score += 15
            if "2026" in u_lower or "2026" in comb:
                score += 10
            elif "2025" in u_lower or "2025" in comb:
                score += 6
            if any(y in u_lower or y in comb for y in ["2018", "2019", "2020", "2021"]):
                score -= 10

        # Khớp từ khóa cốt lõi
        hits = sum(1 for w in core_words if w in comb)
        score += hits * 3

        if score > -5:
            scored.append((score, r))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:num_results]]

    return results[:num_results]


def search_web(query: str, num_results: int = 3, api_key: str = None, cx: str = None, domains_file: str = None) -> list:
    """
    Tìm kiếm web dựa trên API key mà người dùng cấu hình:
    1. Ưu tiên 1: Tavily AI Search (TAVILY_API_KEY) — Tối ưu nhất cho LLM/RAG
    2. Ưu tiên 2: Serper (Google Search API - SERPER_API_KEY)
    3. Ưu tiên 3: Google Custom Search JSON API (GOOGLE_CSE_API_KEY & CX)
    """
    global _daily_call_count, _last_search_error
    _last_search_error = ""

    creds = _get_api_credentials()
    allowed_domains = load_allowed_domains(domains_file)
    refined_q = refine_search_query(query)
    target_q = refined_q if refined_q else query.strip()

    # Nếu câu hỏi hỏi trực tiếp về một subdomain hợp lệ (vd: it.ptit.edu.vn), ưu tiên tìm thẳng trong subdomain đó
    queried_domains = extract_queried_domains(query)
    valid_queried_domains = [
        d for d in queried_domains
        if is_url_in_allowed_domains(f"https://{d}", allowed_domains)
    ]
    effective_domains = valid_queried_domains if valid_queried_domains else allowed_domains

    # 1. Ưu tiên Tavily AI Search nếu có key
    if creds["tavily_key"]:
        print(f"[*] Web Search: Đang tìm kiếm qua Tavily AI Search cho: '{target_q[:60]}'")
        results = _search_tavily(target_q, effective_domains, num_results, creds["tavily_key"])
        results = _filter_relevant_results(results, query, num_results)
        if not results and effective_domains != allowed_domains:
            results = _search_tavily(target_q, allowed_domains, num_results, creds["tavily_key"])
            results = _filter_relevant_results(results, query, num_results)
        if not results and target_q != query.strip():
            print(f"[*] Web Search: Thử lại với truy vấn gốc: '{query[:60]}'")
            results = _search_tavily(query.strip(), allowed_domains, num_results, creds["tavily_key"])
            results = _filter_relevant_results(results, query, num_results)
        if results:
            return _decorate_results_with_fragments(results, query)
        if _last_search_error:
            print(f"[!] Tavily thất bại ({_last_search_error}), chuyển thử Serper/Google CSE nếu có...")

    # 2. Serper Google Search API nếu có cấu hình
    if creds["serper_key"]:
        print(f"[*] Web Search: Đang tìm kiếm qua Serper Google API cho: '{target_q[:60]}'")
        results = _search_serper(target_q, effective_domains, num_results, creds["serper_key"])
        results = _filter_relevant_results(results, query, num_results)
        if not results and target_q != query.strip():
            results = _search_serper(query.strip(), allowed_domains, num_results, creds["serper_key"])
            results = _filter_relevant_results(results, query, num_results)
        if results:
            return _decorate_results_with_fragments(results, query)

    # 3. Google Custom Search JSON API nếu có cấu hình
    key = (api_key or creds["cse_key"]).strip()
    engine_id = (cx or creds["cse_cx"]).strip()

    if not key or not engine_id:
        if not creds["tavily_key"] and not creds["serper_key"]:
            _last_search_error = "Chưa cấu hình API Key tìm kiếm web (TAVILY_API_KEY hoặc SERPER_API_KEY trong file .env)."
        return []

    if _daily_call_count >= _MAX_DAILY_CALLS:
        _last_search_error = "Đã đạt giới hạn truy vấn tìm kiếm web hàng ngày (90 lượt/ngày)."
        print(f"[!] Web Search: {_last_search_error}")
        return []

    final_query = query.strip()
    if allowed_domains:
        if len(allowed_domains) == 1:
            site_filter = f"site:{allowed_domains[0]}"
        else:
            site_filter = "(" + " OR ".join(f"site:{d}" for d in allowed_domains) + ")"
        final_query = f"{final_query} {site_filter}"
        print(f"[*] Web Search: Giới hạn tìm kiếm trong {len(allowed_domains)} tên miền: {allowed_domains}")

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": key,
        "cx": engine_id,
        "q": final_query,
        "num": min(max(1, num_results * 2 if allowed_domains else num_results), 10),
        "lr": "lang_vi",
        "safe": "active",
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        _daily_call_count += 1

        if resp.status_code == 429:
            _last_search_error = "Hết hạn mức truy vấn Google Custom Search API (HTTP 429)."
            print(f"[!] Web Search: {_last_search_error}")
            return []
        if resp.status_code == 403:
            err_data = {}
            try:
                err_data = resp.json().get("error", {})
            except Exception:
                pass
            err_msg = err_data.get("message", "Lỗi xác thực API key (HTTP 403).")
            _last_search_error = f"Lỗi Google Custom Search API (403): {err_msg}"
            print(f"[!] Web Search: {_last_search_error}")
            return []
        if resp.status_code != 200:
            _last_search_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
            print(f"[!] Web Search: {_last_search_error}")
            return []

        data = resp.json()
        items = data.get("items", [])

        results = []
        for item in items:
            item_url = item.get("link", "")
            if allowed_domains and not is_url_in_allowed_domains(item_url, allowed_domains):
                continue

            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", "").replace("\n", " ").strip(),
                "url": item_url,
            })
            if len(results) >= num_results:
                break

        return _decorate_results_with_fragments(results, query)

    except requests.exceptions.Timeout:
        _last_search_error = "Timeout (5s) — Máy chủ tìm kiếm không phản hồi."
        print(f"[!] Web Search: {_last_search_error}")
        return []
    except requests.exceptions.ConnectionError:
        _last_search_error = "Lỗi kết nối mạng khi tìm kiếm web."
        print(f"[!] Web Search: {_last_search_error}")
        return []
    except Exception as e:
        _last_search_error = f"Web Search Error: {e}"
        print(f"[!] Web Search Error: {e}")
        return []


def build_web_context(results: list) -> str:
    """
    Ghép các kết quả tìm kiếm web thành một chuỗi context cho LLM tổng hợp.
    """
    if not results:
        return ""
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(
            f"--- [KẾT QUẢ WEB {i}] ---\n"
            f"Tiêu đề: {r['title']}\n"
            f"Nội dung tóm tắt: {r['snippet']}\n"
            f"Nguồn URL: {r['url']}"
        )
    return "\n\n".join(parts)


def _extract_snippet_highlight_phrase(snippet: str, question: str) -> str:
    """
    Trích xuất cụm từ 2-4 từ có ý nghĩa xuất hiện đồng thời trong cả snippet và câu hỏi.
    Đảm bảo cụm từ này chắc chắn có mặt trên trang web để Text Fragment highlight thành công.
    """
    if not snippet or not question:
        return ""
    snip_clean = re.sub(r"\s+", " ", snippet).strip()

    # Tìm cụm 2-4 từ liên tiếp trong question có xuất hiện nguyên văn trong snippet
    q_words = [w for w in re.findall(r"[a-zA-ZÀ-ỹ0-9]+", question) if len(w) >= 2]
    for window_size in (4, 3, 2):
        for i in range(len(q_words) - window_size + 1):
            candidate = " ".join(q_words[i:i + window_size])
            if len(candidate) >= 8 and candidate.lower() in snip_clean.lower():
                idx = snip_clean.lower().find(candidate.lower())
                exact_slice = snip_clean[idx:idx + len(candidate)].strip(".,;:-!?\"'()[]{} ")
                if len(exact_slice) >= 6:
                    return exact_slice
    return ""


def build_highlight_fragment(url: str, question: str = "", snippet: str = "") -> str:
    """
    Tạo URL có gắn chỉ thị Scroll-to-Text Fragment (W3C standard #:~:text=...)
    hoặc PDF search directive (#search=...) để khi người dùng mở liên kết,
    trình duyệt tự động cuộn đến đúng vị trí và bôi sáng văn bản khớp với câu hỏi.
    """
    if not url:
        return ""

    # Tránh gắn lặp lại nếu URL đã có directive text fragment
    if ":~:text=" in url:
        return url

    is_pdf = url.lower().split("?")[0].endswith(".pdf")
    target_term = ""

    # 1. Ưu tiên 1: Tên giảng viên / cá nhân cụ thể được hỏi
    if question:
        lecturer = extract_queried_lecturer_name(question)
        if lecturer:
            target_term = lecturer

    # 2. Ưu tiên 2: Cụm từ danh từ sau "môn", "học phần", "ngành"
    if not target_term and question:
        subj_m = re.search(r"\b(?:môn|học phần|ngành)\s+([A-Za-zÀ-ỹ0-9\s]{3,35})", question, re.IGNORECASE)
        if subj_m:
            raw_subj = subj_m.group(1).strip()
            raw_subj = re.split(r"\b(?:là|ở|như|của|cho|gì|nào)\b", raw_subj, flags=re.IGNORECASE)[0].strip()
            if len(raw_subj) >= 4:
                if not snippet or raw_subj.lower() in snippet.lower():
                    target_term = raw_subj

    # 3. Ưu tiên 3: Giao điểm từ khóa giữa Question và Snippet (chắc chắn có trên trang)
    if not target_term and snippet and question:
        target_term = _extract_snippet_highlight_phrase(snippet, question)

    # 4. Fallback an toàn: Nếu không tìm thấy cụm từ đủ độ tin cậy, giữ nguyên URL gốc
    if not target_term or len(target_term.strip()) < 3:
        return url

    clean_term = target_term.strip(".,;:-!?\"'()[]{} ")
    # Mã hóa ký tự theo chuẩn URL percent-encoding (khoảng trắng thành %20, dấu gạch ngang thành %2D)
    encoded_term = quote(clean_term).replace("-", "%2D")

    if is_pdf:
        sep = "&" if "#" in url else "#"
        return f"{url}{sep}search={encoded_term}"

    sep = ":~:text=" if "#" in url else "#:~:text="
    return f"{url}{sep}{encoded_term}"


def _decorate_results_with_fragments(results: list, question: str) -> list:
    """Gắn thêm trường highlight_url cho từng kết quả tìm kiếm web."""
    if not results:
        return []
    for r in results:
        if "highlight_url" not in r:
            r["highlight_url"] = build_highlight_fragment(
                r.get("url", ""),
                question=question,
                snippet=r.get("snippet", "")
            )
    return results


def format_web_citations(results: list, original_query: str = "") -> str:
    """
    Tạo khối trích dẫn nguồn web dạng Markdown để gắn cuối câu trả lời.
    Tự động áp dụng URL Scroll-to-Text Fragment (#:~:text=...) để bôi sáng
    văn bản khớp với câu hỏi ngay khi người dùng mở liên kết.
    """
    if not results:
        return ""
    lines = []
    for r in results:
        url = r.get("highlight_url") or build_highlight_fragment(
            r.get("url", ""),
            question=original_query,
            snippet=r.get("snippet", "")
        )
        title = r.get("title", url)
        if url:
            lines.append(f"- 🌐 [{title}]({url})")
    if not lines:
        return ""
    return "\n\n---\n🔍 **Nguồn từ Internet:**\n" + "\n".join(lines)
