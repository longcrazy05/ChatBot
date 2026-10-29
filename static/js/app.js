/**
 * PTIT SMART ASSISTANT - CLIENT APPLICATION
 * Features: RAG Chatting, Markdown & Table Rendering, TTS/STT, Chat History,
 * Sources Inspector, Custom Settings & Document Catalog.
 */

// SUGGESTIONS DATA REPOSITORY
const PROMPT_SUGGESTIONS = [
    {
        cat: "tuition",
        icon: "fa-solid fa-coins",
        title: "Học phí CNTT năm 2025",
        desc: "Mức thu học phí một tín chỉ và toàn khóa của ngành Công nghệ Thông tin là bao nhiêu?",
        prompt: "Mức thu học phí ngành Công nghệ Thông tin theo văn bản hp_2025 là bao nhiêu tiền một tín chỉ?"
    },
    {
        cat: "tuition",
        icon: "fa-solid fa-chart-line",
        title: "So sánh Học phí 2025 & 2026",
        desc: "Khung học phí năm học 2025-2026 có những điều chỉnh gì so với năm 2024-2025?",
        prompt: "So sánh mức thu học phí giữa năm 2024-2025 và năm học 2025-2026 của các hệ đào tạo chính quy?"
    },
    {
        cat: "curriculum",
        icon: "fa-solid fa-graduation-cap",
        title: "Khối lượng Tín chỉ CNTT",
        desc: "Chương trình đào tạo đại học ngành CNTT yêu cầu tích lũy tối thiểu bao nhiêu tín chỉ?",
        prompt: "Tổng khối lượng kiến thức toàn khóa của chương trình đào tạo ngành Công nghệ thông tin là bao nhiêu tín chỉ?"
    },
    {
        cat: "curriculum",
        icon: "fa-solid fa-laptop-code",
        title: "Các môn Chuyên ngành CNTT",
        desc: "Danh sách các môn học cơ sở ngành và chuyên ngành bắt buộc trong khung đào tạo CNTT?",
        prompt: "Liệt kê danh sách các môn học bắt buộc và chuyên ngành trong chương trình đào tạo CNTT?"
    },
    {
        cat: "rules",
        icon: "fa-solid fa-award",
        title: "Học bổng Khuyến khích PTIT",
        desc: "Điều kiện điểm học tập và điểm rèn luyện để được xét cấp học bổng khuyến khích?",
        prompt: "Điều kiện và tiêu chuẩn để sinh viên PTIT được xét cấp học bổng khuyến khích học tập là gì?"
    },
    {
        cat: "rules",
        icon: "fa-solid fa-book-bookmark",
        title: "Quy chế Đăng ký môn & Học lại",
        desc: "Quy định về việc đăng ký tín chỉ tối thiểu, học lại và học cải thiện điểm thế nào?",
        prompt: "Theo sổ tay sinh viên, quy định về số tín chỉ đăng ký tối thiểu mỗi học kỳ và quy chế học lại ra sao?"
    }
];

class PTITChatApp {
    constructor() {
        this.currentSessionId = null;
        this.sessions = [];
        this.settings = {
            apiKey: "",
            model: "gemini-3.1-flash-lite",
            topK: 4,
            autoVoice: false
        };
        this.currentCategory = "all";
        this.isProcessing = false;
        this.currentUtterance = null;
        this.recognition = null;

        this.init();
    }

