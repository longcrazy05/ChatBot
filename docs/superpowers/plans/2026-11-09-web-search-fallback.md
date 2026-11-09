# Web Search Fallback — Tự Động Tìm Kiếm Web Khi Tài Liệu Nội Bộ Không Có Thông Tin

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khi chatbot phát hiện tài liệu nội bộ PTIT không chứa đủ thông tin để trả lời câu hỏi, tự động tìm kiếm trên web (Google Custom Search API), tổng hợp kết quả, sinh câu trả lời qua LLM, và trích dẫn kèm link nguồn gốc.

**Architecture:** Thêm module `web_search.py` chuyên trách gọi Google Custom Search JSON API (hoặc SerpAPI) → lấy top 3-5 snippet + URL. Hàm `_is_no_info_response()` đã có sẵn trong `app.py` để phát hiện câu trả lời từ chối. Khi phát hiện "không có thông tin", hệ thống sẽ gọi `web_search.search()` → xây prompt mới kèm web context → gọi LLM lần 2 → hậu xử lý gắn link nguồn web vào câu trả lời. Flow streaming SSE cũng được cập nhật tương tự.

**Tech Stack:** Python, Flask, Google Custom Search JSON API (`requests`), Gemini REST API (đã có)

## Global Constraints

- Không cài thêm thư viện bên ngoài (chỉ dùng `requests` đã có sẵn)
- API key Google Custom Search và Search Engine ID (cx) lưu trong file `.env`
- Giới hạn tối đa 3 kết quả web để tránh tốn quota và giữ prompt ngắn gọn
- Luôn trích dẫn rõ URL nguồn web ở cuối câu trả lời, phân biệt với nguồn tài liệu PTIT
- Không bao giờ trả kết quả web cho các câu hỏi thuộc phạm vi `user_only` (chỉ tài liệu tải lên)
- Web search chỉ kích hoạt khi scope là `ptit_only` hoặc `hybrid` VÀ câu trả lời từ tài liệu nội bộ bị phát hiện là "không có thông tin"
- Giữ nguyên toàn bộ logic RAG hiện tại — web search là bước fallback bổ sung, không thay thế

## Review Focus

1. **Câu hỏi về thông tin nhạy cảm nội bộ PTIT (điểm số, mật khẩu):** Không nên tìm web — LLM prompt phải chặn việc tiết lộ thông tin không chính thống.
2. **Google Custom Search API trả kết quả rỗng hoặc timeout:** Hệ thống phải xử lý gracefully, trả về câu trả lời dự phòng thay vì crash.
3. **Kết quả web chứa thông tin sai lệch/cũ về PTIT:** Prompt LLM phải yêu cầu ghi chú rõ "thông tin từ nguồn bên ngoài, có thể chưa cập nhật".
4. **Rate limit Google CSE (100 truy vấn/ngày miễn phí):** Phải có cơ chế đếm và dừng khi hết quota.
5. **Scope `user_only` nhưng câu trả lời vẫn bị nhận nhầm là "không có thông tin":** Kiểm tra scope trước khi kích hoạt web search.

---

## File Structure

| File | Vai trò |
|---|---|
| **Tạo mới:** `web_search.py` | Module tìm kiếm web: gọi Google CSE API, trả snippet + URL |
| **Sửa:** `app.py` (~L1413-1478, ~L2327-2395, ~L2398-2489) | Tích hợp web fallback vào flow chat và chat/stream |
| **Sửa:** `.env` | Thêm biến `GOOGLE_CSE_API_KEY` và `GOOGLE_CSE_CX` |
| **Sửa:** `templates/index.html` | Hiển thị link nguồn web trong giao diện (nếu có) |

---

### Task 1: Module Web Search (`web_search.py`)

**Files:**
- Create: `web_search.py`
- Modify: `.env` (thêm 2 biến cấu hình)

**Interfaces:**
- Consumes: `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX` từ `.env`; `requests` (đã cài)
- Produces:
  - `search_web(query: str, num_results: int = 3, api_key: str = None, cx: str = None) -> list[dict]`
    - Trả về: `[{"title": str, "snippet": str, "url": str}, ...]`
    - Trả `[]` nếu lỗi/hết quota/không có kết quả
  - `is_web_search_available() -> bool` — kiểm tra có cấu hình API key hay không
  - `build_web_context(results: list[dict]) -> str` — ghép snippet thành chuỗi context cho LLM
  - `format_web_citations(results: list[dict]) -> str` — tạo khối trích dẫn web Markdown

- [ ] **Step 1: Tạo file `.env` mẫu bổ sung**

