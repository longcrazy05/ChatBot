/**
 * PTIT SMART ASSISTANT - CLIENT APPLICATION (CLEAN & OPTIMIZED)
 * Features: RAG Chatting, Markdown & Table Formatting, Chat History,
 * Sources Inspector, Custom Settings & Document Catalog.
 */

// Gợi ý câu hỏi phổ biến và chính xác
const PROMPT_SUGGESTIONS = [
    {
        icon: "fa-solid fa-coins",
        title: "Học phí CNTT năm 2025",
        desc: "Mức thu học phí một tín chỉ và toàn khóa của ngành Công nghệ Thông tin?",
        prompt: "Mức thu học phí ngành Công nghệ Thông tin theo văn bản hp_2025 là bao nhiêu tiền một tín chỉ?"
    },
    {
        icon: "fa-solid fa-chart-line",
        title: "So sánh Học phí 2025 & 2026",
        desc: "Khung học phí năm học 2025-2026 có những điều chỉnh gì so với 2024-2025?",
        prompt: "So sánh mức thu học phí giữa năm 2024-2025 và năm học 2025-2026 của các hệ đào tạo chính quy?"
    },
    {
        icon: "fa-solid fa-graduation-cap",
        title: "Khung Tín chỉ Tốt nghiệp CNTT",
        desc: "Chương trình đào tạo đại học ngành CNTT yêu cầu tích lũy bao nhiêu tín chỉ?",
        prompt: "Tổng khối lượng kiến thức toàn khóa của chương trình đào tạo ngành Công nghệ thông tin là bao nhiêu tín chỉ?"
    },
    {
        icon: "fa-solid fa-award",
        title: "Học bổng Khuyến khích PTIT",
        desc: "Điều kiện điểm học tập và điểm rèn luyện để được xét cấp học bổng?",
        prompt: "Điều kiện và tiêu chuẩn để sinh viên PTIT được xét cấp học bổng khuyến khích học tập là gì?"
    }
];

class PTITChatApp {
    constructor() {
        this.currentSessionId = null;
        this.sessions = [];
        this.settings = {
            apiKey: "",
            model: "gemini-3.5-flash-lite"
        };
        this.isProcessing = false;

        this.init();
    }

    init() {
        this.bindElements();
        this.setupMarkdown();
        this.loadSettings();
        this.loadSessions();
        this.bindEvents();
        this.fetchKBStatus();
        this.renderSuggestions();

        if (this.sessions.length > 0) {
            this.switchSession(this.sessions[0].id);
        } else {
            this.createNewSession();
        }
    }

    setupMarkdown() {
        if (window.marked) {
            marked.setOptions({
                breaks: true,
                gfm: true,
                highlight: function (code, lang) {
                    if (window.hljs && hljs.getLanguage(lang)) {
                        return hljs.highlight(code, { language: lang }).value;
                    }
                    return code;
                }
            });
        }
    }