    init() {
        this.bindElements();
        this.setupMarkdown();
        this.loadSettings();
        this.loadSessions();
        this.bindEvents();
        this.initSpeechRecognition();
        this.fetchKBStatus();
        this.renderCategorySuggestions();

        // Start or load first session
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
        this.chatHistoryList = document.getElementById("chatHistoryList");
        this.clearAllHistoryBtn = document.getElementById("clearAllHistoryBtn");
        this.currentChatTitle = document.getElementById("currentChatTitle");
        this.modelBadgeDisplay = document.getElementById("modelBadgeDisplay");
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
        this.voiceInputBtn = document.getElementById("voiceInputBtn");
        this.exportChatBtn = document.getElementById("exportChatBtn");
        this.clearCurrentChatBtn = document.getElementById("clearCurrentChatBtn");

        // Modals
        this.kbModal = document.getElementById("kbModal");
        this.openKbModalBtn = document.getElementById("openKbModalBtn");
        this.viewDocsNavbarBtn = document.getElementById("viewDocsNavbarBtn");
        this.closeKbModalBtn = document.getElementById("closeKbModalBtn");
        this.closeKbModalFooterBtn = document.getElementById("closeKbModalFooterBtn");
        this.catalogGrid = document.getElementById("catalogGrid");
        this.totalChunksDisplay = document.getElementById("totalChunksDisplay");
        this.modalTotalChunks = document.getElementById("modalTotalChunks");

        this.settingsModal = document.getElementById("settingsModal");
        this.openSettingsBtn = document.getElementById("openSettingsBtn");
        this.closeSettingsModalBtn = document.getElementById("closeSettingsModalBtn");
        this.saveSettingsBtn = document.getElementById("saveSettingsBtn");
        this.resetSettingsBtn = document.getElementById("resetSettingsBtn");
        this.customApiKeyInput = document.getElementById("customApiKeyInput");
        this.modelSelect = document.getElementById("modelSelect");
        this.topKInput = document.getElementById("topKInput");
        this.topKValue = document.getElementById("topKValue");
        this.autoVoiceToggle = document.getElementById("autoVoiceToggle");

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
        // Theme Toggle
        this.themeToggleBtn.addEventListener("click", () => this.toggleTheme());

        // Sidebar Mobile
        this.openSidebarBtn.addEventListener("click", () => this.sidebar.classList.add("open"));
        this.closeSidebarBtn.addEventListener("click", () => this.sidebar.classList.remove("open"));

        // Sessions
        this.newChatBtn.addEventListener("click", () => this.createNewSession());
        this.clearAllHistoryBtn.addEventListener("click", () => this.clearAllHistory());
        this.clearCurrentChatBtn.addEventListener("click", () => this.clearCurrentChat());
        this.exportChatBtn.addEventListener("click", () => this.exportCurrentChat());

        // Chat Input & Auto-grow
        this.userInput.addEventListener("input", () => this.autoGrowTextarea());
        this.userInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                this.handleSubmit();
            }
        });
        this.chatForm.addEventListener("submit", (e) => {
            e.preventDefault();
            this.handleSubmit();
        });

        // Quick prompt chips
        document.querySelectorAll(".quick-chip").forEach(chip => {
            chip.addEventListener("click", () => {
                const prompt = chip.getAttribute("data-prompt");
                if (prompt) {
                    this.userInput.value = prompt;
                    this.autoGrowTextarea();
                    this.handleSubmit();
                }
            });
        });

        // Category filter tabs
        document.querySelectorAll(".cat-pill").forEach(tab => {
            tab.addEventListener("click", () => {
                document.querySelectorAll(".cat-pill").forEach(t => t.classList.remove("active"));
                tab.classList.add("active");
                this.currentCategory = tab.getAttribute("data-cat");
                this.renderCategorySuggestions();
            });
        });

        // Modals Open/Close
        if (this.openKbModalBtn) this.openKbModalBtn.addEventListener("click", () => this.openKbModal());
        if (this.viewDocsNavbarBtn) this.viewDocsNavbarBtn.addEventListener("click", () => this.openKbModal());
        if (this.closeKbModalBtn) this.closeKbModalBtn.addEventListener("click", () => this.kbModal && this.kbModal.classList.remove("active"));
        if (this.closeKbModalFooterBtn) this.closeKbModalFooterBtn.addEventListener("click", () => this.kbModal && this.kbModal.classList.remove("active"));

        if (this.openSettingsBtn) this.openSettingsBtn.addEventListener("click", () => this.openSettingsModal());
        if (this.closeSettingsModalBtn) this.closeSettingsModalBtn.addEventListener("click", () => this.settingsModal && this.settingsModal.classList.remove("active"));
        if (this.saveSettingsBtn) this.saveSettingsBtn.addEventListener("click", () => this.saveSettings());
        if (this.resetSettingsBtn) this.resetSettingsBtn.addEventListener("click", () => this.resetSettings());

        if (this.topKInput) {
            this.topKInput.addEventListener("input", () => {
                if (this.topKValue) this.topKValue.textContent = this.topKInput.value;
            });
        }

        if (this.closeSourceModalBtn) this.closeSourceModalBtn.addEventListener("click", () => this.sourceModal && this.sourceModal.classList.remove("active"));
        if (this.closeSourceModalFooterBtn) this.closeSourceModalFooterBtn.addEventListener("click", () => this.sourceModal && this.sourceModal.classList.remove("active"));
        if (this.copySourceContentBtn) {
            this.copySourceContentBtn.addEventListener("click", () => {
                navigator.clipboard.writeText(this.sourceModalContent ? this.sourceModalContent.textContent : "").then(() => {
                    this.showToast("Đã sao chép nội dung!", "success");
                });
            });
        }

        // Voice Input
        if (this.voiceInputBtn) this.voiceInputBtn.addEventListener("click", () => this.toggleVoiceInput());

        // Close modals on backdrop click
        [this.kbModal, this.settingsModal, this.sourceModal].filter(Boolean).forEach(modal => {
            modal.addEventListener("click", (e) => {
                if (e.target === modal) modal.classList.remove("active");
            });
        });
    }

    autoGrowTextarea() {
        this.userInput.style.height = "auto";
        this.userInput.style.height = Math.min(this.userInput.scrollHeight, 160) + "px";
    }

    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
        const newTheme = currentTheme === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", newTheme);
        localStorage.setItem("ptit_chat_theme", newTheme);
        this.updateThemeUI(newTheme);
    }

    updateThemeUI(theme) {
        if (!this.themeIcon || !this.themeText) return;
        if (theme === "dark") {
            this.themeIcon.className = "fa-solid fa-moon";
            this.themeText.textContent = "Giao diện Tối";
        } else {
            this.themeIcon.className = "fa-solid fa-sun";
            this.themeText.textContent = "Giao diện Sáng";
        }
    }

    loadSettings() {
        const savedTheme = localStorage.getItem("ptit_chat_theme") || "dark";
        document.documentElement.setAttribute("data-theme", savedTheme);
        setTimeout(() => this.updateThemeUI(savedTheme), 0);

        const savedSettings = localStorage.getItem("ptit_chat_settings");
        if (savedSettings) {
            try {
                this.settings = { ...this.settings, ...JSON.parse(savedSettings) };
                const validModels = [
                    "gemini-3.1-flash-lite",
                    "gemini-3.5-flash-lite",
                    "gemini-flash-lite-latest",
                    "gemini-3-flash-preview",
                    "gemini-3.6-flash",
                    "gemini-flash-latest",
                    "gemini-3.5-flash",
                    "gemini-3.7-flash"
                ];
                if (!this.settings.model || !validModels.includes(this.settings.model) || this.settings.model === "gemini-2.5-flash" || this.settings.model === "gemini-3.6-flash") {
                    this.settings.model = "gemini-3.1-flash-lite";
                    localStorage.setItem("ptit_chat_settings", JSON.stringify(this.settings));
                }
            } catch (e) {
                console.error("Lỗi đọc cài đặt:", e);
            }
        }
    }

    openSettingsModal() {
        this.customApiKeyInput.value = this.settings.apiKey || "";
        this.modelSelect.value = this.settings.model || "gemini-3.1-flash-lite";
        this.topKInput.value = this.settings.topK || 4;
        this.topKValue.textContent = this.topKInput.value;
        this.autoVoiceToggle.checked = !!this.settings.autoVoice;
        this.settingsModal.classList.add("active");
    }

    saveSettings() {
        this.settings.apiKey = this.customApiKeyInput.value.trim();
        this.settings.model = this.modelSelect.value;
        this.settings.topK = parseInt(this.topKInput.value, 10) || 4;
        this.settings.autoVoice = this.autoVoiceToggle.checked;

        localStorage.setItem("ptit_chat_settings", JSON.stringify(this.settings));
        this.modelBadgeDisplay.textContent = this.settings.model;
        this.settingsModal.classList.remove("active");
        this.showToast("Đã lưu cấu hình RAG thành công!", "success");
    }

    resetSettings() {
        this.settings = {
            apiKey: "",
            model: "gemini-3.1-flash-lite",
            topK: 4,
            autoVoice: false
        };
        this.customApiKeyInput.value = "";
        this.modelSelect.value = "gemini-3.1-flash-lite";
        this.topKInput.value = 4;
        this.topKValue.textContent = "4";
        this.autoVoiceToggle.checked = false;
        localStorage.removeItem("ptit_chat_settings");
        this.modelBadgeDisplay.textContent = "gemini-3.1-flash-lite";
        this.showToast("Đã khôi phục cài đặt mặc định.", "info");
    }

    renderCategorySuggestions() {
        if (!this.suggestionsGrid) return;
        this.suggestionsGrid.innerHTML = "";
        const list = this.currentCategory === "all"
            ? PROMPT_SUGGESTIONS
            : PROMPT_SUGGESTIONS.filter(item => item.cat === this.currentCategory);

        list.forEach(item => {
            const card = document.createElement("div");
            card.className = "suggestion-card";
            card.innerHTML = `
                <div class="sugg-icon"><i class="${item.icon}"></i></div>
                <div class="sugg-content">
                    <h4 class="sugg-title">${item.title}</h4>
                    <p class="sugg-desc">${item.desc}</p>
                </div>
            `;
            card.addEventListener("click", () => {
                this.userInput.value = item.prompt;
                this.autoGrowTextarea();
                this.handleSubmit();
            });
            this.suggestionsGrid.appendChild(card);
        });
    }

    // SESSION / HISTORY MANAGEMENT
    loadSessions() {
        const stored = localStorage.getItem("ptit_chat_sessions");
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
        localStorage.setItem("ptit_chat_sessions", JSON.stringify(this.sessions));
        this.renderHistoryList();
    }

    createNewSession() {
        const newSession = {
            id: "chat_" + Date.now(),
            title: "Đoạn chat mới",
            createdAt: new Date().toISOString(),
            messages: []
        };
        this.sessions.unshift(newSession);
        this.saveSessions();
        this.switchSession(newSession.id);
        if (window.innerWidth <= 768) {
            this.sidebar.classList.remove("open");
        }
    }

    switchSession(sessionId) {
        this.currentSessionId = sessionId;
        const session = this.sessions.find(s => s.id === sessionId);
        if (!session) return;

        this.currentChatTitle.textContent = session.title;
        this.renderMessages(session.messages);
        this.renderHistoryList();
    }

    deleteSession(sessionId, event) {
        if (event) event.stopPropagation();
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

    clearCurrentChat() {
        const session = this.sessions.find(s => s.id === this.currentSessionId);
        if (session) {
            session.messages = [];
            session.title = "Đoạn chat mới";
            this.currentChatTitle.textContent = session.title;
            this.saveSessions();
            this.renderMessages([]);
            this.showToast("Đã xóa nội dung đoạn chat hiện tại.", "info");
        }
    }

    clearAllHistory() {
        if (confirm("Bạn có chắc chắn muốn xóa toàn bộ lịch sử trò chuyện?")) {
            this.sessions = [];
            localStorage.removeItem("ptit_chat_sessions");
            this.createNewSession();
            this.showToast("Đã dọn sạch toàn bộ lịch sử.", "info");
        }
    }

    renderHistoryList() {
        if (!this.chatHistoryList) return;
        this.chatHistoryList.innerHTML = "";
        if (this.sessions.length === 0) {
            this.chatHistoryList.innerHTML = `<div style="padding: 12px; color: var(--text-muted); font-size: 0.8rem; text-align: center;">Chưa có lịch sử</div>`;
            return;
        }

        this.sessions.forEach(sess => {
            const item = document.createElement("div");
            item.className = `history-item ${sess.id === this.currentSessionId ? "active" : ""}`;
            item.innerHTML = `
                <i class="fa-regular fa-message" style="font-size: 0.82rem"></i>
                <span class="history-item-title">${this.escapeHtml(sess.title)}</span>
                <button class="history-delete-btn" title="Xóa đoạn chat"><i class="fa-solid fa-trash-can"></i></button>
            `;
            item.addEventListener("click", () => this.switchSession(sess.id));
            item.querySelector(".history-delete-btn").addEventListener("click", (e) => this.deleteSession(sess.id, e));
            this.chatHistoryList.appendChild(item);
        });
    }

    renderMessages(messages) {
        if (!this.messageThread || !this.welcomeHero) return;
        this.messageThread.innerHTML = "";
        if (!messages || messages.length === 0) {
            this.welcomeHero.style.display = "flex";
            return;
        }

        this.welcomeHero.style.display = "none";
        messages.forEach(msg => {
            this.appendMessageToDOM(msg, false);
        });
        this.scrollToBottom();
    }

    appendMessageToDOM(msg, shouldScroll = true) {
        this.welcomeHero.style.display = "none";

        const msgDiv = document.createElement("div");
        msgDiv.className = `chat-message ${msg.role === "user" ? "user-message" : "bot-message"}`;

        const avatarDiv = document.createElement("div");
        avatarDiv.className = "msg-avatar";
        avatarDiv.innerHTML = msg.role === "user" ? '<i class="fa-solid fa-user"></i>' : '<span>P</span>';

        const wrapperDiv = document.createElement("div");
        wrapperDiv.className = "msg-bubble-wrapper";

        const bubbleDiv = document.createElement("div");
        bubbleDiv.className = "msg-bubble";

        if (msg.role === "user") {
            bubbleDiv.textContent = msg.content;
        } else {
            // Render Bot Markdown with LaTeX cleanup
            let textToRender = msg.content || "";
            textToRender = textToRender.replace(/\$\s*\\ge(q)?\s*([^$]+)\$/g, "từ $2 trở lên");
            textToRender = textToRender.replace(/\$\s*\\le(q)?\s*([^$]+)\$/g, "dưới hoặc bằng $2");
            textToRender = textToRender.replace(/\$\s*\\ge(q)?\s*\$/g, "từ ");
            textToRender = textToRender.replace(/\$\s*\\le(q)?\s*\$/g, "dưới hoặc bằng ");
            textToRender = textToRender.replace(/\\ge(q)?\b/g, ">=");
            textToRender = textToRender.replace(/\\le(q)?\b/g, "<=");
            textToRender = textToRender.replace(/\$([^$]+)\$/g, "$1");
            textToRender = textToRender.replace(/\$/g, "");

            let htmlContent = textToRender;
            if (window.marked) {
                htmlContent = marked.parse(textToRender);
            }
            bubbleDiv.innerHTML = htmlContent;

            // Wrap any tables in table-wrapper for horizontal scroll and clean formatting
            bubbleDiv.querySelectorAll("table").forEach(table => {
                if (!table.parentElement.classList.contains("table-wrapper")) {
                    const wrap = document.createElement("div");
                    wrap.className = "table-wrapper";
                    table.parentNode.insertBefore(wrap, table);
                    wrap.appendChild(table);
                }

                // Loại bỏ dòng đánh số cột scan rác như: | 1 | 2 | 3 | 4 | 5 |
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

                    // Loại bỏ dòng tiêu đề nhóm hoặc ô rác (ví dụ: | III | Khóa 2025 | | |)
                    const nonEmpties = cells.filter(td => td.textContent.trim() !== "");
                    if (nonEmpties.length <= 1) {
                        row.remove();
                        return;
                    }
                });

                // Chuẩn hóa cột STT (1, 2, 3...) nếu cột đầu tiên là STT hoặc TT
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

                // Căn chỉnh số tiền và đơn vị, tuyệt đối không ngắt dòng số hoặc đơn vị
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

            // Sources display disabled per user request
        }

        wrapperDiv.appendChild(bubbleDiv);

        // Action Buttons for Bot Message (Copy, TTS)
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

            const speakBtn = document.createElement("button");
            speakBtn.className = "msg-action-btn";
            speakBtn.innerHTML = '<i class="fa-solid fa-volume-high"></i> <span>Đọc</span>';
            speakBtn.addEventListener("click", () => this.toggleSpeech(msg.content, speakBtn));

            actionsDiv.appendChild(copyBtn);
            actionsDiv.appendChild(speakBtn);
            wrapperDiv.appendChild(actionsDiv);
        }

        msgDiv.appendChild(avatarDiv);
        msgDiv.appendChild(wrapperDiv);

        this.messageThread.appendChild(msgDiv);
        if (shouldScroll) this.scrollToBottom();
    }

    scrollToBottom() {
        setTimeout(() => {
            this.chatMessagesArea.scrollTop = this.chatMessagesArea.scrollHeight;
        }, 50);
    }

    // SUBMIT QUESTION
    async handleSubmit() {
        const text = this.userInput.value.trim();
        if (!text || this.isProcessing) return;

        // Reset Textarea
        this.userInput.value = "";
        this.userInput.style.height = "auto";

        let currentSession = this.sessions.find(s => s.id === this.currentSessionId);
        if (!currentSession) {
            this.createNewSession();
            currentSession = this.sessions.find(s => s.id === this.currentSessionId) || this.sessions[0];
        }

        // Set title on first message
        if (currentSession.messages.length === 0) {
            currentSession.title = text.length > 32 ? text.substring(0, 32) + "..." : text;
            this.currentChatTitle.textContent = currentSession.title;
        }

        // Add User Message
        const userMsg = { role: "user", content: text, timestamp: new Date().toISOString() };
        currentSession.messages.push(userMsg);
        this.saveSessions();
        this.appendMessageToDOM(userMsg, true);

        // Show Typing Indicator
        this.isProcessing = true;
        this.sendBtn.disabled = true;
        this.typingIndicator.classList.remove("hidden");
        this.typingLabel.textContent = "Đang tra cứu Vector DB & tạo câu trả lời...";
        this.scrollToBottom();

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 45000);

        try {
            const payload = {
                question: text,
                api_key: this.settings.apiKey,
                model: this.settings.model,
                top_k: this.settings.topK,
                history: currentSession.messages.slice(-6)
            };

            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            const data = await response.json();

            this.typingIndicator.classList.add("hidden");
            this.isProcessing = false;
            this.sendBtn.disabled = false;

            if (data.error) {
                const errorMsg = {
                    role: "assistant",
                    content: `❌ **Đã xảy ra lỗi:** ${data.error}`,
                    sources: []
                };
                currentSession.messages.push(errorMsg);
                this.saveSessions();
                this.appendMessageToDOM(errorMsg, true);
                return;
            }

            const botMsg = {
                role: "assistant",
                content: data.answer || "Không nhận được phản hồi từ hệ thống.",
                sources: data.sources || [],
                model_used: data.model_used,
                timestamp: new Date().toISOString()
            };

            currentSession.messages.push(botMsg);
            this.saveSessions();
            this.appendMessageToDOM(botMsg, true);

            // Auto-voice if enabled
            if (this.settings.autoVoice) {
                this.speakText(botMsg.content);
            }

        } catch (err) {
            clearTimeout(timeoutId);
            console.error("Fetch Error:", err);
            this.typingIndicator.classList.add("hidden");
            this.isProcessing = false;
            this.sendBtn.disabled = false;

            let errorText = `❌ **Lỗi kết nối máy chủ:** Không thể liên lạc với backend Flask. Vui lòng kiểm tra lại terminal xem lệnh 'python app.py' có đang chạy không.`;
            if (err.name === 'AbortError') {
                errorText = `⏱️ **Hết thời gian chờ (Timeout):** Máy chủ phản hồi quá lâu. Bạn hãy thử lại hoặc nhập Gemini API Key cá nhân trong phần Cài đặt (⚙️) nhé.`;
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
        this.sourceModalTitle.textContent = `${src.source} - Trang ${src.page}`;
        this.sourceModalSubtitle.textContent = `Phân loại: [${src.type}] • Trích xuất nguyên bản từ cơ sở tri thức PTIT`;
        this.sourceModalContent.textContent = src.full_content || src.preview;
        this.sourceModal.classList.add("active");
    }

    // KNOWLEDGE BASE MODAL & STATUS
    async fetchKBStatus() {
        try {
            const res = await fetch("/api/status");
            const data = await res.json();
            if (data.chunks_count !== undefined) {
                this.totalChunksDisplay.textContent = `${data.chunks_count} Chunks`;
                this.modalTotalChunks.textContent = `${data.chunks_count} Chunks`;
            }
        } catch (e) {
            console.warn("Could not fetch KB status:", e);
        }
    }

    async openKbModal() {
        this.kbModal.classList.add("active");
        try {
            const res = await fetch("/api/sources");
            const data = await res.json();
            if (data.catalog) {
                this.catalogGrid.innerHTML = "";
                data.catalog.forEach(item => {
                    const card = document.createElement("div");
                    card.className = "catalog-item-card";
                    card.innerHTML = `
                        <div class="catalog-item-header">
                            <span class="catalog-cat-tag">${item.category}</span>
                            <span style="font-size: 0.75rem; color: var(--accent-green); font-weight: 600;"><i class="fa-solid fa-circle-check"></i> Đã số hóa</span>
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

    // SPEECH SYNTHESIS (TTS)
    toggleSpeech(text, btnElement) {
        if (!('speechSynthesis' in window)) {
            this.showToast("Trình duyệt không hỗ trợ đọc giọng nói Text-to-Speech.", "info");
            return;
        }

        if (window.speechSynthesis.speaking) {
            window.speechSynthesis.cancel();
            document.querySelectorAll(".msg-action-btn.active").forEach(b => b.classList.remove("active"));
            if (this.currentUtteranceText === text) {
                this.currentUtteranceText = null;
                return;
            }
        }

        this.speakText(text, btnElement);
    }

    speakText(text, btnElement = null) {
        if (!('speechSynthesis' in window)) return;
        window.speechSynthesis.cancel();

        // Strip Markdown tags for smooth voice reading
        const plainText = text
            .replace(/[#*_`~\[\]\(\)>|]/g, " ")
            .replace(/\s+/g, " ")
            .trim();

        const utterance = new SpeechSynthesisUtterance(plainText);
        utterance.lang = "vi-VN";
        utterance.rate = 1.0;

        // Try to pick a Vietnamese voice
        const voices = window.speechSynthesis.getVoices();
        const viVoice = voices.find(v => v.lang.includes("vi") || v.name.includes("Vietnamese"));
        if (viVoice) utterance.voice = viVoice;

        if (btnElement) {
            btnElement.classList.add("active");
            btnElement.querySelector("span").textContent = "Dừng";
        }

        this.currentUtteranceText = text;

        utterance.onend = () => {
            if (btnElement) {
                btnElement.classList.remove("active");
                btnElement.querySelector("span").textContent = "Đọc";
            }
            this.currentUtteranceText = null;
        };

        utterance.onerror = () => {
            if (btnElement) {
                btnElement.classList.remove("active");
                btnElement.querySelector("span").textContent = "Đọc";
            }
            this.currentUtteranceText = null;
        };

        window.speechSynthesis.speak(utterance);
    }

    // SPEECH RECOGNITION (STT)
    initSpeechRecognition() {
        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRec) {
            this.recognition = new SpeechRec();
            this.recognition.lang = "vi-VN";
            this.recognition.continuous = false;
            this.recognition.interimResults = false;

            this.recognition.onstart = () => {
                this.voiceInputBtn.classList.add("listening");
                this.voiceInputBtn.title = "Đang lắng nghe giọng nói của bạn...";
                this.showToast("Đang lắng nghe... Hãy nói câu hỏi của bạn!", "info");
            };

            this.recognition.onresult = (event) => {
                const speechResult = event.results[0][0].transcript;
                this.userInput.value = speechResult;
                this.autoGrowTextarea();
                this.handleSubmit();
            };

            this.recognition.onerror = (event) => {
                console.warn("Speech recognition error:", event.error);
                this.voiceInputBtn.classList.remove("listening");
                this.showToast("Không nhận diện được giọng nói hoặc micro bị từ chối.", "error");
            };

            this.recognition.onend = () => {
                this.voiceInputBtn.classList.remove("listening");
                this.voiceInputBtn.title = "Nhập câu hỏi bằng giọng nói";
            };
        } else {
            this.voiceInputBtn.style.display = "none";
        }
    }

    toggleVoiceInput() {
        if (!this.recognition) {
            this.showToast("Trình duyệt không hỗ trợ nhận diện giọng nói tiếng Việt.", "info");
            return;
        }
        try {
            this.recognition.start();
        } catch (e) {
            this.recognition.stop();
        }
    }

    // EXPORT CHAT
    exportCurrentChat() {
        const session = this.sessions.find(s => s.id === this.currentSessionId);
        if (!session || session.messages.length === 0) {
            this.showToast("Đoạn chat hiện tại chưa có nội dung để xuất.", "info");
            return;
        }

        let mdContent = `# ${session.title}\n`;
        mdContent += `*Thời gian xuất: ${new Date().toLocaleString("vi-VN")}*\n\n---\n\n`;

        session.messages.forEach(m => {
            const sender = m.role === "user" ? "👤 **Sinh viên**" : "🎓 **Trợ lý PTIT**";
            mdContent += `### ${sender}\n\n${m.content}\n\n`;
            if (m.sources && m.sources.length > 0) {
                mdContent += `**Tài liệu tham khảo:**\n`;
                m.sources.forEach(s => {
                    mdContent += `- \`${s.source}\` (Trang ${s.page})\n`;
                });
                mdContent += `\n`;
            }
            mdContent += `---\n\n`;
        });

        const blob = new Blob([mdContent], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${session.title.replace(/[^\w\s-]/gi, '_')}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        this.showToast("Đã tải xuống file ghi chép Markdown!", "success");
    }

    // TOAST UTILITY
    showToast(message, type = "info") {
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        const icon = type === "success" ? "fa-circle-check" : (type === "error" ? "fa-circle-exclamation" : "fa-circle-info");
        toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${this.escapeHtml(message)}</span>`;
        this.toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(30px)";
            toast.style.transition = "all 0.3s ease";
            setTimeout(() => toast.remove(), 300);
        }, 3200);
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

// Instantiate on DOM Loaded
document.addEventListener("DOMContentLoaded", () => {
    window.ptitApp = new PTITChatApp();
});