Thêm vào cuối file `.env` hiện tại:
```
# Google Custom Search (Web Fallback)
GOOGLE_CSE_API_KEY=
GOOGLE_CSE_CX=
```

- [ ] **Step 2: Implement `web_search.py`**

```python
# web_search.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "").strip()
_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "").strip()
_daily_call_count = 0
_MAX_DAILY_CALLS = 90  # giữ dưới 100 free tier

def is_web_search_available() -> bool:
    """Kiểm tra xem tính năng tìm kiếm web có được cấu hình hay chưa."""
    return bool(_CSE_API_KEY and _CSE_CX)

def search_web(query: str, num_results: int = 3, api_key: str = None, cx: str = None) -> list:
    """
    Tìm kiếm web qua Google Custom Search JSON API.
    Trả về danh sách dict {title, snippet, url} hoặc [] nếu lỗi.
    """
    global _daily_call_count
    key = (api_key or _CSE_API_KEY).strip()
    engine_id = (cx or _CSE_CX).strip()

    if not key or not engine_id:
        return []
    if _daily_call_count >= _MAX_DAILY_CALLS:
        print("[!] Web Search: Đã đạt giới hạn truy vấn hàng ngày.")
        return []

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": key,
        "cx": engine_id,
        "q": query,
        "num": min(num_results, 5),
        "lr": "lang_vi",       # ưu tiên kết quả tiếng Việt
        "safe": "active"
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        _daily_call_count += 1

        if resp.status_code == 429:
            print("[!] Web Search: Google CSE quota exceeded (429).")
            return []
        if resp.status_code != 200:
            print(f"[!] Web Search: HTTP {resp.status_code}")
            return []

        data = resp.json()
        items = data.get("items", [])
        results = []
        for item in items[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "url": item.get("link", ""),
            })
        return results
    except requests.exceptions.Timeout:
        print("[!] Web Search: Timeout (5s)")
        return []
    except Exception as e:
        print(f"[!] Web Search Error: {e}")
        return []

def build_web_context(results: list) -> str:
    """Ghép kết quả tìm kiếm web thành chuỗi context cho LLM."""
    if not results:
        return ""
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(
            f"--- [KẾT QUẢ WEB {i}] ---\n"
            f"Tiêu đề: {r['title']}\n"
            f"Nội dung: {r['snippet']}\n"
            f"Nguồn: {r['url']}"
        )
    return "\n\n".join(parts)

def format_web_citations(results: list) -> str:
    """Tạo khối trích dẫn nguồn web Markdown để gắn cuối câu trả lời."""
    if not results:
        return ""
    lines = []
    for r in results:
        if r.get("url"):
            lines.append(f"- 🌐 [{r['title']}]({r['url']})")
    if not lines:
        return ""
    return "\n\n---\n🔍 **Nguồn từ Internet:**\n" + "\n".join(lines)
```

- [ ] **Step 3: Kiểm tra module chạy được**

Run: `python -c "import web_search; print(web_search.is_web_search_available())"`
Expected: `False` (chưa cấu hình key) — không crash.

- [ ] **Step 4: Commit**

```bash
git add web_search.py .env
git commit -m "feat: add web_search module for Google CSE fallback"
```

---

### Task 2: Tích hợp Web Fallback vào luồng Chat `/api/chat`

**Files:**
- Modify: `app.py:2327-2395` (hàm `chat()`)
- Modify: `app.py:1329-1350` (hàm `generate_llm_answer()` — thêm tham số prompt override)

**Interfaces:**
- Consumes: `web_search.search_web()`, `web_search.build_web_context()`, `web_search.format_web_citations()`, `web_search.is_web_search_available()`, `_is_no_info_response()` (đã có)
- Produces: Câu trả lời JSON có thêm trường `"web_searched": true/false` và `"web_sources": [...]`

- [ ] **Step 1: Thêm import `web_search` ở đầu `app.py`**

Thêm dòng `import web_search` vào block import đầu file `app.py` (sau dòng `import document_parser`).

- [ ] **Step 2: Tạo hàm `build_web_rag_prompt()` trong `app.py`**

Hàm này sinh prompt cho LLM khi trả lời dựa trên kết quả web:

