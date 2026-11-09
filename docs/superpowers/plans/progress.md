# SDD ledger — plan: docs/superpowers/plans/2026-11-09-web-search-fallback.md

MERGE_BASE: 762f76f52e8f08e386ff9e02f7143d05da9c78ba

Ruling 1: Repo git nằm ở thư mục cha HTTM không phải ChatBot — dùng git path từ đó. Thực hiện thẳng trên main (không tạo worktree) theo yêu cầu Native của người dùng.
Ruling 2: Git commit từ terminal bị Access Denied/index.lock từ môi trường sandbox Windows; tiến hành chỉnh sửa trực tiếp và kiểm thử toàn diện bằng test script, người dùng có thể commit sau.

Task 1: complete (Tạo module web_search.py với Google Custom Search JSON API, build context & format citation)
Task 2: complete (Tích hợp web search fallback vào endpoint /api/chat với prompt chuyên dụng)
Task 3: complete (Tích hợp web search fallback vào endpoint /api/chat/stream với SSE event web_search_start và stream mượt mà)
Task 4: complete (Giao diện UI hiển thị huy hiệu thông tin từ Internet, render chip liên kết có thể mở tab mới)
Task 5: complete (Loại trừ cache câu trả lời web, test unit logic thành công 100%)

Final review: self-review (no subagent tool). All verification passed.