    bindElements() {
        // Layout Elements
        this.sidebar = document.getElementById("sidebar");
        this.openSidebarBtn = document.getElementById("openSidebarBtn");
        this.closeSidebarBtn = document.getElementById("closeSidebarBtn");
        this.themeToggleBtn = document.getElementById("themeToggleBtn");
        this.themeIcon = document.getElementById("themeIcon");
        this.themeText = document.getElementById("themeText");

        // Chat Elements
        this.newChatBtn = document.getElementById("newChatBtn");
        this.navbarNewChatBtn = document.getElementById("navbarNewChatBtn");
        this.chatHistoryList = document.getElementById("chatHistoryList");
        this.clearAllHistoryBtn = document.getElementById("clearAllHistoryBtn");
        this.currentChatTitle = document.getElementById("currentChatTitle");
        this.chatMessagesArea = document.getElementById("chatMessagesArea");
        this.welcomeHero = document.getElementById("welcomeHero");
        this.messageThread = document.getElementById("messageThread");
        this.typingIndicator = document.getElementById("typingIndicator");
        this.typingLabel = document.getElementById("typingLabel");
        this.suggestionsGrid = document.getElementById("suggestionsGrid");

        // Input Form
        this.chatForm = document.getElementById("chatForm");
        this.userInput = document.getElementById("userInput");
        this.sendBtn = document.getElementById("sendBtn");

        // Modals
        this.kbModal = document.getElementById("kbModal");
        this.openKbModalBtn = document.getElementById("openKbModalBtn");
        this.navbarDocsBtn = document.getElementById("navbarDocsBtn");
        this.closeKbModalBtn = document.getElementById("closeKbModalBtn");
        this.closeKbModalFooterBtn = document.getElementById("closeKbModalFooterBtn");
        this.catalogGrid = document.getElementById("catalogGrid");
        this.sidebarChunksCount = document.getElementById("sidebarChunksCount");
        this.modalTotalChunks = document.getElementById("modalTotalChunks");

        this.settingsModal = document.getElementById("settingsModal");
        this.openSettingsBtn = document.getElementById("openSettingsBtn");
        this.closeSettingsModalBtn = document.getElementById("closeSettingsModalBtn");
        this.saveSettingsBtn = document.getElementById("saveSettingsBtn");
        this.resetSettingsBtn = document.getElementById("resetSettingsBtn");
        this.customApiKeyInput = document.getElementById("customApiKeyInput");
        this.modelSelect = document.getElementById("modelSelect");

        this.sourceModal = document.getElementById("sourceModal");
        this.sourceModalTitle = document.getElementById("sourceModalTitle");
        this.sourceModalSubtitle = document.getElementById("sourceModalSubtitle");
        this.sourceModalContent = document.getElementById("sourceModalContent");
        this.closeSourceModalBtn = document.getElementById("closeSourceModalBtn");
        this.closeSourceModalFooterBtn = document.getElementById("closeSourceModalFooterBtn");
        this.copySourceContentBtn = document.getElementById("copySourceContentBtn");

        this.toastContainer = document.getElementById("toastContainer");
    }