```python
def build_web_rag_prompt(question: str, web_context: str, history=None) -> str:
    """Prompt chuyên dụng khi trả lời từ kết quả tìm kiếm web."""
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

    return f"""Bạn là Trợ lý Ảo AI của Học viện Công nghệ Bưu chính Viễn thông (PTIT).
Tài liệu nội bộ của Học viện KHÔNG có thông tin để trả lời câu hỏi này.
Dưới đây là kết quả tìm kiếm từ Internet để tham khảo:

{web_context}

{history_prompt}CÂU HỎI: {question}

NGUYÊN TẮC BẮT BUỘC:
1. Tổng hợp thông tin từ các kết quả web ở trên để trả lời câu hỏi một cách ngắn gọn, chính xác.
2. BẮT BUỘC mở đầu bằng: "⚠️ **Lưu ý:** Thông tin này được tổng hợp từ nguồn bên ngoài Internet, không phải từ tài liệu chính thức của Học viện PTIT. Vui lòng xác minh lại với phòng ban liên quan."
3. KHÔNG tự bịa thêm thông tin ngoài những gì có trong kết quả tìm kiếm.
4. TUYỆT ĐỐI KHÔNG gắn mục "📌 Nguồn trích dẫn" kiểu tài liệu nội bộ — hệ thống sẽ tự động gắn link nguồn web.
5. Trả lời bằng tiếng Việt, văn phong thân thiện.
6. KHÔNG sử dụng ký hiệu LaTeX toán học."""
```

- [ ] **Step 3: Sửa hàm `chat()` — thêm bước Web Fallback sau khi phát hiện "không có thông tin"**

Vị trí: Sau dòng `clean_answer = clean_llm_response(answer)` và trước `clean_answer, sources_list = ensure_answer_citations(...)`.

Logic thêm vào:
```python
    web_searched = False
    web_sources = []

    # Web Search Fallback: Nếu câu trả lời từ tài liệu nội bộ là "không có thông tin"
    # VÀ scope không phải user_only VÀ web search đã cấu hình
    if (_is_no_info_response(clean_answer)
            and effective_scope != "user_only"
            and web_search.is_web_search_available()):
        web_results = web_search.search_web(question, num_results=3)
        if web_results:
            web_context = web_search.build_web_context(web_results)
            web_prompt = build_web_rag_prompt(question, web_context, history)
            web_answer, web_model, web_err = generate_llm_answer(
                question=question,
                context_str=web_context,
                custom_api_key=custom_api_key,
                preferred_model=preferred_model,
                history=history,
                has_user_docs=False,
                user_files=None,
                scope="web"  # đánh dấu để build_rag_prompt không chạy
            )
            # Gọi trực tiếp với web_prompt thay vì qua build_rag_prompt
            active_key = custom_api_key.strip() if custom_api_key.strip() else API_KEY
            models_to_try = _resolve_and_order_models(preferred_model)
            for model_name in models_to_try:
                web_answer, web_err = call_gemini_rest_api(web_prompt, model_name, active_key, timeout=8.5)
                if web_answer:
                    model_used = model_name
                    break

            if web_answer:
                clean_answer = clean_llm_response(web_answer)
                clean_answer += web_search.format_web_citations(web_results)
                web_searched = True
                web_sources = [{"title": r["title"], "url": r["url"]} for r in web_results]
                is_fallback = False
```

- [ ] **Step 4: Thêm `web_searched` và `web_sources` vào JSON response**

Sửa block `return jsonify(...)` cuối hàm `chat()`:
```python
    return jsonify({
        "answer": clean_answer,
        "model_used": model_used,
        "scope_used": effective_scope,
        "referenced_files": referenced_files,
        "sources": sources_list,
        "web_searched": web_searched,
        "web_sources": web_sources
    })
```

- [ ] **Step 5: Kiểm tra server khởi động không lỗi**

Run: `python -c "from app import app; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat: integrate web search fallback into /api/chat endpoint"
```

---

### Task 3: Tích hợp Web Fallback vào luồng Streaming SSE `/api/chat/stream`

**Files:**
- Modify: `app.py:2398-2489` (hàm `chat_stream()`, bên trong `generate_sse()`)

**Interfaces:**
- Consumes: Cùng các hàm từ Task 1 & 2
- Produces: SSE events bổ sung `type: "web_search_start"`, `type: "chunk"` (từ web answer), và `type: "done"` có `web_searched`, `web_sources`

- [ ] **Step 1: Sửa `generate_sse()` — thêm Web Fallback**

Vị trí: Sau block `if not raw_full:` (dòng fallback an toàn), trước `clean_answer = clean_llm_response(raw_full)`.

Logic tương tự Task 2 nhưng yield SSE events:

