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
            model: "gemini-3-flash-preview",
            topK: 6,
            autoVoice: false,
            voiceURI: ""
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
        this.autoGrowTextarea();
        this.initSpeechSynthesis();
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

        // File Upload & Attachment Elements
        this.fileUploadInput = document.getElementById("fileUploadInput");
        this.uploadFileBtn = document.getElementById("uploadFileBtn");
        this.attachmentPreview = document.getElementById("attachmentPreview");
        this.attachmentFilename = document.getElementById("attachmentFilename");
        this.attachmentFilesize = document.getElementById("attachmentFilesize");
        this.attachmentIcon = document.getElementById("attachmentIcon");
        this.removeAttachmentBtn = document.getElementById("removeAttachmentBtn");
        this.attachedFile = null;

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
        this.voiceSelect = document.getElementById("voiceSelect");
        this.testVoiceBtn = document.getElementById("testVoiceBtn");

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

        // File Upload Listeners
        if (this.uploadFileBtn && this.fileUploadInput) {
            this.uploadFileBtn.addEventListener("click", () => this.fileUploadInput.click());
            this.fileUploadInput.addEventListener("change", (e) => {
                const file = e.target.files && e.target.files[0];
                if (file) this.setAttachedFile(file);
            });
        }

        if (this.removeAttachmentBtn) {
            this.removeAttachmentBtn.addEventListener("click", () => this.clearAttachedFile());
        }

        // Drag and Drop files onto chat area
        const inputArea = document.querySelector(".chat-input-area");
        if (inputArea) {
            ["dragenter", "dragover"].forEach(evtName => {
                inputArea.addEventListener(evtName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    inputArea.classList.add("drag-over");
                });
            });
            ["dragleave", "drop"].forEach(evtName => {
                inputArea.addEventListener(evtName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    inputArea.classList.remove("drag-over");
                });
            });
            inputArea.addEventListener("drop", (e) => {
                const dt = e.dataTransfer;
                if (dt && dt.files && dt.files.length > 0) {
                    this.setAttachedFile(dt.files[0]);
                }
            });
        }

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
        if (this.testVoiceBtn) {
            this.testVoiceBtn.addEventListener("click", () => {
                const sampleText = "Xin chào bạn! Tôi là Trợ lý Ảo AI chính thức của Học viện Công nghệ Bưu chính Viễn thông PTIT.";
                this.speakText(sampleText, null, this.voiceSelect ? this.voiceSelect.value : null);
            });
        }

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
        this.initQuickModelSelector();
    }

    getModelDisplayLabel(modelId) {
        const labels = {
            "gemini-3-flash-preview": "3 Flash Preview (Khuyên dùng • Siêu tốc)",
            "gemini-3.5-flash": "3.5 Flash (Cân bằng)",
            "gemini-flash-lite-latest": "Flash Lite Latest (Nhanh)",
            "gemini-3.5-flash-lite": "3.5 Flash-Lite",
            "gemini-3.1-flash-lite-preview": "3.1 Flash Lite Preview",
            "gemini-3.8-flash": "3.8 Flash (Chất lượng cao)",
            "gemini-pro-latest": "Pro (Lý luận)"
        };
        return labels[modelId] || modelId;
    }

    initQuickModelSelector() {
        const wrapper = document.getElementById("modelSelectorWrapper");
        const btn = document.getElementById("modelSelectorBtn");
        const label = document.getElementById("modelBtnLabel");
        const popup = document.getElementById("modelPopupCard");
        const quickSelect = document.getElementById("quickModelSelect");

        this.updateQuickModelUI = (modelValue) => {
            const currentModel = modelValue || this.settings.model || "gemini-3-flash-preview";
            if (label) {
                label.textContent = this.getModelDisplayLabel(currentModel);
            }
            if (quickSelect) {
                quickSelect.value = currentModel;
            }
            if (popup) {
                popup.querySelectorAll(".model-popup-item").forEach(item => {
                    const isSelected = item.getAttribute("data-model") === currentModel;
                    item.classList.toggle("selected", isSelected);
                });
            }
        };

        // Initialize state
        this.updateQuickModelUI(this.settings.model);

        if (!wrapper || !btn || !popup) return;

        // Toggle popup open/close
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            const isOpen = popup.classList.contains("show");
            if (isOpen) {
                popup.classList.remove("show");
                wrapper.classList.remove("active");
                btn.setAttribute("aria-expanded", "false");
            } else {
                popup.classList.add("show");
                wrapper.classList.add("active");
                btn.setAttribute("aria-expanded", "true");
            }
        });

        // Click on item in popup
        popup.querySelectorAll(".model-popup-item").forEach(item => {
            item.addEventListener("click", (e) => {
                e.stopPropagation();
                const selectedModel = item.getAttribute("data-model");
                if (selectedModel) {
                    this.settings.model = selectedModel;
                    localStorage.setItem("ptit_chat_settings", JSON.stringify(this.settings));
                    this.updateQuickModelUI(selectedModel);
                    if (this.modelSelect) {
                        this.modelSelect.value = selectedModel;
                    }
                    if (this.modelBadgeDisplay) {
                        this.modelBadgeDisplay.textContent = selectedModel;
                    }
                    popup.classList.remove("show");
                    wrapper.classList.remove("active");
                    btn.setAttribute("aria-expanded", "false");
                    this.showToast(`Đã chuyển sang mô hình: ${selectedModel}`, "success");
                }
            });
        });

        // Close on click outside
        document.addEventListener("click", (e) => {
            if (!wrapper.contains(e.target)) {
                popup.classList.remove("show");
                wrapper.classList.remove("active");
                btn.setAttribute("aria-expanded", "false");
            }
        });

        // Close on Escape key
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && popup.classList.contains("show")) {
                popup.classList.remove("show");
                wrapper.classList.remove("active");
                btn.setAttribute("aria-expanded", "false");
            }
        });

        if (quickSelect) {
            quickSelect.addEventListener("change", (e) => {
                this.settings.model = e.target.value;
                localStorage.setItem("ptit_chat_settings", JSON.stringify(this.settings));
                this.updateQuickModelUI(this.settings.model);
            });
        }
    }

    autoGrowTextarea() {
        this.userInput.style.height = "auto";
        const newHeight = Math.min(this.userInput.scrollHeight, 160);
        this.userInput.style.height = (newHeight > 38 ? newHeight : 38) + "px";
        if (newHeight > 46) {
            this.chatForm.classList.add("multiline");
        } else {
            this.chatForm.classList.remove("multiline");
        }
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
                    "gemini-3-flash-preview",
                    "gemini-3.5-flash",
                    "gemini-flash-lite-latest",
                    "gemini-3.5-flash-lite",
                    "gemini-3.1-flash-lite",
                    "gemini-3.8-flash",
                    "gemini-3.7-flash"
                ];
                // Tự động nâng cấp các model hay bị timeout trên Google server sang gemini-3-flash-preview
                const slowOrTimeoutModels = [
                    "gemini-3.5-flash-lite",
                    "gemini-3.1-flash-lite",
                    "gemini-2.5-flash",
                    "gemini-3.6-flash",
                    "gemini-3.1-flash-lite-preview"
                ];
                if (!this.settings.model || !validModels.includes(this.settings.model) || slowOrTimeoutModels.includes(this.settings.model)) {
                    this.settings.model = "gemini-3-flash-preview";
                    localStorage.setItem("ptit_chat_settings", JSON.stringify(this.settings));
                }
                if (!this.settings.topK || this.settings.topK < 6) {
                    this.settings.topK = 6;
                }
            } catch (e) {
                console.error("Lỗi đọc cài đặt:", e);
            }
        }
        if (this.updateQuickModelUI) {
            this.updateQuickModelUI(this.settings.model);
        }
    }

    openSettingsModal() {
        this.customApiKeyInput.value = this.settings.apiKey || "";
        this.modelSelect.value = this.settings.model || "gemini-3-flash-preview";
        this.topKInput.value = this.settings.topK || 6;
        this.topKValue.textContent = this.topKInput.value;
        this.autoVoiceToggle.checked = !!this.settings.autoVoice;
        this.populateVoiceSelect();
        if (this.voiceSelect && this.settings.voiceURI) {
            this.voiceSelect.value = this.settings.voiceURI;
        }
        this.settingsModal.classList.add("active");
    }

    saveSettings() {
        this.settings.apiKey = this.customApiKeyInput.value.trim();
        this.settings.model = this.modelSelect.value;
        this.settings.topK = parseInt(this.topKInput.value, 10) || 6;
        this.settings.autoVoice = this.autoVoiceToggle.checked;
        this.settings.voiceURI = this.voiceSelect ? this.voiceSelect.value : "";

        localStorage.setItem("ptit_chat_settings", JSON.stringify(this.settings));
        if (this.modelBadgeDisplay) {
            this.modelBadgeDisplay.textContent = this.settings.model;
        }
        if (this.updateQuickModelUI) {
            this.updateQuickModelUI(this.settings.model);
        }
        this.settingsModal.classList.remove("active");
        this.showToast("Đã lưu cấu hình RAG thành công!", "success");
    }

    resetSettings() {
        this.settings = {
            apiKey: "",
            model: "gemini-3-flash-preview",
            topK: 6,
            autoVoice: false,
            voiceURI: ""
        };
        this.customApiKeyInput.value = "";
        this.modelSelect.value = "gemini-3-flash-preview";
        this.topKInput.value = 6;
        this.topKValue.textContent = "6";
        this.autoVoiceToggle.checked = false;
        if (this.voiceSelect) this.voiceSelect.value = "";
        localStorage.removeItem("ptit_chat_settings");
        this.modelBadgeDisplay.textContent = "gemini-3-flash-preview";
        if (this.updateQuickModelUI) {
            this.updateQuickModelUI("gemini-3-flash-preview");
        }
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
            if (msg.attachment) {
                const attachBadge = document.createElement("div");
                attachBadge.className = "msg-attachment-badge";
                attachBadge.innerHTML = `<i class="fa-solid fa-paperclip"></i> <span>${this.escapeHtml(msg.attachment.name)}</span> <small>(${msg.attachment.size || ""})</small>`;
                bubbleDiv.appendChild(attachBadge);
            }
            const textEl = document.createElement("div");
            textEl.className = "user-text-content";
            textEl.textContent = msg.content;
            bubbleDiv.appendChild(textEl);
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

    // ATTACHMENT MANAGEMENT
    setAttachedFile(file) {
        if (!file) return;
        const validExtensions = [".pdf", ".docx", ".txt", ".md"];
        const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
        if (!validExtensions.includes(ext)) {
            this.showToast("Chỉ hỗ trợ định dạng tệp: .pdf, .docx, .txt, .md", "warning");
            if (this.fileUploadInput) this.fileUploadInput.value = "";
            return;
        }

        if (file.size > 35 * 1024 * 1024) {
            this.showToast("Kích thước file không được vượt quá 35MB", "warning");
            if (this.fileUploadInput) this.fileUploadInput.value = "";
            return;
        }

        this.attachedFile = file;
        if (this.attachmentFilename) this.attachmentFilename.textContent = file.name;
        if (this.attachmentFilesize) {
            this.attachmentFilesize.textContent = `${this.formatFileSize(file.size)} • Tự động lưu data/ & chunking`;
        }

        if (this.attachmentIcon) {
            if (ext === ".pdf") this.attachmentIcon.className = "fa-solid fa-file-pdf attachment-icon";
            else if (ext === ".docx") this.attachmentIcon.className = "fa-solid fa-file-word attachment-icon";
            else this.attachmentIcon.className = "fa-solid fa-file-lines attachment-icon";
        }

        if (this.attachmentPreview) {
            this.attachmentPreview.classList.remove("hidden");
        }

        if (this.userInput) {
            this.userInput.placeholder = "Nhập câu hỏi về tài liệu đính kèm hoặc bấm Gửi để tóm tắt...";
            this.userInput.focus();
        }
    }

    clearAttachedFile() {
        this.attachedFile = null;
        if (this.fileUploadInput) this.fileUploadInput.value = "";
        if (this.attachmentPreview) this.attachmentPreview.classList.add("hidden");
        if (this.userInput) {
            this.userInput.placeholder = "Nhập câu hỏi về học phí, môn học, quy chế PTIT...";
        }
    }

    formatFileSize(bytes) {
        if (!bytes || bytes === 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    }

    // SUBMIT QUESTION
    async handleSubmit() {
        const text = this.userInput.value.trim();
        const fileToSend = this.attachedFile;
        if ((!text && !fileToSend) || this.isProcessing) return;

        // Reset Textarea
        this.userInput.value = "";
        this.userInput.style.height = "38px";
        if (this.chatForm) this.chatForm.classList.remove("multiline");

        const displayQuestion = text || (fileToSend ? `Tóm tắt nội dung tài liệu: ${fileToSend.name}` : "");
        const actualQuestion = text || (fileToSend ? `Hãy tóm tắt chi tiết các nội dung chính và thông tin quan trọng nhất trong tài liệu '${fileToSend.name}'.` : "");

        let currentSession = this.sessions.find(s => s.id === this.currentSessionId);
        if (!currentSession) {
            this.createNewSession();
            currentSession = this.sessions.find(s => s.id === this.currentSessionId) || this.sessions[0];
        }

        // Set title on first message
        if (currentSession.messages.length === 0) {
            const titleSource = fileToSend ? `Tài liệu: ${fileToSend.name}` : text;
            currentSession.title = titleSource.length > 32 ? titleSource.substring(0, 32) + "..." : titleSource;
            this.currentChatTitle.textContent = currentSession.title;
        }

        // Add User Message
        const userMsg = {
            role: "user",
            content: displayQuestion,
            attachment: fileToSend ? {
                name: fileToSend.name,
                size: this.formatFileSize(fileToSend.size)
            } : null,
            timestamp: new Date().toISOString()
        };
        currentSession.messages.push(userMsg);
        this.saveSessions();
        this.appendMessageToDOM(userMsg, true);

        // Clear attachment UI now that message is queued
        this.clearAttachedFile();

        // Show Typing Indicator
        this.isProcessing = true;
        this.sendBtn.disabled = true;
        this.typingIndicator.classList.remove("hidden");
        if (fileToSend) {
            this.typingLabel.textContent = "Đang lưu tài liệu vào thư mục data, xử lý & băm nhỏ dữ liệu (chunking)...";
        } else {
            this.typingLabel.textContent = "Đang tra cứu Vector DB & tạo câu trả lời...";
        }
        this.scrollToBottom();

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), fileToSend ? 120000 : 45000);

        try {
            let response;
            if (fileToSend) {
                const formData = new FormData();
                formData.append("file", fileToSend);
                formData.append("question", actualQuestion);
                formData.append("api_key", this.settings.apiKey || "");
                formData.append("model", this.settings.model || "");
                formData.append("top_k", this.settings.topK || 3);
                formData.append("history", JSON.stringify(currentSession.messages.slice(-6)));

                response = await fetch("/api/chat", {
                    method: "POST",
                    body: formData,
                    signal: controller.signal
                });
            } else {
                const payload = {
                    question: actualQuestion,
                    api_key: this.settings.apiKey,
                    model: this.settings.model,
                    top_k: this.settings.topK,
                    history: currentSession.messages.slice(-6)
                };

                response = await fetch("/api/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                    signal: controller.signal
                });
            }
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
                file_info: data.file_info || null,
                timestamp: new Date().toISOString()
            };

            currentSession.messages.push(botMsg);
            this.saveSessions();
            this.appendMessageToDOM(botMsg, true);

            // Update KB stats in sidebar if file was uploaded
            if (fileToSend) {
                this.fetchKBStatus();
                this.showToast(`Đã lưu "${fileToSend.name}" vào data/ và hoàn tất băm chunks!`, "success");
            }

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
                errorText = `⏱️ **Hết thời gian chờ (Timeout):** Quá trình xử lý tài liệu hoặc sinh câu trả lời quá lâu. Bạn hãy thử lại hoặc nhập Gemini API Key cá nhân trong phần Cài đặt (⚙️) nhé.`;
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

    // SPEECH SYNTHESIS (TTS) - TỐI ƯU GIỌNG ĐỌC TIẾNG VIỆT TỰ NHIÊN
    initSpeechSynthesis() {
        this.cachedVoices = [];
        this.speechQueue = [];
        this.currentSpeechBtn = null;

        if ('speechSynthesis' in window) {
            this.cachedVoices = window.speechSynthesis.getVoices();
            window.speechSynthesis.onvoiceschanged = () => {
                this.cachedVoices = window.speechSynthesis.getVoices();
                this.populateVoiceSelect();
            };
        }
    }

    populateVoiceSelect() {
        if (!this.voiceSelect || !('speechSynthesis' in window)) return;
        let voices = window.speechSynthesis.getVoices();
        if (!voices || voices.length === 0) {
            voices = this.cachedVoices || [];
        }
        if (!voices || voices.length === 0) return;

        const currentVal = this.voiceSelect.value || this.settings.voiceURI || "";
        this.voiceSelect.innerHTML = '<option value="">-- Tự động chọn giọng tiếng Việt tốt nhất --</option>';

        const viVoices = [];
        const otherVoices = [];
        voices.forEach(v => {
            const l = (v.lang || "").toLowerCase();
            const n = (v.name || "").toLowerCase();
            if (l.includes("vi") || n.includes("vietnam") || n.includes("tiếng việt")) {
                viVoices.push(v);
            } else {
                otherVoices.push(v);
            }
        });

        viVoices.sort((a, b) => {
            const aN = (a.name || "").toLowerCase();
            const bN = (b.name || "").toLowerCase();
            const aPref = (aN.includes("natural") || aN.includes("google") || aN.includes("hoaimy") || aN.includes("namminh")) ? 1 : 0;
            const bPref = (bN.includes("natural") || bN.includes("google") || bN.includes("hoaimy") || bN.includes("namminh")) ? 1 : 0;
            return bPref - aPref;
        });

        if (viVoices.length > 0) {
            const viGroup = document.createElement("optgroup");
            viGroup.label = "🇻🇳 Giọng Đọc Tiếng Việt (Khuyên dùng)";
            viVoices.forEach(v => {
                const opt = document.createElement("option");
                opt.value = v.voiceURI || v.name;
                let badge = "";
                if (v.name.includes("Google")) badge = " [Google Chrome]";
                else if (v.name.includes("Natural") || v.name.includes("Online")) badge = " [Microsoft Natural]";
                opt.textContent = `${v.name}${badge}`;
                viGroup.appendChild(opt);
            });
            this.voiceSelect.appendChild(viGroup);
        }

        if (otherVoices.length > 0) {
            const otherGroup = document.createElement("optgroup");
            otherGroup.label = "🌐 Các giọng đọc khác trong máy";
            otherVoices.slice(0, 15).forEach(v => {
                const opt = document.createElement("option");
                opt.value = v.voiceURI || v.name;
                opt.textContent = `${v.name} (${v.lang})`;
                otherGroup.appendChild(opt);
            });
            this.voiceSelect.appendChild(otherGroup);
        }

        if (currentVal) {
            this.voiceSelect.value = currentVal;
        }
    }

    getBestVietnameseVoice(forcedVoiceURI = null) {
        if (!('speechSynthesis' in window)) return null;
        let voices = window.speechSynthesis.getVoices();
        if (!voices || voices.length === 0) {
            voices = this.cachedVoices || [];
        }
        if (!voices || voices.length === 0) return null;

        const targetURI = forcedVoiceURI || this.settings.voiceURI;
        if (targetURI) {
            const matched = voices.find(v => (v.voiceURI === targetURI || v.name === targetURI));
            if (matched) return matched;
        }

        // 1. Ưu tiên giọng cao cấp Natural / Neural của Microsoft Edge (rất tự nhiên, như người thật đọc)
        let best = voices.find(v => {
            const l = (v.lang || "").toLowerCase();
            const n = (v.name || "").toLowerCase();
            return (l.includes("vi") || n.includes("vietnam")) && 
                   (n.includes("natural") || n.includes("online") || n.includes("hoaimy") || n.includes("namminh"));
        });

        // 2. Ưu tiên giọng Google tiếng Việt trên Chrome / Android
        if (!best) {
            best = voices.find(v => {
                const l = (v.lang || "").toLowerCase();
                const n = (v.name || "").toLowerCase();
                return (l.includes("vi") || n.includes("vietnam")) && n.includes("google");
            });
        }

        // 3. Ưu tiên bất kỳ giọng tiếng Việt chuẩn vi-VN nào khác
        if (!best) {
            best = voices.find(v => {
                const l = (v.lang || "").toLowerCase().replace("_", "-");
                const n = (v.name || "").toLowerCase();
                return l.startsWith("vi") || n.includes("vietnamese") || n.includes("tiếng việt") || n.includes("an - vietnamese");
            });
        }

        return best;
    }

    cleanTextForVietnameseTTS(rawText) {
        if (!rawText) return "";

        let t = rawText;

        // 1. Chuyển đổi các bảng Markdown thành câu văn tự nhiên
        t = t.replace(/\|[\s-:]+\|[\s-:]+\|/g, ""); // Dòng kẻ bảng |---|---|
        t = t.replace(/\|\s*/g, ", "); // Dấu cột | thành dấu phẩy nghỉ nhịp

        // 2. Chuyển đổi từ viết tắt học thuật và chuyên ngành sang từ ngữ nói tự nhiên
        const acronyms = [
            [/\bThS\./gi, "Thạc sĩ "],
            [/\bPGS\.TS\./gi, "Phó giáo sư Tiến sĩ "],
            [/\bPGS\./gi, "Phó giáo sư "],
            [/\bTS\./gi, "Tiến sĩ "],
            [/\bGV\s*:\s*/gi, "Giảng viên: "],
            [/\bGV\b/gi, "Giảng viên"],
            [/\bMSc\b/gi, "Thạc sĩ"],
            [/\bCNPM\b/gi, "Công nghệ phần mềm"],
            [/\bCNTT1\b/gi, "Công nghệ thông tin một"],
            [/\bCNTT\b/gi, "Công nghệ thông tin"],
            [/\bATTT\b/gi, "An toàn thông tin"],
            [/\bKTX\b/gi, "Ký túc xá"],
            [/\bQLDAPM\b/gi, "Quản lý dự án phần mềm"],
            [/\bQLDA\b/gi, "Quản lý dự án"],
            [/\bPTIT\b/gi, "Học viện Bưu chính Viễn thông"],
            [/\bSlink\b/gi, "Ét link"],
            [/\bVNĐ\b/gi, "đồng"],
            [/\bđ\/tín chỉ\b/gi, "đồng trên một tín chỉ"],
            [/\bđ\/TC\b/gi, "đồng trên một tín chỉ"],
            [/\bMSV\b/gi, "Mã sinh viên"],
            [/\bSV\b/gi, "Sinh viên"],
            [/\bHK(\d)\b/gi, "Học kỳ $1"],
            [/\b(\d+)\s*đ\b/gi, "$1 đồng"],
            [/>=/g, " lớn hơn hoặc bằng "],
            [/<=/g, " nhỏ hơn hoặc bằng "],
            [/!=/g, " khác "],
            [/==/g, " bằng "]
        ];

        for (const [pattern, replacement] of acronyms) {
            t = t.replace(pattern, replacement);
        }

        // 3. Xử lý đường dẫn web và email
        t = t.replace(/https?:\/\/\S+/gi, "");
        t = t.replace(/[\w.-]+@ptit\.edu\.vn/gi, "địa chỉ email trường");
        t = t.replace(/[\w.-]+@[\w.-]+\.\w+/gi, "địa chỉ email");

        // 4. Bỏ các ký tự định dạng Markdown
        t = t.replace(/`{1,3}[^`]*`{1,3}/g, ""); // Khối code
        t = t.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1"); // Link markdown: [Tên](url) -> Tên
        t = t.replace(/[#*_~`>]/g, " "); // Ký tự định dạng in đậm, nghiêng, tiêu đề
        t = t.replace(/^[\s•\-\*]+\s*/gm, ""); // Ký hiệu gạch đầu dòng bullet
        t = t.replace(/---/g, " ");

        // 5. Chuẩn hóa khoảng trắng và dấu câu
        t = t.replace(/([,.:;?!])\1+/g, "$1");
        t = t.replace(/\s+/g, " ").trim();

        return t;
    }

    toggleSpeech(text, btnElement) {
        if (!('speechSynthesis' in window)) {
            this.showToast("Trình duyệt không hỗ trợ đọc giọng nói Text-to-Speech.", "info");
            return;
        }

        if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
            window.speechSynthesis.cancel();
            this.speechQueue = [];
            document.querySelectorAll(".msg-action-btn.active").forEach(b => {
                b.classList.remove("active");
                const label = b.querySelector("span");
                if (label) label.textContent = "Đọc";
            });

            if (this.currentUtteranceText === text) {
                this.currentUtteranceText = null;
                return;
            }
        }

        this.speakText(text, btnElement);
    }

    speakText(text, btnElement = null, forcedVoiceURI = null) {
        if (!('speechSynthesis' in window)) return;
        window.speechSynthesis.cancel();
        this.speechQueue = [];

        const cleanText = this.cleanTextForVietnameseTTS(text);
        if (!cleanText) return;

        const viVoice = this.getBestVietnameseVoice(forcedVoiceURI);
        if (!viVoice) {
            this.showToast("Mẹo: Để nghe giọng đọc tiếng Việt mượt mà và tự nhiên nhất, bạn hãy mở trên Microsoft Edge (giọng Hoài My) hoặc Google Chrome nhé!", "info");
        }

        // Chia văn bản thành các câu ngắn (< 150 ký tự) theo dấu chấm, chấm phẩy hoặc xuống dòng
        // Tránh tình trạng Chrome SpeechSynthesis bị dừng giữa chừng sau 15 giây
        const rawSentences = cleanText.split(/(?<=[.!?;:\n])\s+/);
        const sentences = [];
        for (const s of rawSentences) {
            const trimmed = s.trim();
            if (trimmed) {
                if (trimmed.length > 180) {
                    const subParts = trimmed.split(/,\s+/);
                    for (const sp of subParts) {
                        if (sp.trim()) sentences.push(sp.trim());
                    }
                } else {
                    sentences.push(trimmed);
                }
            }
        }

        if (sentences.length === 0) return;

        this.currentSpeechBtn = btnElement;
        this.currentUtteranceText = text;

        if (btnElement) {
            btnElement.classList.add("active");
            const label = btnElement.querySelector("span");
            if (label) label.textContent = "Dừng";
        }

        const resetBtn = () => {
            if (this.currentSpeechBtn) {
                this.currentSpeechBtn.classList.remove("active");
                const label = this.currentSpeechBtn.querySelector("span");
                if (label) label.textContent = "Đọc";
            }
            this.currentUtteranceText = null;
            this.speechQueue = [];
        };

        let sentenceIndex = 0;
        const speakNext = () => {
            if (sentenceIndex >= sentences.length) {
                resetBtn();
                return;
            }

            const currentSentence = sentences[sentenceIndex++];
            const utterance = new SpeechSynthesisUtterance(currentSentence);
            utterance.lang = viVoice ? (viVoice.lang || "vi-VN") : "vi-VN";
            utterance.rate = 0.96; // Tốc độ tự nhiên, rõ chữ
            utterance.pitch = 1.0;

            if (viVoice) {
                utterance.voice = viVoice;
            }

            utterance.onend = () => {
                speakNext();
            };

            utterance.onerror = (e) => {
                if (e.error !== "canceled" && e.error !== "interrupted") {
                    console.warn("Lỗi phát âm SpeechSynthesis:", e);
                }
                resetBtn();
            };

            window.speechSynthesis.speak(utterance);
        };

        speakNext();
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