    bindEvents() {
        // Sidebar Toggles
        if (this.openSidebarBtn) {
            this.openSidebarBtn.addEventListener("click", () => {
                this.sidebar.classList.add("open");
            });
        }
        if (this.closeSidebarBtn) {
            this.closeSidebarBtn.addEventListener("click", () => {
                this.sidebar.classList.remove("open");
            });
        }

        // New Chat
        if (this.newChatBtn) {
            this.newChatBtn.addEventListener("click", () => this.createNewSession());
        }
        if (this.navbarNewChatBtn) {
            this.navbarNewChatBtn.addEventListener("click", () => this.createNewSession());
        }

        // Clear History
        if (this.clearAllHistoryBtn) {
            this.clearAllHistoryBtn.addEventListener("click", () => this.clearAllHistory());
        }

        // Theme Toggle
        if (this.themeToggleBtn) {
            this.themeToggleBtn.addEventListener("click", () => this.toggleTheme());
        }

        // Modals
        if (this.openKbModalBtn) {
            this.openKbModalBtn.addEventListener("click", () => this.openCatalogModal());
        }
        if (this.navbarDocsBtn) {
            this.navbarDocsBtn.addEventListener("click", () => this.openCatalogModal());
        }
        if (this.closeKbModalBtn) {
            this.closeKbModalBtn.addEventListener("click", () => this.kbModal.classList.remove("active"));
        }
        if (this.closeKbModalFooterBtn) {
            this.closeKbModalFooterBtn.addEventListener("click", () => this.kbModal.classList.remove("active"));
        }

        if (this.openSettingsBtn) {
            this.openSettingsBtn.addEventListener("click", () => this.openSettings());
        }
        if (this.closeSettingsModalBtn) {
            this.closeSettingsModalBtn.addEventListener("click", () => this.settingsModal.classList.remove("active"));
        }
        if (this.saveSettingsBtn) {
            this.saveSettingsBtn.addEventListener("click", () => this.saveSettings());
        }
        if (this.resetSettingsBtn) {
            this.resetSettingsBtn.addEventListener("click", () => this.resetSettings());
        }

        if (this.closeSourceModalBtn) {
            this.closeSourceModalBtn.addEventListener("click", () => this.sourceModal.classList.remove("active"));
        }
        if (this.closeSourceModalFooterBtn) {
            this.closeSourceModalFooterBtn.addEventListener("click", () => this.sourceModal.classList.remove("active"));
        }
        if (this.copySourceContentBtn) {
            this.copySourceContentBtn.addEventListener("click", () => {
                navigator.clipboard.writeText(this.sourceModalContent.textContent).then(() => {
                    this.showToast("Đã sao chép đoạn trích dẫn!", "success");
                });
            });
        }

        // Close modal on click outside backdrop
        [this.kbModal, this.settingsModal, this.sourceModal].forEach(modal => {
            if (modal) {
                modal.addEventListener("click", (e) => {
                    if (e.target === modal) modal.classList.remove("active");
                });
            }
        });

        // Chat Form Submission
        if (this.chatForm) {
            this.chatForm.addEventListener("submit", (e) => {
                e.preventDefault();
                this.handleSubmit();
            });
        }

        // Textarea auto-resize and Enter key
        if (this.userInput) {
            this.userInput.addEventListener("keydown", (e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    this.handleSubmit();
                }
            });

            this.userInput.addEventListener("input", () => {
                this.userInput.style.height = "auto";
                this.userInput.style.height = Math.min(this.userInput.scrollHeight, 160) + "px";
            });
        }
    }

    // SUGGESTIONS RENDERING
    renderSuggestions() {
        if (!this.suggestionsGrid) return;
        this.suggestionsGrid.innerHTML = "";

        PROMPT_SUGGESTIONS.forEach(item => {
            const card = document.createElement("div");
            card.className = "suggestion-card";
            card.innerHTML = `
                <div class="sugg-header">
                    <div class="sugg-icon"><i class="${item.icon}"></i></div>
                    <span class="sugg-title">${item.title}</span>
                </div>
                <p class="sugg-desc">${item.desc}</p>
            `;
            card.addEventListener("click", () => {
                this.userInput.value = item.prompt;
                this.handleSubmit();
            });
            this.suggestionsGrid.appendChild(card);
        });
    }

    // THEME MANAGEMENT
    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
        const newTheme = currentTheme === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", newTheme);
        localStorage.setItem("ptit_theme", newTheme);
        this.updateThemeUI(newTheme);
    }

    updateThemeUI(theme) {
        if (!this.themeIcon || !this.themeText) return;
        if (theme === "light") {
            this.themeIcon.className = "fa-solid fa-sun";
            this.themeText.textContent = "Giao diện sáng";
        } else {
            this.themeIcon.className = "fa-solid fa-moon";
            this.themeText.textContent = "Giao diện tối";
        }
    }

    // SETTINGS MANAGEMENT
    loadSettings() {
        const saved = localStorage.getItem("ptit_settings");
        if (saved) {
            try {
                this.settings = Object.assign(this.settings, JSON.parse(saved));
            } catch (e) {
                console.error("Failed to parse settings:", e);
            }
        }
        const savedTheme = localStorage.getItem("ptit_theme") || "dark";
        document.documentElement.setAttribute("data-theme", savedTheme);
        this.updateThemeUI(savedTheme);
    }

    openSettings() {
        if (this.customApiKeyInput) this.customApiKeyInput.value = this.settings.apiKey || "";
        if (this.modelSelect) this.modelSelect.value = this.settings.model || "gemini-3.5-flash-lite";
        this.settingsModal.classList.add("active");
    }

    saveSettings() {
        this.settings.apiKey = this.customApiKeyInput ? this.customApiKeyInput.value.trim() : "";
        this.settings.model = this.modelSelect ? this.modelSelect.value : "gemini-3.5-flash-lite";

        localStorage.setItem("ptit_settings", JSON.stringify(this.settings));
        this.settingsModal.classList.remove("active");
        this.showToast("Đã lưu cài đặt thành công!", "success");
    }

    resetSettings() {
        this.settings = {
            apiKey: "",
            model: "gemini-3.5-flash-lite"
        };
        if (this.customApiKeyInput) this.customApiKeyInput.value = "";
        if (this.modelSelect) this.modelSelect.value = "gemini-3.5-flash-lite";
        localStorage.setItem("ptit_settings", JSON.stringify(this.settings));
        this.showToast("Đã khôi phục cài đặt mặc định.", "info");
    }

    // SESSIONS & HISTORY MANAGEMENT
    loadSessions() {
        const stored = localStorage.getItem("ptit_sessions");
        if (stored) {
            try {
                this.sessions = JSON.parse(stored);
            } catch (e) {
                this.sessions = [];
            }
        }
        this.renderHistoryList();
    }

    saveSessions() {
        localStorage.setItem("ptit_sessions", JSON.stringify(this.sessions));
        this.renderHistoryList();
    }

    createNewSession() {
        const newId = "session_" + Date.now();
        const newSession = {
            id: newId,
            title: "Cuộc trò chuyện mới",
            timestamp: Date.now(),
            messages: []
        };
        this.sessions.unshift(newSession);
        this.saveSessions();
        this.switchSession(newId);

        if (window.innerWidth <= 768 && this.sidebar) {
            this.sidebar.classList.remove("open");
        }
    }

    switchSession(sessionId) {
        this.currentSessionId = sessionId;
        const currentSession = this.sessions.find(s => s.id === sessionId);
        if (!currentSession) return;

        if (this.currentChatTitle) {
            this.currentChatTitle.textContent = currentSession.title || "Cuộc trò chuyện mới";
        }
        this.renderMessages(currentSession.messages);
        this.renderHistoryList();

        if (window.innerWidth <= 768 && this.sidebar) {
            this.sidebar.classList.remove("open");
        }
    }

    deleteSession(sessionId, e) {
        if (e) e.stopPropagation();
        this.sessions = this.sessions.filter(s => s.id !== sessionId);
        this.saveSessions();

        if (this.currentSessionId === sessionId) {
            if (this.sessions.length > 0) {
                this.switchSession(this.sessions[0].id);
            } else {
                this.createNewSession();
            }
        }
    }

    clearAllHistory() {
        if (confirm("Bạn có chắc chắn muốn xóa toàn bộ lịch sử trò chuyện không?")) {
            this.sessions = [];
            this.saveSessions();
            this.createNewSession();
            this.showToast("Đã xóa toàn bộ lịch sử trò chuyện.", "info");
        }
    }

    renderHistoryList() {
        if (!this.chatHistoryList) return;
        this.chatHistoryList.innerHTML = "";

        if (this.sessions.length === 0) {
            this.chatHistoryList.innerHTML = `
                <div class="empty-history">
                    <i class="fa-regular fa-comment-dots"></i>
                    <span>Chưa có cuộc trò chuyện nào</span>
                </div>
            `;
            return;
        }

        this.sessions.forEach(sess => {
            const item = document.createElement("div");
            item.className = `history-item ${sess.id === this.currentSessionId ? 'active' : ''}`;
            item.innerHTML = `
                <i class="fa-regular fa-message history-icon"></i>
                <span class="history-title">${this.escapeHtml(sess.title)}</span>
                <button class="delete-history-btn" title="Xóa">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            `;

            item.addEventListener("click", () => this.switchSession(sess.id));

            const delBtn = item.querySelector(".delete-history-btn");
            delBtn.addEventListener("click", (e) => this.deleteSession(sess.id, e));

            this.chatHistoryList.appendChild(item);
        });
    }

    renderMessages(messages) {
        if (!this.messageThread) return;
        this.messageThread.innerHTML = "";

        if (!messages || messages.length === 0) {
            if (this.welcomeHero) this.welcomeHero.style.display = "flex";
            return;
        }

        if (this.welcomeHero) this.welcomeHero.style.display = "none";
        messages.forEach(msg => this.appendMessageToDOM(msg, false));
        this.scrollToBottom();
    }

    appendMessageToDOM(msg, shouldScroll = true) {
        if (this.welcomeHero) this.welcomeHero.style.display = "none";

        const msgDiv = document.createElement("div");
        msgDiv.className = `message-item ${msg.role === 'user' ? 'user' : 'assistant'}`;

        const avatarDiv = document.createElement("div");
        avatarDiv.className = "message-avatar";
        if (msg.role === "user") {
            avatarDiv.innerHTML = '<i class="fa-regular fa-user"></i>';
        } else {
            avatarDiv.innerHTML = '<span>P</span>';
        }

        const wrapperDiv = document.createElement("div");
        wrapperDiv.className = "message-wrapper";

        const bubbleDiv = document.createElement("div");
        bubbleDiv.className = "message-bubble";

        if (msg.role === "user") {
            bubbleDiv.textContent = msg.content;
        } else {
            // Render Markdown & Tables
            const rawHtml = window.marked ? marked.parse(msg.content) : msg.content;
            bubbleDiv.innerHTML = rawHtml;

            // Enhance table layout & numbering
            bubbleDiv.querySelectorAll("table").forEach(table => {
                if (!table.parentElement.classList.contains("table-wrapper")) {
                    const wrap = document.createElement("div");
                    wrap.className = "table-wrapper";
                    table.parentNode.insertBefore(wrap, table);
                    wrap.appendChild(table);
                }

                // Clean OCR artifact rows
                table.querySelectorAll("tbody tr").forEach(row => {
                    const cells = Array.from(row.querySelectorAll("td"));
                    const isDummyCounterRow = cells.length >= 3 && cells.every((td, idx) => {
                        const val = td.textContent.trim().replace(/\*/g, "");
                        return val === "" || val === String(idx + 1);
                    });
                    if (isDummyCounterRow) {
                        row.remove();
                        return;
                    }
                    const nonEmpties = cells.filter(td => td.textContent.trim() !== "");
                    if (nonEmpties.length <= 1) {
                        row.remove();
                        return;
                    }
                });

                // Sequential STT counter if table has STT/TT column
                const headers = Array.from(table.querySelectorAll("th"));
                if (headers.length > 0) {
                    const firstHeader = headers[0].textContent.trim().toUpperCase();
                    if (firstHeader === "STT" || firstHeader === "TT") {
                        let sttCounter = 1;
                        table.querySelectorAll("tbody tr").forEach(row => {
                            const cells = Array.from(row.querySelectorAll("td"));
                            if (cells.length > 0) {
                                cells[0].textContent = sttCounter++;
                                cells[0].style.textAlign = "center";
                                cells[0].style.fontWeight = "600";
                            }
                        });
                    }
                }

                // Format money amounts nicely
                table.querySelectorAll("td").forEach(td => {
                    const txt = td.textContent.trim();
                    if (/^\d{1,3}(\.\d{3})+(\s*đ|\s*đồng|\s*VNĐ)?$/i.test(txt) || /đồng\/tín chỉ|VNĐ\/tín chỉ/i.test(txt)) {
                        td.style.whiteSpace = "nowrap";
                        td.style.fontWeight = "700";
                        td.style.color = "var(--primary)";
                        td.style.textAlign = "center";
                    }
                    if (/^Khóa\s*\d{4}/i.test(txt) || /^\d{4}/.test(txt)) {
                        td.style.whiteSpace = "nowrap";
                        td.style.textAlign = "center";
                    }
                });
            });

            // Citation Sources Accordion
            if (msg.sources && msg.sources.length > 0) {
                const sourcesContainer = document.createElement("div");
                sourcesContainer.className = "msg-sources-container";

                const toggleBtn = document.createElement("button");
                toggleBtn.className = "sources-toggle-btn";
                toggleBtn.innerHTML = `<i class="fa-solid fa-book-bookmark"></i> <span>Trích dẫn ${msg.sources.length} tài liệu đối chiếu</span> <i class="fa-solid fa-chevron-down"></i>`;

                const cardsList = document.createElement("div");
                cardsList.className = "sources-cards-list";
                cardsList.style.display = "none";

                msg.sources.forEach(src => {
                    const card = document.createElement("div");
                    card.className = "source-card-item";
                    card.innerHTML = `
                        <div class="source-info">
                            <span class="source-file-badge"><i class="fa-regular fa-file-pdf"></i> ${src.source}</span>
                            <span class="source-page-badge">Trang ${src.page}</span>
                            <span class="source-snippet">${this.escapeHtml(src.preview)}</span>
                        </div>
                        <i class="fa-solid fa-arrow-up-right-from-square" style="color: var(--text-muted); font-size: 0.75rem"></i>
                    `;
                    card.addEventListener("click", () => this.openSourceModal(src));
                    cardsList.appendChild(card);
                });

                toggleBtn.addEventListener("click", () => {
                    const isOpen = cardsList.style.display === "flex";
                    cardsList.style.display = isOpen ? "none" : "flex";
                    const icon = toggleBtn.querySelector(".fa-chevron-down, .fa-chevron-up");
                    if (icon) icon.className = isOpen ? "fa-solid fa-chevron-down" : "fa-solid fa-chevron-up";
                });

                sourcesContainer.appendChild(toggleBtn);
                sourcesContainer.appendChild(cardsList);
                bubbleDiv.appendChild(sourcesContainer);
            }
        }

        wrapperDiv.appendChild(bubbleDiv);

        // Action Buttons for Bot Message: Copy
        if (msg.role === "assistant") {
            const actionsDiv = document.createElement("div");
            actionsDiv.className = "msg-actions";

            const copyBtn = document.createElement("button");
            copyBtn.className = "msg-action-btn";
            copyBtn.innerHTML = '<i class="fa-regular fa-copy"></i> <span>Sao chép</span>';
            copyBtn.addEventListener("click", () => {
                navigator.clipboard.writeText(msg.content).then(() => {
                    this.showToast("Đã sao chép câu trả lời!", "success");
                });
            });

            actionsDiv.appendChild(copyBtn);
            wrapperDiv.appendChild(actionsDiv);
        }

        msgDiv.appendChild(avatarDiv);
        msgDiv.appendChild(wrapperDiv);

        this.messageThread.appendChild(msgDiv);
        if (shouldScroll) this.scrollToBottom();
    }

    scrollToBottom() {
        setTimeout(() => {
            if (this.chatMessagesArea) {
                this.chatMessagesArea.scrollTop = this.chatMessagesArea.scrollHeight;
            }
        }, 50);
    }

    // SUBMIT QUESTION
    async handleSubmit() {
        const text = this.userInput.value.trim();
        if (!text || this.isProcessing) return;

        this.userInput.value = "";
        this.userInput.style.height = "auto";

        let currentSession = this.sessions.find(s => s.id === this.currentSessionId);
        if (!currentSession) {
            this.createNewSession();
            currentSession = this.sessions.find(s => s.id === this.currentSessionId) || this.sessions[0];
        }

        // Set session title from first question
        if (currentSession.messages.length === 0) {
            currentSession.title = text.length > 28 ? text.substring(0, 28) + "..." : text;
            if (this.currentChatTitle) this.currentChatTitle.textContent = currentSession.title;
        }

        const userMsg = { role: "user", content: text };
        currentSession.messages.push(userMsg);
        this.saveSessions();
        this.appendMessageToDOM(userMsg, true);

        // Prepare UI state for waiting
        this.isProcessing = true;
        this.sendBtn.disabled = true;
        this.typingIndicator.classList.remove("hidden");
        this.scrollToBottom();

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 35000);

        try {
            const payload = {
                question: text,
                api_key: this.settings.apiKey || "",
                model: this.settings.model || "gemini-3.5-flash-lite",
                top_k: 4,
                history: currentSession.messages.slice(-5, -1)
            };

            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
                signal: controller.signal
            });

            clearTimeout(timeoutId);
            this.typingIndicator.classList.add("hidden");
            this.isProcessing = false;
            this.sendBtn.disabled = false;

            if (!response.ok) {
                throw new Error(`HTTP Error: ${response.status}`);
            }

            const data = await response.json();
            const botMsg = {
                role: "assistant",
                content: data.answer || "Không thể tạo câu trả lời.",
                sources: data.sources || [],
                model: data.model_used || ""
            };

            currentSession.messages.push(botMsg);
            this.saveSessions();
            this.appendMessageToDOM(botMsg, true);

        } catch (err) {
            clearTimeout(timeoutId);
            console.error("Fetch Error:", err);
            this.typingIndicator.classList.add("hidden");
            this.isProcessing = false;
            this.sendBtn.disabled = false;

            let errorText = `❌ **Lỗi kết nối:** Không thể liên lạc với máy chủ. Hãy đảm bảo lệnh \`python app.py\` đang chạy bình thường.`;
            if (err.name === 'AbortError') {
                errorText = `⏱️ **Thời gian chờ phản hồi quá lâu.** Bạn có thể thử lại hoặc cấu hình Gemini API Key cá nhân trong phần Cài đặt.`;
            }

            const netErrorMsg = {
                role: "assistant",
                content: errorText,
                sources: []
            };
            currentSession.messages.push(netErrorMsg);
            this.saveSessions();
            this.appendMessageToDOM(netErrorMsg, true);
        }
    }

    // SOURCE MODAL
    openSourceModal(src) {
        if (!this.sourceModal) return;
        this.sourceModalTitle.textContent = `${src.source} - Trang ${src.page}`;
        this.sourceModalSubtitle.textContent = `Phân loại: [${src.type}] • Trích xuất nguyên bản từ cơ sở dữ liệu PTIT`;
        this.sourceModalContent.textContent = src.full_content || src.preview;
        this.sourceModal.classList.add("active");
    }

    // KNOWLEDGE BASE MODAL & STATUS
    async fetchKBStatus() {
        try {
            const res = await fetch("/api/status");
            const data = await res.json();
            if (data.chunks_count !== undefined) {
                if (this.sidebarChunksCount) this.sidebarChunksCount.textContent = data.chunks_count;
                if (this.modalTotalChunks) this.modalTotalChunks.textContent = data.chunks_count;
            }
        } catch (e) {
            console.warn("Could not fetch KB status:", e);
        }
    }

    async openCatalogModal() {
        this.kbModal.classList.add("active");
        try {
            const res = await fetch("/api/sources");
            const data = await res.json();
            if (data.sources && this.catalogGrid) {
                this.catalogGrid.innerHTML = "";
                data.sources.forEach(item => {
                    const card = document.createElement("div");
                    card.className = "catalog-card";
                    card.innerHTML = `
                        <div class="catalog-item-header">
                            <span class="catalog-cat-badge">${item.category}</span>
                            <span class="catalog-chunks-badge">${item.chunks} chunks</span>
                        </div>
                        <h4 class="catalog-item-title">${item.title}</h4>
                        <p class="catalog-item-desc">${item.desc}</p>
                        <div class="catalog-item-meta">
                            <span><i class="fa-regular fa-file-pdf"></i> ${item.name}</span>
                            <span>Kích thước: <strong>${item.file_size}</strong></span>
                        </div>
                    `;
                    this.catalogGrid.appendChild(card);
                });
            }
        } catch (e) {
            console.error("Error loading sources catalog:", e);
        }
    }

    // TOAST UTILITY
    showToast(message, type = "info") {
        if (!this.toastContainer) return;
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        const icon = type === "success" ? "fa-circle-check" : (type === "error" ? "fa-circle-exclamation" : "fa-circle-info");
        toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${this.escapeHtml(message)}</span>`;
        this.toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(20px)";
            toast.style.transition = "all 0.25s ease";
            setTimeout(() => toast.remove(), 250);
        }, 2800);
    }

    escapeHtml(str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
}

// Khởi chạy khi DOM sẵn sàng
document.addEventListener("DOMContentLoaded", () => {
    window.ptitApp = new PTITChatApp();
});