```python
        web_searched = False
        web_sources = []

        if (_is_no_info_response(clean_llm_response(raw_full))
                and effective_scope != "user_only"
                and web_search.is_web_search_available()):
            yield f"data: {json.dumps({'type': 'web_search_start'}, ensure_ascii=False)}\n\n"
            web_results = web_search.search_web(question, num_results=3)
            if web_results:
                web_context = web_search.build_web_context(web_results)
                web_prompt = build_web_rag_prompt(question, web_context, history)
                # Stream lại từ đầu với web context
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
                            web_sources = [{"title": r["title"], "url": r["url"]} for r in web_results]
                            is_fallback = False
                            break
                    except Exception:
                        continue
```

- [ ] **Step 2: Thêm `web_searched`, `web_sources` vào SSE event `type: "done"`**

Sửa dòng yield cuối cùng trong `generate_sse()`:
```python
        # Nếu web_searched, gắn link nguồn web
        if web_searched:
            clean_answer += web_search.format_web_citations(web_results)

        yield f"data: {json.dumps({
            'type': 'done',
            'answer': clean_answer,
            'model_used': model_used,
            'scope_used': effective_scope,
            'referenced_files': final_refs,
            'sources': sources_list,
            'web_searched': web_searched,
            'web_sources': web_sources
        }, ensure_ascii=False)}\n\n"
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: integrate web search fallback into SSE streaming endpoint"
```

---

### Task 4: Cập nhật giao diện hiển thị nguồn web

**Files:**
- Modify: `templates/index.html`
- Modify: `static/css/style.css` (nếu cần)

**Interfaces:**
- Consumes: JSON response có `web_searched: true`, `web_sources: [{title, url}]`, và SSE event `type: "web_search_start"`
- Produces: Giao diện hiển thị badge "🌐 Tìm kiếm Web" và danh sách link nguồn có thể click

- [ ] **Step 1: Xử lý SSE event `web_search_start` trong JavaScript**

Khi nhận event `type: "web_search_start"`, hiển thị indicator nhỏ trong bubble chat:
```
"🔍 Đang tìm kiếm thông tin trên Internet..."
```

- [ ] **Step 2: Xử lý `web_sources` trong event `type: "done"`**

Khi `data.web_searched === true`:
- Hiển thị badge `🌐 Nguồn từ Internet` bên dưới câu trả lời
- Render danh sách link từ `web_sources` dưới dạng các thẻ `<a>` có `target="_blank"` và `rel="noopener noreferrer"`

- [ ] **Step 3: Thêm CSS cho badge và link web**

```css
.web-source-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    background: #e3f2fd;
    color: #1565c0;
    border-radius: 12px;
    font-size: 0.82em;
    margin-top: 8px;
}
.web-source-link {
    display: block;
    color: #1976d2;
    text-decoration: none;
    font-size: 0.88em;
    padding: 2px 0;
    word-break: break-all;
}
.web-source-link:hover {
    text-decoration: underline;
}
```

- [ ] **Step 4: Kiểm tra giao diện**

Khởi chạy server, gửi một câu hỏi không liên quan đến PTIT (ví dụ: "Thủ đô của Pháp là gì?").
- Nếu đã cấu hình CSE key: Kiểm tra có hiện badge web và link nguồn
- Nếu chưa cấu hình: Kiểm tra hiện thông báo "không có thông tin" bình thường, không crash

- [ ] **Step 5: Commit**

```bash
git add templates/index.html static/css/style.css
git commit -m "feat: display web search results and source links in chat UI"
```

---

### Task 5: Không lưu cache kết quả web & kiểm tra toàn bộ luồng

**Files:**
- Modify: `app.py` (hàm `_store_response_cache`)

**Interfaces:**
- Consumes: `web_searched` flag
- Produces: Đảm bảo kết quả web không bị cache sai vào LRU

- [ ] **Step 1: Sửa logic cache — không cache câu trả lời web**

Trong hàm `chat()` và `generate_sse()`, khi `web_searched == True`, không gọi `_store_response_cache()`:

```python
    if not is_fallback and not web_searched and cache_key:
        _store_response_cache(cache_key, clean_answer, model_used, referenced_files, sources=sources_list)
```

- [ ] **Step 2: Kiểm tra toàn diện**

1. Câu hỏi có trong tài liệu PTIT → Trả lời bình thường, không gọi web search
2. Câu hỏi không có trong tài liệu PTIT + có CSE key → Tự động tìm web, trả kèm link
3. Câu hỏi không có trong tài liệu PTIT + không có CSE key → Trả "không có thông tin" như cũ
4. Scope `user_only` + câu hỏi ngoài tài liệu → Không tìm web, gợi ý đổi scope
5. Server restart → Không bị crash vì thiếu biến môi trường web search

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "fix: exclude web search results from response cache"
```

