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
            model: "gemini-3.5-flash-lite",
            topK: 4,
            autoVoice: false,
            showLatency: false,
            voice: "female",
            voiceSpeed: 1.35,
            voiceMode: "auto"
        };
        this.lastBenchmark = null;
        this.currentBotAudio = null;
        this.currentBotSpeakBtn = null;
        this.currentCategory = "all";
        this.isProcessing = false;
        this.currentScope = "ptit_only";
        this.uploadedFiles = [];
        this.currentUtterance = null;
        this.recognition = null;

        this.init();
    }

    init() {
        this.bindElements();
        this.setupMarkdown();
        this.loadSettings();
        this.loadSessions();
        this.initSidebar();
        this.bindEvents();
        this.autoGrowTextarea();
        this.initSpeechSynthesisVoices();
        this.initSpeechRecognition();
        this.fetchKBStatus();
        this.renderCategorySuggestions();
        this.initScopeSelector();
        this.initFileUpload();

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
        this.appLayout = document.getElementById("appLayout") || document.querySelector(".app-layout");
        this.sidebar = document.getElementById("sidebar");
        this.sidebarBackdrop = document.getElementById("sidebarBackdrop");
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
        this.inputTopBar = document.getElementById("inputTopBar");
        this.chatForm = document.getElementById("chatForm");
        this.userInput = document.getElementById("userInput");
        this.sendBtn = document.getElementById("sendBtn");
        this.voiceInputBtn = document.getElementById("voiceInputBtn");
        this.exportChatBtn = document.getElementById("exportChatBtn");
        this.clearCurrentChatBtn = document.getElementById("clearCurrentChatBtn");

        // Gemini-style 3-dots Chat Options Menu & Rename Modal
        this.chatMenuDropdownWrapper = document.getElementById("chatMenuDropdownWrapper");
        this.chatMenuBtn = document.getElementById("chatMenuBtn");
        this.chatDropdownMenu = document.getElementById("chatDropdownMenu");
        this.menuPinBtn = document.getElementById("menuPinBtn");
        this.menuPinIcon = document.getElementById("menuPinIcon");
        this.menuPinText = document.getElementById("menuPinText");
        this.menuRenameBtn = document.getElementById("menuRenameBtn");
        this.menuDeleteChatBtn = document.getElementById("menuDeleteChatBtn");
        this.renameChatModal = document.getElementById("renameChatModal");
        this.renameChatInput = document.getElementById("renameChatInput");
        this.saveRenameBtn = document.getElementById("saveRenameBtn");
        this.cancelRenameBtn = document.getElementById("cancelRenameBtn");
        this.closeRenameModalBtn = document.getElementById("closeRenameModalBtn");

        // Document Upload & Scope Switcher
        this.fileUploadInput = document.getElementById("fileUploadInput");
        this.uploadFileBtn = document.getElementById("uploadFileBtn");
        this.uploadedFilesBar = document.getElementById("uploadedFilesBar");
        this.uploadedFilesList = document.getElementById("uploadedFilesList");
        this.uploadStatusIndicator = document.getElementById("uploadStatusIndicator");
        this.uploadStatusText = document.getElementById("uploadStatusText");
        this.scopeSelectorWrapper = document.getElementById("scopeSelectorWrapper");
        this.scopeSelectorBtn = document.getElementById("scopeSelectorBtn");
        this.scopeBtnLabel = document.getElementById("scopeBtnLabel");
        this.scopePopupCard = document.getElementById("scopePopupCard");
        this.scopeDocsCountBadge = document.getElementById("scopeDocsCountBadge");
        this.openUploadedDocsModalBtn = document.getElementById("openUploadedDocsModalBtn");
        this.openDocsModalFromBarBtn = document.getElementById("openDocsModalFromBarBtn");
        this.navDocsCountText = document.getElementById("navDocsCountText");

        // Uploaded Docs Side Panel
        this.docsSidePanel = document.getElementById("docsSidePanel");
        this.docsSidePanelBackdrop = document.getElementById("docsSidePanelBackdrop");
        this.closeDocsSidePanelBtn = document.getElementById("closeDocsSidePanelBtn");
        this.closeDocsSidePanelFooterBtn = document.getElementById("closeDocsSidePanelFooterBtn");
        this.sidePanelDocsList = document.getElementById("sidePanelDocsList");
        this.sidePanelDocsCountBadge = document.getElementById("sidePanelDocsCountBadge");
        this.sidePanelUploadBtn = document.getElementById("sidePanelUploadBtn");
        this.sidePanelClearAllBtn = document.getElementById("sidePanelClearAllBtn");

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
        this.showLatencyToggle = document.getElementById("showLatencyToggle");
        this.statTtftDisplay = document.getElementById("statTtftDisplay");
        this.statTotalDisplay = document.getElementById("statTotalDisplay");
        this.statModelDisplay = document.getElementById("statModelDisplay");
        this.voiceModeSelect = document.getElementById("voiceModeSelect");
        this.voiceSelect = document.getElementById("voiceSelect");
        this.voiceSpeedSelect = document.getElementById("voiceSpeedSelect");
        this.voiceSpeedRange = document.getElementById("voiceSpeedRange");
        this.voiceSpeedValue = document.getElementById("voiceSpeedValue");
        this.testVoiceSpeedBtn = document.getElementById("testVoiceSpeedBtn");
        this.testVoiceSpeedBtnText = document.getElementById("testVoiceSpeedBtnText");
        this.currentVoiceNameDisplay = document.getElementById("currentVoiceNameDisplay");

        this.sourceModal = document.getElementById("sourceModal");
        this.sourceModalIcon = document.getElementById("sourceModalIcon");
        this.sourceModalTitle = document.getElementById("sourceModalTitle");
        this.sourceModalSubtitle = document.getElementById("sourceModalSubtitle");
        this.sourceModalContent = document.getElementById("sourceModalContent");
        this.sourcePageNav = document.getElementById("sourcePageNav");
        this.sourcePrevPageBtn = document.getElementById("sourcePrevPageBtn");
        this.sourceNextPageBtn = document.getElementById("sourceNextPageBtn");
        this.sourcePageIndicator = document.getElementById("sourcePageIndicator");
        this.sourceViewTabs = document.getElementById("sourceViewTabs");
        this.sourceTabPdfBtn = document.getElementById("sourceTabPdfBtn");
        this.sourceTabImageBtn = document.getElementById("sourceTabImageBtn");
        this.sourceTabTextBtn = document.getElementById("sourceTabTextBtn");
        this.sourcePdfPane = document.getElementById("sourcePdfPane");
        this.sourceImagePane = document.getElementById("sourceImagePane");
        this.sourceTextPane = document.getElementById("sourceTextPane");
        this.sourcePdfFrame = document.getElementById("sourcePdfFrame");
        this.sourcePageImage = document.getElementById("sourcePageImage");
        this.openSourceNewTabBtn = document.getElementById("openSourceNewTabBtn");
        this.openSourceNewTabText = document.getElementById("openSourceNewTabText");
        this.toggleSourceModalFullscreenBtn = document.getElementById("toggleSourceModalFullscreenBtn");
        this.closeSourceModalBtn = document.getElementById("closeSourceModalBtn");
        this.closeSourceModalFooterBtn = document.getElementById("closeSourceModalFooterBtn");
        this.copySourceContentBtn = document.getElementById("copySourceContentBtn");
        this.currentSourceViewer = {
            file: "",
            title: "",
            page: 1,
            totalPages: 1,
            isPdf: true,
            activeTab: "pdf"
        };

        this.toastContainer = document.getElementById("toastContainer");
    }

    bindEvents() {
        // Theme Toggle
        this.themeToggleBtn.addEventListener("click", () => this.toggleTheme());

        // Sidebar Toggle (Window Icon)
        if (this.openSidebarBtn) this.openSidebarBtn.addEventListener("click", () => this.openSidebar());
        if (this.closeSidebarBtn) this.closeSidebarBtn.addEventListener("click", () => this.closeSidebar());
        if (this.sidebarBackdrop) this.sidebarBackdrop.addEventListener("click", () => this.closeSidebar());

        // Global hotkey Ctrl+B / Cmd+B to toggle sidebar
        window.addEventListener("keydown", (e) => {
            if ((e.ctrlKey || e.metaKey) && (e.key === "b" || e.key === "B")) {
                if (document.activeElement === this.userInput && this.userInput.selectionStart !== this.userInput.selectionEnd) {
                    return;
                }
                e.preventDefault();
                this.toggleSidebar();
            }
        });

        // Sessions
        if (this.newChatBtn) this.newChatBtn.addEventListener("click", () => this.createNewSession());
        if (this.clearAllHistoryBtn) this.clearAllHistoryBtn.addEventListener("click", () => this.clearAllHistory());
        if (this.clearCurrentChatBtn) this.clearCurrentChatBtn.addEventListener("click", () => this.clearCurrentChat());

        // Chat 3-dots Options Menu (Gemini Style)
        if (this.chatMenuBtn) {
            this.chatMenuBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                this.toggleChatMenu();
            });
        }
        if (this.menuPinBtn) {
            this.menuPinBtn.addEventListener("click", () => this.togglePinCurrentChat());
        }
        if (this.menuRenameBtn) {
            this.menuRenameBtn.addEventListener("click", () => this.openRenameModal());
        }
        if (this.exportChatBtn) {
            this.exportChatBtn.addEventListener("click", () => {
                this.closeChatMenu();
                this.exportCurrentChat();
            });
        }
        if (this.menuDeleteChatBtn) {
            this.menuDeleteChatBtn.addEventListener("click", () => this.deleteCurrentChatFromMenu());
        }

        // Close dropdown on outside click or Escape
        document.addEventListener("click", (e) => {
            if (this.chatDropdownMenu && this.chatDropdownMenu.classList.contains("show")) {
                if (this.chatMenuDropdownWrapper && !this.chatMenuDropdownWrapper.contains(e.target)) {
                    this.closeChatMenu();
                }
            }
        });

        // Rename Chat Modal Events
        if (this.saveRenameBtn) {
            this.saveRenameBtn.addEventListener("click", () => this.saveRenameChat());
        }
        if (this.cancelRenameBtn) {
            this.cancelRenameBtn.addEventListener("click", () => this.closeRenameModal());
        }
        if (this.closeRenameModalBtn) {
            this.closeRenameModalBtn.addEventListener("click", () => this.closeRenameModal());
        }
        if (this.renameChatInput) {
            this.renameChatInput.addEventListener("keydown", (e) => {
                if (e.key === "Enter") {
                    e.preventDefault();
                    this.saveRenameChat();
                } else if (e.key === "Escape") {
                    this.closeRenameModal();
                }
            });
        }
        if (this.renameChatModal) {
            this.renameChatModal.addEventListener("click", (e) => {
                if (e.target === this.renameChatModal) this.closeRenameModal();
            });
        }

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
        if (this.voiceModeSelect) {
            this.voiceModeSelect.addEventListener("change", () => {
                this.updateVoiceStatusUI(this.voiceSelect ? this.voiceSelect.value : this.settings.voice);
            });
        }
        if (this.voiceSelect) {
            this.voiceSelect.addEventListener("change", () => {
                this.updateVoiceStatusUI(this.voiceSelect.value);
            });
        }

        // Chức năng chỉnh tốc độ đọc trong cài đặt
        if (this.voiceSpeedRange) {
            this.voiceSpeedRange.addEventListener("input", () => {
                const val = parseFloat(this.voiceSpeedRange.value) || 1.35;
                if (this.voiceSpeedValue) this.voiceSpeedValue.textContent = val.toFixed(2) + "x";
                if (this.voiceSpeedSelect) this.voiceSpeedSelect.value = String(val);
                this.updateSpeedPresetUI(val);
            });
        }

        document.querySelectorAll(".speed-preset-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                const spd = parseFloat(btn.getAttribute("data-speed")) || 1.35;
                if (this.voiceSpeedRange) this.voiceSpeedRange.value = spd;
                if (this.voiceSpeedValue) this.voiceSpeedValue.textContent = spd.toFixed(2) + "x";
                if (this.voiceSpeedSelect) this.voiceSpeedSelect.value = String(spd);
                this.updateSpeedPresetUI(spd);
            });
        });

        if (this.testVoiceSpeedBtn) {
            this.testVoiceSpeedBtn.addEventListener("click", () => {
                const spd = parseFloat(this.voiceSpeedRange ? this.voiceSpeedRange.value : this.settings.voiceSpeed) || 1.35;
                const sampleText = "Xin chào bạn, đây là thử nghiệm tốc độ đọc của trợ lý ảo Bưu chính Viễn thông.";

                const btn = this.testVoiceSpeedBtn;
                const textSpan = this.testVoiceSpeedBtnText || btn.querySelector("span");
                const icon = btn.querySelector("i");

                if (btn.classList.contains("speaking")) {
                    this.stopCurrentSpeech();
                    btn.classList.remove("speaking");
                    if (textSpan) textSpan.textContent = "Nghe thử tốc độ";
                    if (icon) icon.className = "fa-solid fa-volume-high";
                    return;
                }

                btn.classList.add("speaking");
                if (textSpan) textSpan.textContent = "Đang đọc...";
                if (icon) icon.className = "fa-solid fa-stop";

                const onDone = () => {
                    btn.classList.remove("speaking");
                    if (textSpan) textSpan.textContent = "Nghe thử tốc độ";
                    if (icon) icon.className = "fa-solid fa-volume-high";
                };

                const voiceInfo = this.getActiveVoiceInfo();
                if (voiceInfo.mode === "native" && voiceInfo.voiceObj && window.speechSynthesis) {
                    window.speechSynthesis.cancel();
                    const u = new SpeechSynthesisUtterance(sampleText);
                    u.voice = voiceInfo.voiceObj;
                    u.lang = voiceInfo.voiceObj.lang || "vi-VN";
                    u.rate = spd;
                    u.onend = onDone;
                    u.onerror = onDone;
                    window.speechSynthesis.speak(u);
                } else {
                    fetch("/api/tts", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            text: sampleText,
                            voice: voiceInfo.backendVoice || "vi-VN-HoaiMyNeural",
                            speed: spd
                        })
                    })
                    .then(res => res.json())
                    .then(data => {
                        if (data && data.audio_url) {
                            const aud = new Audio(data.audio_url);
                            aud.defaultPlaybackRate = spd;
                            aud.playbackRate = spd;
                            aud.onloadedmetadata = () => { try { aud.playbackRate = spd; } catch (e) { } };
                            aud.oncanplay = () => { try { aud.playbackRate = spd; } catch (e) { } };
                            aud.onended = onDone;
                            aud.onerror = onDone;
                            aud.play().catch(onDone);
                        } else {
                            onDone();
                        }
                    })
                    .catch(onDone);
                }
            });
        }

        if (this.closeSourceModalBtn) this.closeSourceModalBtn.addEventListener("click", () => this.closeSourceModal());
        if (this.closeSourceModalFooterBtn) this.closeSourceModalFooterBtn.addEventListener("click", () => this.closeSourceModal());
        if (this.toggleSourceModalFullscreenBtn) {
            this.toggleSourceModalFullscreenBtn.addEventListener("click", () => this.toggleSourceModalFullscreen());
        }
        if (this.sourcePrevPageBtn) {
            this.sourcePrevPageBtn.addEventListener("click", () => {
                if (this.currentSourceViewer && this.currentSourceViewer.page > 1) {
                    this.loadCitationPage(this.currentSourceViewer.page - 1);
                }
            });
        }
        if (this.sourceNextPageBtn) {
            this.sourceNextPageBtn.addEventListener("click", () => {
                if (this.currentSourceViewer && this.currentSourceViewer.page < this.currentSourceViewer.totalPages) {
                    this.loadCitationPage(this.currentSourceViewer.page + 1);
                }
            });
        }
        [this.sourceTabPdfBtn, this.sourceTabImageBtn, this.sourceTabTextBtn].filter(Boolean).forEach(btn => {
            btn.addEventListener("click", () => {
                const tab = btn.getAttribute("data-tab") || "pdf";
                this.switchSourceModalTab(tab);
            });
        });
        if (this.copySourceContentBtn) {
            this.copySourceContentBtn.addEventListener("click", () => {
                navigator.clipboard.writeText(this.sourceModalContent ? this.sourceModalContent.textContent : "").then(() => {
                    this.showToast("Đã sao chép nội dung trang!", "success");
                });
            });
        }

        // Voice Input
        if (this.voiceInputBtn) this.voiceInputBtn.addEventListener("click", () => this.toggleVoiceInput());

        // Uploaded Docs Side Panel Events
        if (this.openUploadedDocsModalBtn) this.openUploadedDocsModalBtn.addEventListener("click", () => this.openSidePanel());
        if (this.openDocsModalFromBarBtn) this.openDocsModalFromBarBtn.addEventListener("click", () => this.openSidePanel());
        if (this.closeDocsSidePanelBtn) this.closeDocsSidePanelBtn.addEventListener("click", () => this.closeSidePanel());
        if (this.closeDocsSidePanelFooterBtn) this.closeDocsSidePanelFooterBtn.addEventListener("click", () => this.closeSidePanel());
        if (this.docsSidePanelBackdrop) this.docsSidePanelBackdrop.addEventListener("click", () => this.closeSidePanel());
        if (this.sidePanelUploadBtn) this.sidePanelUploadBtn.addEventListener("click", () => this.fileUploadInput && this.fileUploadInput.click());
        if (this.sidePanelClearAllBtn) this.sidePanelClearAllBtn.addEventListener("click", () => this.clearAllSessionDocs());

        // Close modals on backdrop click
        [this.kbModal, this.settingsModal, this.sourceModal].filter(Boolean).forEach(modal => {
            modal.addEventListener("click", (e) => {
                if (e.target === modal) {
                    if (modal === this.sourceModal) {
                        this.closeSourceModal();
                    } else {
                        modal.classList.remove("active");
                    }
                }
            });
        });
        this.initQuickModelSelector();
    }

    getModelDisplayLabel(modelId) {
        const labels = {
            "gemini-3.5-flash-lite": "3.5 Flash-Lite (Mặc định)",
            "gemini-3.6-flash": "3.6 Flash (Cân bằng & Nhanh)",
            "gemini-3.8-flash": "3.8 Flash (Tư duy sâu)"
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
            const currentModel = modelValue || this.settings.model || "gemini-3.5-flash-lite";
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
                    this.showToast(`Đã chuyển sang mô hình: ${this.getModelDisplayLabel(selectedModel)}`, "success");
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

        if (this.modelSelect) {
            this.modelSelect.addEventListener("change", (e) => {
                this.updateQuickModelUI(e.target.value);
            });
        }
    }

    autoGrowTextarea() {
        this.userInput.style.height = "auto";
        const newHeight = Math.min(this.userInput.scrollHeight, 160);
        this.userInput.style.height = (newHeight > 30 ? newHeight : 30) + "px";
        if (newHeight > 38) {
            this.chatForm.classList.add("multiline");
        } else {
            this.chatForm.classList.remove("multiline");
        }
    }

    initSidebar() {
        if (!this.sidebar) return;

        // Restore desktop collapsed state from localStorage
        if (window.innerWidth > 768) {
            try {
                const isCollapsed = localStorage.getItem("ptit_sidebar_collapsed") === "true";
                if (isCollapsed) {
                    this.sidebar.classList.add("collapsed");
                    if (this.appLayout) this.appLayout.classList.add("sidebar-collapsed");
                }
            } catch (e) {
                console.warn("Could not read sidebar preference:", e);
            }
        }

        // Handle responsive resize smoothly
        window.addEventListener("resize", () => {
            if (window.innerWidth <= 768) {
                this.sidebar.classList.remove("collapsed");
                if (this.appLayout) this.appLayout.classList.remove("sidebar-collapsed");
            } else {
                this.sidebar.classList.remove("open");
                if (this.sidebarBackdrop) this.sidebarBackdrop.classList.remove("active");
                const isCollapsed = localStorage.getItem("ptit_sidebar_collapsed") === "true";
                if (isCollapsed) {
                    this.sidebar.classList.add("collapsed");
                    if (this.appLayout) this.appLayout.classList.add("sidebar-collapsed");
                }
            }
        });
    }

    toggleSidebar() {
        if (window.innerWidth <= 768) {
            if (!this.sidebar) return;
            const isOpen = this.sidebar.classList.toggle("open");
            if (this.sidebarBackdrop) {
                this.sidebarBackdrop.classList.toggle("active", isOpen);
            }
        } else {
            if (!this.sidebar) return;
            const isCollapsed = this.sidebar.classList.toggle("collapsed");
            if (this.appLayout) {
                this.appLayout.classList.toggle("sidebar-collapsed", isCollapsed);
            }
            try {
                localStorage.setItem("ptit_sidebar_collapsed", isCollapsed ? "true" : "false");
            } catch (e) { }
        }
    }

    openSidebar() {
        if (!this.sidebar) return;
        if (window.innerWidth <= 768) {
            this.sidebar.classList.add("open");
            if (this.sidebarBackdrop) this.sidebarBackdrop.classList.add("active");
        } else {
            this.sidebar.classList.remove("collapsed");
            if (this.appLayout) this.appLayout.classList.remove("sidebar-collapsed");
            try {
                localStorage.setItem("ptit_sidebar_collapsed", "false");
            } catch (e) { }
        }
    }

    closeSidebar() {
        if (!this.sidebar) return;
        if (window.innerWidth <= 768) {
            this.sidebar.classList.remove("open");
            if (this.sidebarBackdrop) this.sidebarBackdrop.classList.remove("active");
        } else {
            this.sidebar.classList.add("collapsed");
            if (this.appLayout) this.appLayout.classList.add("sidebar-collapsed");
            try {
                localStorage.setItem("ptit_sidebar_collapsed", "true");
            } catch (e) { }
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
                // Nâng cấp tốc độ đọc mặc định lên 1.35x nếu cài đặt cũ đang để 1.0 hoặc 1.25
                if (!this.settings.voiceSpeed || this.settings.voiceSpeed === 1.0 || this.settings.voiceSpeed === 1.25) {
                    this.settings.voiceSpeed = 1.35;
                }
                if (!this.settings.voiceMode) {
                    this.settings.voiceMode = "auto";
                }
                const validModels = [
                    "gemini-3.5-flash-lite",
                    "gemini-3.6-flash",
                    "gemini-3.8-flash"
                ];
                if (!this.settings.model || !validModels.includes(this.settings.model)) {
                    this.settings.model = "gemini-3.5-flash-lite";
                    localStorage.setItem("ptit_chat_settings", JSON.stringify(this.settings));
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
        if ("speechSynthesis" in window && typeof window.speechSynthesis.getVoices === "function") {
            try { window.speechSynthesis.getVoices(); } catch (e) { }
        }
        this.customApiKeyInput.value = this.settings.apiKey || "";
        this.modelSelect.value = this.settings.model || "gemini-3.5-flash-lite";
        this.topKInput.value = this.settings.topK || 4;
        this.topKValue.textContent = this.topKInput.value;
        this.autoVoiceToggle.checked = !!this.settings.autoVoice;
        if (this.showLatencyToggle) this.showLatencyToggle.checked = !!this.settings.showLatency;
        if (this.voiceModeSelect) this.voiceModeSelect.value = this.settings.voiceMode || "auto";
        if (this.voiceSelect) this.voiceSelect.value = /namminh|male/i.test(this.settings.voice || "") && !/^female$/i.test(this.settings.voice) ? "male" : "female";
        const curSpeed = parseFloat(this.settings.voiceSpeed || 1.35);
        if (this.voiceSpeedRange) this.voiceSpeedRange.value = curSpeed;
        if (this.voiceSpeedValue) this.voiceSpeedValue.textContent = curSpeed.toFixed(2) + "x";
        if (this.voiceSpeedSelect) this.voiceSpeedSelect.value = String(curSpeed);
        this.updateSpeedPresetUI(curSpeed);
        this.updateVoiceStatusUI(this.voiceSelect ? this.voiceSelect.value : this.settings.voice);
        this.updateBenchmarkSettingsDisplay();
        this.settingsModal.classList.add("active");
    }

    updateSpeedPresetUI(currentSpeed) {
        document.querySelectorAll(".speed-preset-btn").forEach(btn => {
            const btnSpeed = parseFloat(btn.getAttribute("data-speed"));
            if (Math.abs(btnSpeed - currentSpeed) < 0.04) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });
    }

    updateBenchmarkSettingsDisplay() {
        if (!this.statTtftDisplay || !this.statTotalDisplay || !this.statModelDisplay) return;
        if (!this.lastBenchmark) {
            this.statTtftDisplay.textContent = "Chưa có lượt đo nào";
            this.statTotalDisplay.textContent = "Chưa có lượt đo nào";
            this.statModelDisplay.textContent = "—";
            return;
        }
        const b = this.lastBenchmark;
        const ttftText = b.ttftMs ? `${(b.ttftMs / 1000).toFixed(2)}s (${b.ttftMs}ms)` : (b.isCached ? "0.01s (Trúng cache LRU)" : "—");
        const totalText = b.totalMs ? `${(b.totalMs / 1000).toFixed(2)}s (${b.totalMs}ms)` : "—";
        this.statTtftDisplay.textContent = ttftText;
        this.statTotalDisplay.textContent = totalText;
        this.statModelDisplay.textContent = b.modelUsed || "—";
    }

    saveSettings() {
        this.settings.apiKey = this.customApiKeyInput.value.trim();
        this.settings.model = this.modelSelect.value;
        this.settings.topK = parseInt(this.topKInput.value, 10) || 4;
        this.settings.autoVoice = this.autoVoiceToggle.checked;
        if (this.showLatencyToggle) this.settings.showLatency = this.showLatencyToggle.checked;
        if (this.voiceModeSelect) this.settings.voiceMode = this.voiceModeSelect.value;
        if (this.voiceSelect) this.settings.voice = this.voiceSelect.value;
        if (this.voiceSpeedRange) {
            this.settings.voiceSpeed = parseFloat(this.voiceSpeedRange.value) || 1.35;
        } else if (this.voiceSpeedSelect) {
            this.settings.voiceSpeed = parseFloat(this.voiceSpeedSelect.value) || 1.35;
        }

        localStorage.setItem("ptit_chat_settings", JSON.stringify(this.settings));
        if (this.modelBadgeDisplay) {
            this.modelBadgeDisplay.textContent = this.settings.model;
        }
        if (this.updateQuickModelUI) {
            this.updateQuickModelUI(this.settings.model);
        }
        this.updateVoiceStatusUI(this.settings.voice);
        this.toggleLatencyBadgesInDOM();
        this.settingsModal.classList.remove("active");
        this.showToast("Đã lưu cài đặt!", "success");
    }

    toggleLatencyBadgesInDOM() {
        const isShow = !!this.settings.showLatency;
        document.querySelectorAll(".msg-latency-badge").forEach(badge => {
            badge.style.display = isShow ? "inline-flex" : "none";
        });
    }

    resetSettings() {
        this.settings = {
            apiKey: "",
            model: "gemini-3.5-flash-lite",
            topK: 4,
            autoVoice: false,
            showLatency: false,
            voice: "female",
            voiceSpeed: 1.35,
            voiceMode: "auto"
        };
        this.lastBenchmark = null;
        this.customApiKeyInput.value = "";
        this.modelSelect.value = "gemini-3.5-flash-lite";
        this.topKInput.value = 4;
        this.topKValue.textContent = "4";
        this.autoVoiceToggle.checked = false;
        if (this.showLatencyToggle) this.showLatencyToggle.checked = false;
        if (this.voiceModeSelect) this.voiceModeSelect.value = "auto";
        if (this.voiceSelect) this.voiceSelect.value = "female";
        if (this.voiceSpeedRange) this.voiceSpeedRange.value = 1.35;
        if (this.voiceSpeedValue) this.voiceSpeedValue.textContent = "1.35x";
        if (this.voiceSpeedSelect) this.voiceSpeedSelect.value = "1.35";
        this.updateSpeedPresetUI(1.35);
        localStorage.removeItem("ptit_chat_settings");
        if (this.modelBadgeDisplay) {
            this.modelBadgeDisplay.textContent = "gemini-3.5-flash-lite";
        }
        if (this.updateQuickModelUI) {
            this.updateQuickModelUI("gemini-3.5-flash-lite");
        }
        this.updateVoiceStatusUI("female");
        this.updateBenchmarkSettingsDisplay();
        this.toggleLatencyBadgesInDOM();
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
        this.uploadedFiles = [];
        this.pendingAttachedFiles = [];
        this.renderUploadedFiles([]);
        this.setScope("ptit_only");
        this.switchSession(newSession.id);
        this.updateMenuPinState();
        if (window.innerWidth <= 768) {
            this.closeSidebar();
        }
    }

    switchSession(sessionId) {
        this.stopCurrentSpeech();

        this.currentSessionId = sessionId;
        const session = this.sessions.find(s => s.id === sessionId);
        if (!session) return;

        this.uploadedFiles = [];
        this.pendingAttachedFiles = [];
        this.renderUploadedFiles([], false);
        if (this.currentChatTitle) this.currentChatTitle.textContent = session.title;
        this.renderMessages(session.messages);
        this.renderHistoryList();
        this.fetchSessionDocs(sessionId);
        this.updateMenuPinState();
        if (window.innerWidth <= 768) {
            this.closeSidebar();
        }
    }

    deleteSession(sessionId, event) {
        if (event) event.stopPropagation();
        fetch("/api/session-docs", {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId })
        }).catch(() => { });
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
            fetch("/api/session-docs", {
                method: "DELETE",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ session_id: this.currentSessionId })
            }).catch(() => { });
            this.uploadedFiles = [];
            this.renderUploadedFiles([]);
            this.setScope("ptit_only");
            session.messages = [];
            session.title = "Đoạn chat mới";
            if (this.currentChatTitle) this.currentChatTitle.textContent = session.title;
            this.saveSessions();
            this.renderMessages([]);
            this.showToast("Đã xóa nội dung đoạn chat và tài liệu tải lên.", "info");
        }
    }

    clearAllHistory() {
        if (confirm("Bạn có chắc chắn muốn xóa toàn bộ lịch sử trò chuyện?")) {
            this.sessions.forEach(s => {
                fetch("/api/session-docs", {
                    method: "DELETE",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ session_id: s.id })
                }).catch(() => { });
            });
            this.sessions = [];
            localStorage.removeItem("ptit_chat_sessions");
            this.createNewSession();
            this.showToast("Đã dọn sạch toàn bộ lịch sử.", "info");
        }
    }

    getSortedSessions() {
        return [...this.sessions].sort((a, b) => {
            const aPinned = a.pinned ? 1 : 0;
            const bPinned = b.pinned ? 1 : 0;
            if (aPinned !== bPinned) {
                return bPinned - aPinned; // pinned first
            }
            if (a.pinned && b.pinned) {
                return (b.pinnedAt || 0) - (a.pinnedAt || 0);
            }
            return 0;
        });
    }

    renderHistoryList() {
        if (!this.chatHistoryList) return;
        this.chatHistoryList.innerHTML = "";
        if (this.sessions.length === 0) {
            this.chatHistoryList.innerHTML = `<div style="padding: 12px; color: var(--text-muted); font-size: 0.8rem; text-align: center;">Chưa có lịch sử</div>`;
            return;
        }

        const sorted = this.getSortedSessions();
        sorted.forEach(sess => {
            const item = document.createElement("div");
            item.className = `history-item ${sess.id === this.currentSessionId ? "active" : ""} ${sess.pinned ? "is-pinned" : ""}`;
            item.innerHTML = `
                <i class="${sess.pinned ? 'fa-solid fa-thumbtack pin-badge' : 'fa-regular fa-message'}" style="font-size: 0.82rem"></i>
                <span class="history-item-title" title="${this.escapeHtml(sess.title)}">${this.escapeHtml(sess.title)}</span>
                <button class="history-delete-btn" title="Xóa đoạn chat"><i class="fa-solid fa-trash-can"></i></button>
            `;
            item.addEventListener("click", () => this.switchSession(sess.id));
            item.querySelector(".history-delete-btn").addEventListener("click", (e) => this.deleteSession(sess.id, e));
            this.chatHistoryList.appendChild(item);
        });
    }

    // GEMINI-STYLE 3-DOTS MENU & ACTIONS
    toggleChatMenu() {
        if (!this.chatDropdownMenu) return;
        const isOpen = this.chatDropdownMenu.classList.toggle("show");
        if (this.chatMenuBtn) {
            this.chatMenuBtn.classList.toggle("active", isOpen);
            this.chatMenuBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
        }
        if (isOpen) {
            this.updateMenuPinState();
        }
    }

    closeChatMenu() {
        if (!this.chatDropdownMenu) return;
        this.chatDropdownMenu.classList.remove("show");
        if (this.chatMenuBtn) {
            this.chatMenuBtn.classList.remove("active");
            this.chatMenuBtn.setAttribute("aria-expanded", "false");
        }
    }

    updateMenuPinState() {
        const session = this.sessions.find(s => s.id === this.currentSessionId);
        const isPinned = session && !!session.pinned;
        if (this.menuPinIcon) {
            this.menuPinIcon.className = isPinned ? "fa-solid fa-thumbtack-slash" : "fa-solid fa-thumbtack";
        }
        if (this.menuPinText) {
            this.menuPinText.textContent = isPinned ? "Bỏ ghim" : "Ghim";
        }
    }

    togglePinCurrentChat() {
        this.closeChatMenu();
        const session = this.sessions.find(s => s.id === this.currentSessionId);
        if (!session) return;

        session.pinned = !session.pinned;
        if (session.pinned) {
            session.pinnedAt = Date.now();
        } else {
            delete session.pinnedAt;
        }

        this.saveSessions();
        this.updateMenuPinState();
        this.renderHistoryList();

        if (session.pinned) {
            this.showToast("Đã ghim cuộc trò chuyện lên đầu danh sách.", "success");
        } else {
            this.showToast("Đã bỏ ghim cuộc trò chuyện.", "info");
        }
    }

    openRenameModal() {
        this.closeChatMenu();
        const session = this.sessions.find(s => s.id === this.currentSessionId);
        if (!session) return;

        if (this.renameChatInput) {
            this.renameChatInput.value = session.title || "";
        }
        if (this.renameChatModal) {
            this.renameChatModal.classList.add("active");
            setTimeout(() => {
                if (this.renameChatInput) {
                    this.renameChatInput.focus();
                    this.renameChatInput.select();
                }
            }, 80);
        }
    }

    closeRenameModal() {
        if (this.renameChatModal) {
            this.renameChatModal.classList.remove("active");
        }
    }

    saveRenameChat() {
        const session = this.sessions.find(s => s.id === this.currentSessionId);
        if (!session || !this.renameChatInput) return;

        const newTitle = this.renameChatInput.value.trim();
        if (!newTitle) {
            this.showToast("Tên cuộc trò chuyện không được để trống.", "warning");
            return;
        }

        session.title = newTitle;
        session.isCustomTitle = true;
        this.saveSessions();
        if (this.currentChatTitle) this.currentChatTitle.textContent = newTitle;
        this.renderHistoryList();
        this.closeRenameModal();
        this.showToast("Đã đổi tên cuộc trò chuyện thành công.", "success");
    }

    deleteCurrentChatFromMenu() {
        this.closeChatMenu();
        const session = this.sessions.find(s => s.id === this.currentSessionId);
        if (!session) return;

        const hasMessages = session.messages && session.messages.length > 0;
        if (!hasMessages || confirm("Bạn có chắc chắn muốn xóa cuộc trò chuyện này?")) {
            this.deleteSession(this.currentSessionId);
        }
    }

    renderMessages(messages) {
        if (!this.messageThread || !this.welcomeHero) return;
        this.messageThread.innerHTML = "";
        if (!messages || messages.length === 0) {
            this.welcomeHero.style.display = "flex";
            if (this.inputTopBar) this.inputTopBar.style.display = "block";
            return;
        }

        this.welcomeHero.style.display = "none";
        if (this.inputTopBar) this.inputTopBar.style.display = "none";
        messages.forEach(msg => {
            this.appendMessageToDOM(msg, false);
        });
        this.scrollToBottom();
    }

    normalizeVoiceTranscript(text) {
        if (!text) return "";
        return text
            .replace(/\b(?:gba|g\.p\.a|g\s+p\s+a|ji\s*pi\s*ay)\b/gi, "GPA")
            .replace(/\b(?:pê\s*tít|pê\s*tit|pờ\s*tít)\b/gi, "PTIT")
            .trim();
    }

    isRefusalBotAnswer(rawText) {
        if (!rawText) return false;
        const splitIdx = rawText.search(/(?:\n+---\s*)?\n*(?:📌\s*)?\*{0,2}Nguồn(?:\s+tài\s+liệu)?(?:\s+trích\s+dẫn|\s+tham\s+khảo)?/i);
        const body = (splitIdx >= 0 ? rawText.slice(0, splitIdx) : rawText).trim();
        const refusalRx = /(?:chưa|không)\s+(?:có|chứa|tìm\s+thấy|được\s+cung\s+cấp|đề\s+cập)(?:\s+đầy\s+đủ|\s+đủ|\s+chi\s+tiết|\s+cụ\s+thể)*\s*(?:thông\s+tin|dữ\s+liệu)|tài\s+liệu.*?(?:chưa|không)\s+(?:có|đủ|chứa|đề\s+cập).*?(?:để\s+trả\s+lời|thông\s+tin|dữ\s+liệu)/i;
        if (!refusalRx.test(body)) return false;
        const hasTable = /^\|.+\|$/m.test(body);
        const hasBullets = /^\s*[-*•+]\s+.+/m.test(body);
        return !hasTable && !hasBullets;
    }

    renderBotMarkdownIntoBubble(bubbleDiv, rawContent, isFinal = true) {
        if (!bubbleDiv) return;
        let textToRender = rawContent || "";
        // Nếu câu trả lời là thông báo từ chối / chưa có thông tin, loại bỏ ngay mọi khối trích dẫn thừa
        if (this.isRefusalBotAnswer(textToRender)) {
            textToRender = textToRender.replace(/(?:\n+\s*---\s*)?\n*(?:📌\s*)?\*{0,2}Nguồn(?:\s+tài\s+liệu)?(?:\s+trích\s+dẫn|\s+tham\s+khảo)?[\s\S]*$/i, "").trim();
        }
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

            if (isFinal) {
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
                        headers[0].style.textAlign = "center";
                        let sttCounter = 1;
                        table.querySelectorAll("tbody tr").forEach(row => {
                            const cells = Array.from(row.querySelectorAll("td"));
                            if (cells.length > 0) {
                                cells[0].textContent = sttCounter++;
                                cells[0].classList.add("col-stt");
                                cells[0].style.textAlign = "center";
                                cells[0].style.fontWeight = "600";
                            }
                        });
                    }
                }
            }

            // Căn chỉnh thông minh theo nội dung ô: chỉ nowrap cho số tiền, mã môn, khóa học, số tín chỉ; văn bản dài tự động xuống dòng
            table.querySelectorAll("td").forEach(td => {
                const txt = td.textContent.trim();
                // Ô số tiền / đơn giá học phí
                if (/^\d{1,3}(\.\d{3})+(\s*đ|\s*đồng|\s*VNĐ)?$/i.test(txt) || /đồng\/tín chỉ|VNĐ\/tín chỉ/i.test(txt)) {
                    td.style.whiteSpace = "nowrap";
                    td.style.fontWeight = "700";
                    td.style.color = "var(--primary)";
                    td.style.textAlign = "center";
                } else if (/^Khóa\s*\d{4}/i.test(txt) || /^[A-Z]{2,5}\s*\d{3,5}$/i.test(txt)) {
                    // Ô Khóa tuyển sinh (Khóa 2024) hoặc Mã môn học (INT1332, BAS1150)
                    td.style.whiteSpace = "nowrap";
                    td.style.textAlign = "center";
                    td.style.fontWeight = "600";
                } else if (/^\d{1,2}(\.\d)?$/.test(txt) && !td.classList.contains("col-stt")) {
                    // Ô Số tín chỉ hoặc số ngắn (VD: 2, 3, 4)
                    td.style.whiteSpace = "nowrap";
                    td.style.textAlign = "center";
                } else if (txt.length > 45) {
                    // Ô mô tả / tóm tắt nội dung dài: luôn cho phép tự động xuống dòng nhiều hàng
                    td.style.whiteSpace = "normal";
                    td.style.textAlign = "left";
                    td.style.minWidth = "240px";
                }
            });
        });

        // Chuyển đổi mục "📌 Nguồn trích dẫn:" (Mẫu 1) thành các thẻ trích dẫn tương tác (bấm vào mở đúng file và đúng trang)
        this.decorateInlineCitations(bubbleDiv);
    }

    decorateInlineCitations(bubbleDiv) {
        if (!bubbleDiv) return;

        // Đánh dấu tiêu đề "📌 Nguồn trích dẫn:"
        bubbleDiv.querySelectorAll("p, h4, h5").forEach(el => {
            const txt = (el.textContent || "").trim();
            if (/^📌?\s*Nguồn(\s+trích\s+dẫn|\s+tham\s+khảo)?\s*:?$/i.test(txt) || txt.startsWith("📌 Nguồn")) {
                el.classList.add("citation-section-header");
                const prev = el.previousElementSibling;
                if (prev && prev.tagName === "HR") {
                    prev.classList.add("citation-section-divider");
                }
            } else if (/^🔍?\s*Nguồn(\s+từ)?\s*Internet\s*:?$/i.test(txt) || txt.startsWith("🔍 Nguồn từ Internet")) {
                el.classList.add("citation-section-header");
                const prev = el.previousElementSibling;
                if (prev && prev.tagName === "HR") {
                    prev.classList.add("citation-section-divider");
                }
            }
        });

        const citeRegex = /(?:📄\s*)?Trang\s*(\d+)\s*[-–—|]\s*File:\s*([^\s()<>]+)(?:\s*\(([^)]+)\))?/i;

        // Chuyển các dòng danh sách `<li>` chứa Mẫu 1 thành nút bấm mở trực tiếp tài liệu tại trang tương ứng
        bubbleDiv.querySelectorAll("li").forEach(li => {
            if (li.querySelector(".inline-citation-chip") || li.querySelector(".inline-web-citation-chip")) return;
            const rawText = (li.textContent || "").trim();
            const match = rawText.match(citeRegex);
            if (match) {
                const page = parseInt(match[1], 10) || 1;
                const file = (match[2] || "").trim().replace(/[,.;:]+$/, "");
                const title = (match[3] || "").trim();

                const parentList = li.parentElement;
                if (parentList && (parentList.tagName === "UL" || parentList.tagName === "OL")) {
                    parentList.classList.add("citation-list-inline");
                }
                li.classList.add("citation-list-item");

                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "inline-citation-chip";
                btn.setAttribute("data-file", file);
                btn.setAttribute("data-page", String(page));
                btn.setAttribute("data-title", title);
                btn.title = `Bấm để mở tài liệu ${file} ngay tại Trang ${page}`;

                const safeFile = this.escapeHtml(file);
                const safeTitle = title ? this.escapeHtml(title) : "";

                btn.innerHTML = `
                    <span class="cite-chip-icon"><i class="fa-solid fa-file-pdf"></i></span>
                    <span class="cite-chip-body">
                        <span class="cite-chip-main">📄 Trang <strong>${page}</strong> - File: <strong>${safeFile}</strong></span>
                        ${safeTitle ? `<span class="cite-chip-title">(${safeTitle})</span>` : ""}
                    </span>
                    <span class="cite-chip-action"><i class="fa-solid fa-arrow-up-right-from-square"></i> Xem trang ${page}</span>
                `;

                btn.addEventListener("click", (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.openSourceModal({
                        file: file,
                        page: page,
                        title: title
                    });
                });

                li.innerHTML = "";
                li.appendChild(btn);
                return;
            }

            // Chuyển các dòng danh sách `<li>` chứa link nguồn web thành chip liên kết
            const link = li.querySelector("a");
            if (link && (rawText.includes("🌐") || rawText.toLowerCase().includes("http"))) {
                const url = link.getAttribute("href") || "";
                const title = link.textContent.trim().replace(/^🌐\s*/, "") || url;
                if (!url) return;

                const parentList = li.parentElement;
                if (parentList && (parentList.tagName === "UL" || parentList.tagName === "OL")) {
                    parentList.classList.add("citation-list-inline");
                }
                li.classList.add("citation-list-item");

                const a = document.createElement("a");
                a.href = url;
                a.target = "_blank";
                a.rel = "noopener noreferrer";
                a.className = "inline-web-citation-chip";
                a.title = `Mở liên kết web: ${url}`;

                const hasHighlight = url.includes(":~:text=") || url.includes("#search=");
                const safeTitle = this.escapeHtml(title);
                let domain = "";
                try {
                    domain = new URL(url).hostname;
                } catch (e) {
                    domain = url;
                }
                const safeDomain = this.escapeHtml(domain);

                a.title = hasHighlight
                    ? `Mở trang web và tự động cuộn đến bôi sáng nội dung: ${url}`
                    : `Mở liên kết web: ${url}`;

                a.innerHTML = `
                    <span class="cite-chip-icon"><i class="${hasHighlight ? "fa-solid fa-highlighter" : "fa-solid fa-globe"}"></i></span>
                    <span class="cite-chip-body">
                        <span class="cite-chip-main">${safeTitle}</span>
                        <span class="cite-chip-title">${safeDomain}</span>
                    </span>
                    <span class="cite-chip-action"><i class="fa-solid ${hasHighlight ? "fa-highlighter" : "fa-arrow-up-right-from-square"}"></i> ${hasHighlight ? "Xem đoạn khớp" : "Mở nguồn"}</span>
                `;

                li.innerHTML = "";
                li.appendChild(a);
            }
        });
    }

    updateBotReferencedBadge(wrapperDiv, referencedFiles) {
        if (!wrapperDiv) return;
        let existingBadge = wrapperDiv.querySelector(".bot-msg-ref-badge");
        if (referencedFiles && referencedFiles.length > 0) {
            if (!existingBadge) {
                existingBadge = document.createElement("div");
                existingBadge.className = "bot-msg-ref-badge";
                wrapperDiv.insertBefore(existingBadge, wrapperDiv.firstChild);
            }
            existingBadge.innerHTML = `<i class="fa-solid fa-file-circle-check"></i> <span>Dựa trên tài liệu: <strong>${referencedFiles.map(f => this.escapeHtml(f)).join(", ")}</strong></span>`;
        } else if (existingBadge) {
            existingBadge.remove();
        }
    }

    updateBotWebBadge(wrapperDiv, isWebSearched) {
        if (!wrapperDiv) return;
        let existingBadge = wrapperDiv.querySelector(".bot-msg-web-badge");
        if (isWebSearched) {
            if (!existingBadge) {
                existingBadge = document.createElement("div");
                existingBadge.className = "bot-msg-web-badge";
                wrapperDiv.insertBefore(existingBadge, wrapperDiv.firstChild);
            }
            existingBadge.innerHTML = `<i class="fa-solid fa-globe"></i> <span>Thông tin được tổng hợp từ <strong>Internet</strong> (ngoài tài liệu PTIT)</span>`;
        } else if (existingBadge) {
            existingBadge.remove();
        }
    }

    appendMessageToDOM(msg, shouldScroll = true) {
        this.welcomeHero.style.display = "none";
        if (this.inputTopBar) this.inputTopBar.style.display = "none";

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
            if (msg.audioUrl || msg.isVoiceMessage) {
                const voicePlayer = this.createMessengerVoicePlayer(msg);
                bubbleDiv.appendChild(voicePlayer);

                if (msg.content) {
                    const transcriptDiv = document.createElement("div");
                    transcriptDiv.className = "voice-bubble-transcript";
                    transcriptDiv.innerHTML = `<i class="fa-solid fa-quote-left"></i> <span>${this.escapeHtml(msg.content)}</span>`;
                    bubbleDiv.appendChild(transcriptDiv);
                }
            } else {
                bubbleDiv.textContent = msg.content;
            }
            if (msg.attachedFiles && msg.attachedFiles.length > 0) {
                const attachBox = document.createElement("div");
                attachBox.className = "msg-attached-files";
                attachBox.innerHTML = `<span class="msg-attach-label"><i class="fa-solid fa-paperclip"></i> Đã đính kèm:</span>` +
                    msg.attachedFiles.map(fn => {
                        const ext = fn.split(".").pop().toLowerCase();
                        let iconClass = "fa-file-lines";
                        if (ext === "pdf") iconClass = "fa-file-pdf";
                        else if (ext === "docx") iconClass = "fa-file-word";
                        return `<span class="msg-file-chip"><i class="fa-solid ${iconClass}"></i> ${this.escapeHtml(fn)}</span>`;
                    }).join("");
                bubbleDiv.appendChild(attachBox);
            }
        } else {
            this.updateBotReferencedBadge(wrapperDiv, msg.referenced_files);
            this.updateBotWebBadge(wrapperDiv, msg.web_searched);
            this.renderBotMarkdownIntoBubble(bubbleDiv, msg.content || "", true);
        }

        wrapperDiv.appendChild(bubbleDiv);

        // Action Buttons for Bot Message (Copy, TTS, Benchmark latency)
        let speakBtnRef = null;
        let latencyBadgeRef = null;
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
            speakBtn.className = "msg-action-btn msg-speak-btn";
            speakBtn.innerHTML = '<i class="fa-solid fa-volume-high"></i> <span>Đọc</span>';
            speakBtn.addEventListener("click", () => this.toggleSpeech(msg.content, speakBtn));
            speakBtnRef = speakBtn;

            // Nút / Huy hiệu hiển thị Latency (Mặc định ẩn, bật/tắt trong Cài đặt hoặc click chuyển đổi)
            const latencyBadge = document.createElement("span");
            latencyBadge.className = "msg-latency-badge";
            latencyBadge.style.display = this.settings.showLatency ? "inline-flex" : "none";
            latencyBadge.style.alignItems = "center";
            latencyBadge.style.gap = "4px";
            latencyBadge.style.fontSize = "0.74rem";
            latencyBadge.style.color = "var(--text-muted, #94a3b8)";
            latencyBadge.style.padding = "2px 8px";
            latencyBadge.style.borderRadius = "12px";
            latencyBadge.style.background = "var(--bg-secondary, rgba(255,255,255,0.05))";
            latencyBadge.style.border = "1px solid var(--border-color, rgba(255,255,255,0.08))";
            latencyBadge.style.cursor = "default";

            if (msg.benchmark) {
                const b = msg.benchmark;
                const ttft = b.ttftMs ? `${(b.ttftMs / 1000).toFixed(2)}s` : "0.01s";
                const total = b.totalMs ? `${(b.totalMs / 1000).toFixed(2)}s` : "—";
                latencyBadge.innerHTML = `<i class="fa-solid fa-bolt" style="color: #eab308;"></i> <span>TTFT: <strong>${ttft}</strong> | Tổng: <strong>${total}</strong></span>`;
                latencyBadge.title = `Thời gian có chữ đầu tiên: ${ttft} | Tổng thời gian hoàn thành: ${total} | Model: ${msg.model_used || ''}`;
            } else {
                latencyBadge.innerHTML = `<i class="fa-solid fa-bolt" style="color: #eab308;"></i> <span>Đo tốc độ...</span>`;
            }
            latencyBadgeRef = latencyBadge;

            actionsDiv.appendChild(copyBtn);
            actionsDiv.appendChild(speakBtn);
            actionsDiv.appendChild(latencyBadge);
            wrapperDiv.appendChild(actionsDiv);
        }

        msgDiv.appendChild(avatarDiv);
        msgDiv.appendChild(wrapperDiv);

        this.messageThread.appendChild(msgDiv);
        if (shouldScroll) this.scrollToBottom();
        return { msgDiv, wrapperDiv, bubbleDiv, speakBtn: speakBtnRef, latencyBadge: latencyBadgeRef };
    }

    scrollToBottom() {
        setTimeout(() => {
            this.chatMessagesArea.scrollTop = this.chatMessagesArea.scrollHeight;
        }, 50);
    }

    // SUBMIT QUESTION (TỐI ƯU STREAMING SSE + CACHE PHẢN HỒI TỨC THÌ)
    async handleSubmit(customVoiceData = null) {
        const text = (customVoiceData && customVoiceData.text) ? customVoiceData.text : this.userInput.value.trim();
        if (!text || this.isProcessing) return;

        // Dừng giọng nói bot đang đọc nếu có
        this.stopCurrentSpeech();
        this.isWebSearching = false;
        // Mở khóa sẵn phần tử Audio chính ngay trong thao tác gửi câu hỏi (user gesture)
        // để khi LLM trả lời xong sau > 5 giây, Chrome vẫn cho phép phát tự động
        this.unlockBotAudioPlayer();

        // Reset Textarea
        this.userInput.value = "";
        this.userInput.style.height = "38px";
        if (this.chatForm) this.chatForm.classList.remove("multiline");

        // Ẩn thanh tài liệu khỏi ô chat sau khi gửi câu hỏi (tài liệu vẫn lưu trong phiên)
        if (this.uploadedFilesBar) {
            this.uploadedFilesBar.style.display = "none";
        }

        let currentSession = this.sessions.find(s => s.id === this.currentSessionId);
        if (!currentSession) {
            this.createNewSession();
            currentSession = this.sessions.find(s => s.id === this.currentSessionId) || this.sessions[0];
        }

        // Set title on first message (unless user has manually renamed it)
        if (currentSession.messages.length === 0 && !currentSession.isCustomTitle) {
            currentSession.title = text.length > 32 ? text.substring(0, 32) + "..." : text;
            if (this.currentChatTitle) this.currentChatTitle.textContent = currentSession.title;
        }

        // Add User Message with attached files (chỉ gắn trên câu hỏi ngay sau lượt tải file)
        const attachedFiles = (this.pendingAttachedFiles && this.pendingAttachedFiles.length > 0)
            ? [...this.pendingAttachedFiles]
            : [];
        this.pendingAttachedFiles = [];
        const userMsg = {
            role: "user",
            content: text,
            attachedFiles: attachedFiles,
            audioUrl: customVoiceData ? customVoiceData.audioUrl : null,
            audioDuration: customVoiceData ? customVoiceData.audioDuration : 0,
            isVoiceMessage: !!(customVoiceData && customVoiceData.audioUrl),
            timestamp: new Date().toISOString()
        };
        currentSession.messages.push(userMsg);
        this.saveSessions();
        this.appendMessageToDOM(userMsg, true);

        // Show Typing Indicator
        this.isProcessing = true;
        this.sendBtn.disabled = true;
        this.typingIndicator.classList.remove("hidden");
        this.typingLabel.textContent = "Đang tra cứu & phản hồi...";
        this.scrollToBottom();

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 35000);
        const startTime = performance.now();
        let firstChunkTime = null;

        try {
            const payload = {
                question: text,
                session_id: this.currentSessionId,
                scope: this.currentScope,
                api_key: this.settings.apiKey,
                model: this.settings.model,
                top_k: this.settings.topK,
                history: currentSession.messages.slice(-6)
            };

            const response = await fetch("/api/chat/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
                signal: controller.signal
            });

            if (!response.ok || !response.body) {
                throw new Error(`HTTP ${response.status}`);
            }

            const botMsg = {
                role: "assistant",
                content: "",
                sources: [],
                model_used: this.settings.model,
                scope_used: this.currentScope,
                referenced_files: [],
                benchmark: null,
                timestamp: new Date().toISOString()
            };

            let domRefs = null;
            let lastRenderTime = 0;
            let liveVoiceSessionToken = null;

            const ensureBotBubbleCreated = () => {
                if (!domRefs) {
                    this.typingIndicator.classList.add("hidden");
                    domRefs = this.appendMessageToDOM(botMsg, true);
                }
            };

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                const parts = buffer.split("\n\n");
                buffer = parts.pop() || "";

                for (const block of parts) {
                    const line = block.trim();
                    if (!line.startsWith("data:")) continue;
                    const jsonStr = line.slice(5).trim();
                    if (!jsonStr) continue;

                    let ev = null;
                    try {
                        ev = JSON.parse(jsonStr);
                    } catch (e) {
                        continue;
                    }

                    if (ev.type === "meta") {
                        botMsg.scope_used = ev.scope_used || this.currentScope;
                        botMsg.referenced_files = ev.referenced_files || [];
                        if (ev.sources) botMsg.sources = ev.sources;
                    } else if (ev.type === "web_search_start") {
                        this.isWebSearching = true;
                        // Dừng ngay lập tức giọng đọc câu trả lời thiếu từ server
                        this.stopCurrentSpeech();
                        liveVoiceSessionToken = null;
                        botMsg.content = "";
                        firstChunkTime = null;
                        if (domRefs && domRefs.bubbleDiv) {
                            domRefs.bubbleDiv.innerHTML = `<div class="web-search-in-progress" style="display:flex;align-items:center;gap:10px;padding:8px 4px;color:var(--text-secondary);font-size:13.5px;font-style:italic;"><i class="fa-solid fa-compass fa-spin" style="color:var(--primary-color, #c81e1e);font-size:16px;"></i> <span>${this.escapeHtml(ev.message || "Tài liệu nội bộ chưa có thông tin. Đang tìm kiếm trên Internet...")}</span></div>`;
                        }
                        if (this.typingIndicator) {
                            this.typingIndicator.classList.remove("hidden");
                        }
                        if (this.typingLabel) {
                            this.typingLabel.textContent = ev.message || "🔍 Đang tìm kiếm thông tin trên Internet...";
                        }
                        this.scrollToBottom();
                    } else if (ev.type === "chunk" && ev.delta) {
                        const now = performance.now();
                        if (firstChunkTime === null) {
                            firstChunkTime = now;
                        }
                        ensureBotBubbleCreated();
                        botMsg.content += ev.delta;
                        if (now - lastRenderTime >= 35) {
                            this.renderBotMarkdownIntoBubble(domRefs.bubbleDiv, botMsg.content, false);
                            this.chatMessagesArea.scrollTop = this.chatMessagesArea.scrollHeight;
                            lastRenderTime = now;
                        }
                        // Đọc ngay câu đầu tiên khi đang stream câu trả lời (chỉ áp dụng khi KHÔNG đang tìm kiếm web)
                        if (this.settings.autoVoice && domRefs && domRefs.speakBtn && !this.isWebSearching) {
                            if (liveVoiceSessionToken === null || this.speechSessionToken === liveVoiceSessionToken) {
                                liveVoiceSessionToken = this.feedLiveSpeech(botMsg.content, false, domRefs.speakBtn, liveVoiceSessionToken);
                            }
                        }
                    } else if (ev.type === "done") {
                        const endTime = performance.now();
                        const ttftMs = Math.round((firstChunkTime || endTime) - startTime);
                        const totalMs = Math.round(endTime - startTime);
                        const benchmarkData = {
                            ttftMs: ev.cached ? 10 : ttftMs,
                            totalMs: ev.cached ? 15 : totalMs,
                            modelUsed: ev.model_used || this.settings.model,
                            isCached: !!ev.cached
                        };
                        botMsg.benchmark = benchmarkData;
                        this.lastBenchmark = benchmarkData;

                        ensureBotBubbleCreated();
                        if (ev.answer) botMsg.content = ev.answer;
                        if (ev.model_used) botMsg.model_used = ev.model_used;
                        if (ev.scope_used) botMsg.scope_used = ev.scope_used;
                        if (ev.referenced_files) botMsg.referenced_files = ev.referenced_files;
                        if (ev.sources) botMsg.sources = ev.sources;
                        if (ev.web_searched !== undefined) botMsg.web_searched = ev.web_searched;
                        if (ev.web_sources) botMsg.web_sources = ev.web_sources;
                        this.updateBotReferencedBadge(domRefs.wrapperDiv, botMsg.referenced_files);
                        this.updateBotWebBadge(domRefs.wrapperDiv, botMsg.web_searched);

                        // Cập nhật thẻ đo tốc độ trên tin nhắn
                        if (domRefs.latencyBadge) {
                            const ttftTxt = benchmarkData.isCached ? "0.01s (Cache)" : `${(benchmarkData.ttftMs / 1000).toFixed(2)}s`;
                            const totalTxt = benchmarkData.isCached ? "0.01s" : `${(benchmarkData.totalMs / 1000).toFixed(2)}s`;
                            domRefs.latencyBadge.innerHTML = `<i class="fa-solid fa-bolt" style="color: #eab308;"></i> <span>TTFT: <strong>${ttftTxt}</strong> | Tổng: <strong>${totalTxt}</strong></span>`;
                            domRefs.latencyBadge.title = `Thời gian có chữ đầu tiên: ${ttftTxt} | Tổng thời gian: ${totalTxt} | Mô hình: ${botMsg.model_used}`;
                            domRefs.latencyBadge.style.display = this.settings.showLatency ? "inline-flex" : "none";
                        }

                        this.renderBotMarkdownIntoBubble(domRefs.bubbleDiv, botMsg.content, true);
                        this.updateBenchmarkSettingsDisplay();
                        this.scrollToBottom();
                    }
                }
            }

            clearTimeout(timeoutId);
            this.typingIndicator.classList.add("hidden");
            this.isProcessing = false;
            this.sendBtn.disabled = false;

            if (!botMsg.content) {
                botMsg.content = "Không nhận được phản hồi từ hệ thống.";
                ensureBotBubbleCreated();
                this.renderBotMarkdownIntoBubble(domRefs.bubbleDiv, botMsg.content, true);
            }

            currentSession.messages.push(botMsg);
            this.saveSessions();

            // Auto-voice if enabled:
            if (this.settings.autoVoice && domRefs && domRefs.speakBtn) {
                if (this.isWebSearching || botMsg.web_searched) {
                    this.isWebSearching = false;
                    // Đã sinh xong toàn bộ câu trả lời từ Web Search -> Dừng triệt để giọng đọc cũ và phát câu trả lời mới hoàn chỉnh
                    this.stopCurrentSpeech();
                    this.speakText(botMsg.content, domRefs.speakBtn);
                } else if (liveVoiceSessionToken === null) {
                    this.speakText(botMsg.content, domRefs.speakBtn);
                } else if (this.speechSessionToken === liveVoiceSessionToken) {
                    this.feedLiveSpeech(botMsg.content, true, domRefs.speakBtn, liveVoiceSessionToken);
                }
            }
            this.isWebSearching = false;

        } catch (err) {
            clearTimeout(timeoutId);
            console.error("Stream/Fetch Error:", err);
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

    // SOURCE MODAL (XEM TÀI LIỆU & NHẢY ĐÚNG TRANG TRÍCH DẪN)
    async openSourceModal(src) {
        if (!src || !this.sourceModal) return;
        const file = (src.file || src.source || "").trim();
        const page = parseInt(src.page, 10) || 1;
        const title = (src.title || "").trim();
        const isPdf = file.toLowerCase().endsWith(".pdf");

        this.currentSourceViewer = {
            file: file,
            title: title,
            page: page,
            totalPages: Math.max(page, 1),
            isPdf: isPdf,
            activeTab: isPdf ? "pdf" : "text"
        };

        if (this.sourceModalTitle) {
            this.sourceModalTitle.textContent = `📄 Trang ${page} — File: ${file}`;
        }
        if (this.sourceModalSubtitle) {
            this.sourceModalSubtitle.textContent = title || "Đang tải tài liệu gốc...";
        }
        if (this.openSourceNewTabText) {
            this.openSourceNewTabText.textContent = isPdf
                ? `Mở file PDF ở tab mới (Trang ${page})`
                : `Mở tài liệu gốc (${file})`;
        }

        this.sourceModal.classList.add("active");
        await this.loadCitationPage(page);
    }

    async loadCitationPage(page) {
        if (!this.currentSourceViewer || !this.currentSourceViewer.file) return;
        const targetPage = Math.max(1, parseInt(page, 10) || 1);
        const file = this.currentSourceViewer.file;
        const sessionParam = encodeURIComponent(this.currentSessionId || "");

        try {
            const url = `/api/view-page-detail?file=${encodeURIComponent(file)}&page=${targetPage}&session_id=${sessionParam}`;
            const res = await fetch(url);
            const data = await res.json();

            if (!res.ok || data.error) {
                throw new Error(data.error || "Không tìm thấy dữ liệu trang.");
            }

            const resolvedPage = data.page || targetPage;
            const totalPages = data.total_pages || resolvedPage;
            const isPdf = !!data.is_pdf;

            this.currentSourceViewer.file = data.file || file;
            this.currentSourceViewer.title = data.title || this.currentSourceViewer.title || data.file;
            this.currentSourceViewer.page = resolvedPage;
            this.currentSourceViewer.totalPages = totalPages;
            this.currentSourceViewer.isPdf = isPdf;

            if (this.sourceModalTitle) {
                this.sourceModalTitle.textContent = `📄 Trang ${resolvedPage} - File: ${data.file}`;
            }
            if (this.sourceModalSubtitle) {
                const originBadge = data.is_user_doc ? "Tài liệu người dùng tải lên" : "Cơ sở tri thức PTIT chính thức";
                this.sourceModalSubtitle.textContent = `${data.title} • (${originBadge})`;
            }

            if (isPdf && data.file_url) {
                const sep = data.file_url.includes("?") ? "&" : "?";
                const pdfUrlWithPage = `${data.file_url}${sep}_p=${resolvedPage}#page=${resolvedPage}&view=FitH`;
                if (this.sourcePdfFrame) {
                    this.sourcePdfFrame.src = pdfUrlWithPage;
                }
                if (this.openSourceNewTabBtn) {
                    this.openSourceNewTabBtn.href = `${data.file_url}#page=${resolvedPage}`;
                    this.openSourceNewTabBtn.style.display = "inline-flex";
                }
                if (this.openSourceNewTabText) {
                    this.openSourceNewTabText.textContent = `Mở file PDF ở tab mới (Trang ${resolvedPage})`;
                }
                this.switchSourceModalTab("pdf");
            } else {
                if (this.sourcePdfFrame) {
                    this.sourcePdfFrame.src = "about:blank";
                }
                if (this.openSourceNewTabBtn) {
                    if (data.file_url) {
                        this.openSourceNewTabBtn.href = data.file_url;
                        this.openSourceNewTabBtn.style.display = "inline-flex";
                        if (this.openSourceNewTabText) {
                            this.openSourceNewTabText.textContent = `Mở tài liệu gốc (${data.file})`;
                        }
                    } else {
                        this.openSourceNewTabBtn.style.display = "none";
                    }
                }
                if (this.sourceModalContent) {
                    this.sourceModalContent.textContent = data.text_content || `Không có văn bản trích xuất cho Trang ${resolvedPage}.`;
                }
                this.switchSourceModalTab("text");
            }
        } catch (err) {
            console.error("Error loading citation page detail:", err);
            if (this.sourceModalContent) {
                this.sourceModalContent.textContent = `Không thể tải chi tiết Trang ${targetPage} của file ${file}: ${err.message || err}`;
            }
            this.switchSourceModalTab("text");
        }
    }

    switchSourceModalTab(tabName) {
        if (!this.currentSourceViewer) return;
        const validTab = (!this.currentSourceViewer.isPdf && tabName !== "text") ? "text" : (tabName || "pdf");
        this.currentSourceViewer.activeTab = validTab;

        if (this.sourcePdfPane) {
            this.sourcePdfPane.classList.toggle("active", validTab === "pdf");
        }
        if (this.sourceTextPane) {
            this.sourceTextPane.classList.toggle("active", validTab === "text");
        }
    }

    closeSourceModal() {
        if (this.sourceModal) {
            this.sourceModal.classList.remove("active");
        }
        if (this.sourcePdfFrame) {
            this.sourcePdfFrame.src = "about:blank";
        }
    }

    // KNOWLEDGE BASE MODAL & STATUS
    async fetchKBStatus() {
        try {
            const res = await fetch("/api/status");
            const data = await res.json();
            if (data.chunks_count !== undefined) {
                if (this.totalChunksDisplay) this.totalChunksDisplay.textContent = `${data.chunks_count} Chunks`;
                if (this.modalTotalChunks) this.modalTotalChunks.textContent = `${data.chunks_count} Chunks`;
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
                            <span><i class="fa-regular fa-file-pdf"></i> ${item.pdf_file || item.name}</span>
                            <span>Kích thước: <strong>${item.file_size}</strong></span>
                        </div>
                    `;
                    card.style.cursor = "pointer";
                    card.title = `Bấm để xem tài liệu ${item.pdf_file || item.name}`;
                    card.addEventListener("click", () => {
                        if (this.kbModal) this.kbModal.classList.remove("active");
                        this.openSourceModal({
                            file: item.pdf_file || item.name,
                            page: 1,
                            title: item.title
                        });
                    });
                    this.catalogGrid.appendChild(card);
                });
            }
        } catch (e) {
            console.error("Error loading sources catalog:", e);
        }
    }

    // =========================================================================
    // SPEECH SYNTHESIS (TTS) - GIỌNG BẢN ĐỊA TRÌNH DUYỆT, DỰ PHÒNG QUA BACKEND
    // =========================================================================
    initSpeechSynthesisVoices() {
        if ("speechSynthesis" in window) {
            try {
                window.speechSynthesis.getVoices();
                window.speechSynthesis.onvoiceschanged = () => {
                    this.updateVoiceStatusUI();
                };
            } catch (e) {
                console.warn("SpeechSynthesis init warning:", e);
            }
        }
        setTimeout(() => this.updateVoiceStatusUI(), 350);
        setTimeout(() => this.updateVoiceStatusUI(), 1000);

        // Khởi tạo 1 phần tử Audio duy nhất để giữ quyền phát tự động (user activation) xuyên suốt phiên chat
        if (!this.botAudioPlayer) {
            this.botAudioPlayer = new Audio();
            this.botAudioPlayer.preload = "auto";
        }

        // Mở khóa autoplay ở lần tương tác đầu tiên
        const unlockAudio = () => {
            this.unlockBotAudioPlayer();
            document.removeEventListener("pointerdown", unlockAudio, true);
            document.removeEventListener("keydown", unlockAudio, true);
        };
        document.addEventListener("pointerdown", unlockAudio, true);
        document.addEventListener("keydown", unlockAudio, true);
    }

    unlockBotAudioPlayer() {
        if (this.isPlayingSentenceQueue) return;
        try {
            if (!this.botAudioPlayer) {
                this.botAudioPlayer = new Audio();
                this.botAudioPlayer.preload = "auto";
            }
            const player = this.botAudioPlayer;
            player.muted = true;
            player.volume = 0;
            player.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";
            const p = player.play();
            if (p && typeof p.then === "function") {
                p.then(() => {
                    if (!this.isPlayingSentenceQueue) {
                        try {
                            player.pause();
                            player.currentTime = 0;
                            player.muted = false;
                            player.volume = 1;
                        } catch (e) { }
                    }
                }).catch(() => {
                    player.muted = false;
                    player.volume = 1;
                });
            } else {
                player.muted = false;
                player.volume = 1;
            }
        } catch (e) { }
    }

    getActiveVoiceInfo(preferredVoiceSetting = null, preferredMode = null) {
        const raw = preferredVoiceSetting || (this.settings && this.settings.voice) || "female";
        // Tương thích giá trị cũ (vi-VN-NamMinhNeural -> male, còn lại -> female)
        const wantMale = raw === "male" || /namminh/i.test(raw);
        const modeSetting = preferredMode || (this.voiceModeSelect ? this.voiceModeSelect.value : (this.settings && this.settings.voiceMode)) || "auto";

        // 1. Nếu người dùng chọn ép chế độ "Máy chủ Backend":
        if (modeSetting === "backend") {
            if (wantMale) {
                return {
                    mode: "stream", voiceObj: null, backendVoice: "vi-VN-NamMinhNeural",
                    shortName: "Nam Minh (giọng nam Neural - Backend)",
                    detailName: "Microsoft Nam Minh Neural — giọng chuẩn tự nhiên (Máy chủ Backend)"
                };
            }
            return {
                mode: "stream", voiceObj: null, backendVoice: "vi-VN-HoaiMyNeural",
                shortName: "Hoài My (giọng nữ Neural - Backend)",
                detailName: "Microsoft Hoài My Neural — giọng chuẩn tự nhiên, truyền cảm (Máy chủ Backend)"
            };
        }

        // 2. Tìm kiếm giọng tiếng Việt có sẵn trên trình duyệt (Web Speech API)
        const voices = ("speechSynthesis" in window && typeof window.speechSynthesis.getVoices === "function")
            ? window.speechSynthesis.getVoices()
            : [];
        const viVoices = voices.filter(v => {
            const lang = (v.lang || "").toLowerCase().replace("_", "-");
            const name = (v.name || "").toLowerCase();
            return lang.startsWith("vi") || name.includes("vietnamese") || name.includes("tiếng việt");
        });
        const isMaleName = (n) => /namminh|nam minh|\ban\b/i.test(n);

        let chosen = null;
        if (wantMale) {
            chosen = viVoices.find(v => /namminh|nam minh/i.test(v.name))
                || viVoices.find(v => /\ban\b/i.test(v.name));
        } else {
            chosen = viVoices.find(v => /hoaimy|hoài my/i.test(v.name))
                || viVoices.find(v => /google/i.test(v.name))
                || viVoices.find(v => !isMaleName(v.name));
        }

        if (chosen) {
            const rawName = chosen.name || "Tiếng Việt";
            let friendly;
            if (/hoaimy/i.test(rawName)) friendly = "Microsoft Hoài My (giọng nữ)";
            else if (/namminh/i.test(rawName)) friendly = "Microsoft Nam Minh (giọng nam)";
            else if (/\ban\b/i.test(rawName)) friendly = "Microsoft An (giọng nam)";
            else if (/google/i.test(rawName)) friendly = "Google Tiếng Việt (giọng nữ)";
            else friendly = rawName.replace(/\s*-\s*Vietnamese.*$/i, "");
            return {
                mode: "native",
                voiceObj: chosen,
                backendVoice: null,
                shortName: friendly,
                detailName: friendly + " — đọc trực tiếp từ trình duyệt (Web Speech API)"
            };
        }

        // 3. Nếu người dùng chọn ép chế độ "Trình duyệt" nhưng máy tính/trình duyệt chưa có giọng
        if (modeSetting === "native") {
            return {
                mode: "stream",
                voiceObj: null,
                backendVoice: wantMale ? "vi-VN-NamMinhNeural" : "vi-VN-HoaiMyNeural",
                shortName: (wantMale ? "Nam Minh" : "Hoài My") + " (Tạm chuyển Backend do trình duyệt chưa có giọng)",
                detailName: "Trình duyệt chưa có giọng tiếng Việt (mở bằng Microsoft Edge hoặc dùng Máy chủ Backend)"
            };
        }

        // 4. Chế độ Tự động (auto) mà trình duyệt chưa có giọng: dùng Backend
        if (wantMale) {
            return {
                mode: "stream", voiceObj: null, backendVoice: "vi-VN-NamMinhNeural",
                shortName: "Nam Minh (giọng nam Neural - qua Backend)",
                detailName: "Microsoft Nam Minh Neural — giọng đọc máy chủ chuẩn tự nhiên (Backend)"
            };
        }
        return {
            mode: "stream", voiceObj: null, backendVoice: "vi-VN-HoaiMyNeural",
            shortName: "Hoài My (giọng nữ Neural - qua Backend)",
            detailName: "Microsoft Hoài My Neural — giọng đọc máy chủ chuẩn tự nhiên, truyền cảm (Backend)"
        };
    }

    updateVoiceStatusUI(preferredVoiceSetting = null) {
        const info = this.getActiveVoiceInfo(preferredVoiceSetting);
        if (this.currentVoiceNameDisplay) {
            this.currentVoiceNameDisplay.textContent = info.detailName;
        }
    }

    setVoiceBadgeSpeakingState(btnElement, isSpeaking, voiceShortName = null) {
        // Đã bỏ huy hiệu giọng đọc ở tin nhắn theo yêu cầu giao diện gọn gàng
    }

    stopCurrentSpeech() {
        // Tăng token phiên đọc để vô hiệu hóa tức thì mọi hàm async/promise đang chạy dở
        this.speechSessionToken = (this.speechSessionToken || 0) + 1;
        this.isPlayingSentenceQueue = false;
        this.isLiveStreamComplete = true;
        this.isWaitingForMoreSentences = false;
        this.liveRawCursor = 0;
        this.onLiveSentencesUpdated = null;
        this.sentenceQueue = [];
        this.sentenceIndex = 0;
        this.currentUtteranceText = null;

        // Hủy ngay lập tức mọi request fetch(/api/tts) đang chờ phản hồi
        if (this.ttsAbortController) {
            try {
                this.ttsAbortController.abort();
            } catch (e) { }
            this.ttsAbortController = null;
        }

        // TẮT SẠCH TẤT CẢ các Audio element đã từng được tạo để không bao giờ bị phát đè
        if (this.activeAudioElements && this.activeAudioElements.size > 0) {
            this.activeAudioElements.forEach(audioEl => {
                if (audioEl) {
                    try {
                        audioEl.onended = null;
                        audioEl.onerror = null;
                        audioEl.oncanplay = null;
                        audioEl.muted = true;
                        audioEl.volume = 0;
                        audioEl.pause();
                        audioEl.removeAttribute("src");
                        audioEl.load();
                    } catch (e) { }
                }
            });
            this.activeAudioElements.clear();
        }

        if (this.botAudioPlayer) {
            try {
                this.botAudioPlayer.onended = null;
                this.botAudioPlayer.onerror = null;
                this.botAudioPlayer.onplaying = null;
                this.botAudioPlayer.oncanplay = null;
                this.botAudioPlayer.pause();
                this.botAudioPlayer.currentTime = 0;
                this.botAudioPlayer.removeAttribute("src");
                this.botAudioPlayer.load();
            } catch (e) { }
        }

        if (this.currentBotAudio) {
            try {
                this.currentBotAudio.onended = null;
                this.currentBotAudio.onerror = null;
                this.currentBotAudio.onplaying = null;
                this.currentBotAudio.pause();
                this.currentBotAudio.currentTime = 0;
                this.currentBotAudio.removeAttribute("src");
                this.currentBotAudio.load();
            } catch (e) { }
            this.currentBotAudio = null;
        }

        if (this.ttsObjectUrls && this.ttsObjectUrls.length > 0) {
            this.ttsObjectUrls.forEach(u => {
                try { URL.revokeObjectURL(u); } catch (e) { }
            });
            this.ttsObjectUrls = [];
        }

        if (this.prefetchAudios) {
            this.prefetchAudios.clear();
        }

        // Hủy dứt khoát Web Speech API (Lưu ý: KHÔNG gọi pause() để tránh Chromium bị kẹt trạng thái paused)
        if (this.currentUtterance) {
            this.currentUtterance.onend = null;
            this.currentUtterance.onerror = null;
            this.currentUtterance = null;
        }

        if (window.speechSynthesis) {
            try {
                window.speechSynthesis.cancel();
            } catch (e) { }
        }

        document.querySelectorAll(".msg-action-btn.active").forEach(b => {
            b.classList.remove("active");
            const span = b.querySelector("span");
            if (span) span.textContent = "Đọc";
            const icon = b.querySelector("i");
            if (icon) icon.className = "fa-solid fa-volume-high";
        });
        this.setVoiceBadgeSpeakingState(null, false);
        this.currentBotSpeakBtn = null;
    }

    async toggleSpeech(text, btnElement) {
        // Nếu nút đang ở trạng thái "Dừng" (.active) hoặc đang đọc chính câu này -> Dừng ngay lập tức!
        if ((btnElement && btnElement.classList.contains("active")) || this.currentUtteranceText === text) {
            this.stopCurrentSpeech();
            return;
        }

        // Dừng câu khác đang đọc nếu có
        this.stopCurrentSpeech();

        await this.speakText(text, btnElement);
    }

    normalizeDates(text) {
        if (!text) return "";
        let t = text;

        // 1. dd/mm/yyyy hoặc d/m/yyyy hoặc dd-mm-yyyy hoặc dd.mm.yyyy (có tiền tố hoặc đứng độc lập)
        const replFullDate = (match, prefix, dStr, mStr, yStr) => {
            const p = prefix || "";
            const d = parseInt(dStr, 10);
            const mVal = parseInt(mStr, 10);
            const y = yStr;
            if (d >= 1 && d <= 31 && mVal >= 1 && mVal <= 12 && y.length === 4) {
                const hasNgay = /ngày\s*$/i.test(p);
                if (hasNgay) {
                    return `${p}${d} tháng ${mVal} năm ${y}`;
                }
                return `${p}ngày ${d} tháng ${mVal} năm ${y}`;
            }
            return match;
        };

        t = t.replace(/((?:từ|đến|vào|trước|sau|hạn|ngày)\s+)?\b([0-2]?[1-9]|3[01])[/.-](0?[1-9]|1[0-2])[/.-]((?:19|20)\d{2})\b/gi, replFullDate);
        t = t.replace(/\b([0-2]?[1-9]|3[01])\/(0?[1-9]|1[0-2])\/((?:19|20)\d{2})\b/g, replFullDate);

        // 2. mm/yyyy (tháng 11/2026, kỳ 1/2026)
        const replMonthYear = (match, prefix, mStr, yStr) => {
            const p = prefix || "";
            const mVal = parseInt(mStr, 10);
            const y = yStr;
            if (mVal >= 1 && mVal <= 12) {
                if (/tháng/i.test(p)) {
                    return `${p}${mVal} năm ${y}`;
                }
                return `${p}tháng ${mVal} năm ${y}`;
            }
            return match;
        };

        t = t.replace(/((?:trong|vào|từ|đến|tháng)\s+)?\b(0?[1-9]|1[0-2])\/((?:19|20)\d{2})\b/gi, replMonthYear);

        // 3. Năm học / niên khóa: 2025/2026
        t = t.replace(/\b((?:19|20)\d{2})\s*\/\s*((?:19|20)\d{2})\b/g, "$1 đến $2");

        // 4. Ngày/tháng (có từ ngày, từ, đến đứng trước): ngày 01/11, từ 01/11 đến 15/11
        const replDayMonth = (match, prefix, dStr, mStr) => {
            const p = prefix || "";
            const d = parseInt(dStr, 10);
            const mVal = parseInt(mStr, 10);
            if (d >= 1 && d <= 31 && mVal >= 1 && mVal <= 12) {
                if (/ngày/i.test(p)) {
                    return `${p}${d} tháng ${mVal}`;
                }
                return `${p}ngày ${d} tháng ${mVal}`;
            }
            return match;
        };

        t = t.replace(/((?:từ|đến|vào|trước|sau|ngày)\s+)\b([0-2]?[1-9]|3[01])\/(0?[1-9]|1[0-2])\b/gi, replDayMonth);

        return t;
    }

    normalizeDecimalsAndUnits(text) {
        if (!text) return "";
        let t = text;

        // 1. Số thập phân đi kèm đơn vị tiền tệ: 1,8 tỷ VNĐ, 2,5 triệu đ, 1.8 tỷ đồng
        t = t.replace(/\b(\d+)[,.](\d+)\s*(tỷ|triệu|nghìn|tr)(?:\s*(VNĐ|VND|đ|dong|đồng))?(?=[\s,.)!?;:]|$)/gi, (match, intPart, decPart, unit, cur) => {
            const curWord = (cur || /^(?:tỷ|triệu)$/i.test(unit)) ? " đồng" : "";
            return `${intPart} phẩy ${decPart} ${unit}${curWord}`;
        });

        // 2. Tiền tệ viết dạng: 1 tỷ 8, 2 triệu 5 (chỉ khi số sau là số đơn lẻ 1-9 và không có đơn vị nghìn/triệu/tỷ phía sau)
        t = t.replace(/\b(\d+)\s*(tỷ|triệu)\s*([1-9])(?!\s*(?:nghìn|ngàn|trăm|triệu|tỷ|\d))\s*(?:VNĐ|VND|đ|dong|đồng)?(?=[\s,.)!?;:]|$)/gi, "$1 $2 $3 đồng");

        // 3. Ký hiệu so sánh và đơn vị thời gian kỹ thuật (< 2s, <= 5s, > 100ms)
        t = t.replace(/<=\s*(\d+)\s*s\b/gi, "dưới hoặc bằng $1 giây");
        t = t.replace(/>=\s*(\d+)\s*s\b/gi, "từ $1 giây trở lên");
        t = t.replace(/<\s*(\d+)\s*s\b/gi, "dưới $1 giây");
        t = t.replace(/>\s*(\d+)\s*s\b/gi, "trên $1 giây");
        t = t.replace(/\b(\d+)\s*s\b(?=[\s,.)])/gi, "$1 giây");

        t = t.replace(/<\s*(\d+)\s*ms\b/gi, "dưới $1 mili giây");
        t = t.replace(/>\s*(\d+)\s*ms\b/gi, "trên $1 mili giây");
        t = t.replace(/\b(\d+)\s*ms\b/gi, "$1 mili giây");

        // Các phép so sánh còn lại: <= 2, >= 5, < 2, > 5
        t = t.replace(/<=\s*(\d+)/g, "dưới hoặc bằng $1");
        t = t.replace(/>=\s*(\d+)/g, "từ $1 trở lên");
        t = t.replace(/<\s*(\d+)/g, "dưới $1");
        t = t.replace(/>\s*(\d+)/g, "trên $1");

        // 4. Số thập phân thông thường có dấu phẩy: 1,8 -> 1 phẩy 8 (tránh dấu phẩy tách mệnh đề)
        t = t.replace(/\b(\d+),(\d{1,2})\b/g, "$1 phẩy $2");

        return t;
    }

    stripEnglishSubtitles(text) {
        if (!text) return "";
        return text.replace(/\s*\(([^)]+)\)/g, (match, content) => {
            const raw = content.trim();
            // Nếu có đuôi tên miền, website hoặc email thì giữ lại
            if (/\b(?:edu|vn|com|org|net|http|www)\b/i.test(raw) || raw.includes("@")) {
                return match;
            }
            // Nếu là viết tắt thương hiệu như (PTIT) hoặc (BCVT) thì giữ lại
            if (/^(?:PTIT|BCVT)$/i.test(raw)) {
                return match;
            }
            // Nếu là cụm từ tiếng Anh phụ đề (chữ cái La-tinh không dấu, gạch ngang, khoảng trắng)
            if (/^[A-Za-z\s,.\'\-–—]+$/.test(raw)) {
                const words = raw.split(/\s+/);
                if (words.length >= 2 || raw.length >= 7) {
                    return "";
                }
            }
            return match;
        });
    }

    normalizePhoneNumbers(text) {
        if (!text) return "";
        let t = text;

        const digitMap = {
            '0': 'không', '1': 'một', '2': 'hai', '3': 'ba', '4': 'bốn',
            '5': 'năm', '6': 'sáu', '7': 'bảy', '8': 'tám', '9': 'chín'
        };

        const digitsToWords = (dStr) => {
            return dStr.split("").filter(ch => digitMap[ch]).map(ch => digitMap[ch]).join(" ");
        };

        // Chuẩn hóa tiền tố liên hệ để giọng đọc phát âm rõ ràng
        t = t.replace(/\b(?:SĐT|Sđt|sđt|ĐT|Đt)\s*:\s*/gi, "số điện thoại: ");
        t = t.replace(/\b(?:SĐT|Sđt|sđt)\b/gi, "số điện thoại");
        t = t.replace(/\b(?:Hotline|hotline)\s*:\s*/gi, "hotline: ");
        t = t.replace(/\b(?:Tel|tel)\s*:\s*/gi, "điện thoại: ");
        t = t.replace(/\b(?:Fax|fax)\s*:\s*/gi, "fax: ");

        // 1. Tổng đài Hotline 1800/1900 xxxx (4 số đầu + 4 số cuối)
        t = t.replace(/\b(1[89]00)[\s.-]?(\d{4})\b/g, (match, prefix, suffix) => {
            return `${digitsToWords(prefix)}, ${digitsToWords(suffix)}`;
        });

        // 2. Số điện thoại quốc tế (+84 hoặc 84)
        t = t.replace(/(\+?84|\(\+?84\))[\s.-]?([0-9][0-9\s.-]{7,13}[0-9])\b/g, (match, code, raw) => {
            const lead = code.includes("+") ? "cộng tám bốn" : "tám bốn";
            const digits = raw.replace(/\D/g, "");
            const chunks = [];
            if (digits.length === 9) {
                chunks.push(digitsToWords(digits.substring(0, 2)));
                chunks.push(digitsToWords(digits.substring(2, 5)));
                chunks.push(digitsToWords(digits.substring(5)));
            } else if (digits.length === 10) {
                chunks.push(digitsToWords(digits.substring(0, 2)));
                chunks.push(digitsToWords(digits.substring(2, 6)));
                chunks.push(digitsToWords(digits.substring(6)));
            } else {
                return match;
            }
            return lead + ", " + chunks.join(", ");
        });

        // 3. Số điện thoại di động & cố định trong nước bắt đầu bằng 0 (10 đến 11 số)
        const replDomesticPhone = (match) => {
            const digits = match.replace(/\D/g, "");
            if (!digits.startsWith("0") || (digits.length !== 10 && digits.length !== 11)) {
                return match;
            }
            if (match.includes("/") || match.startsWith("0.0") || match.startsWith("0,0")) {
                return match;
            }

            const chunks = [];
            if (digits.length === 10) {
                // Di động: 4 số đầu, 3 số giữa, 3 số cuối (0988, 123, 456)
                if (digits.startsWith("03") || digits.startsWith("05") || digits.startsWith("07") || digits.startsWith("08") || digits.startsWith("09")) {
                    chunks.push(digitsToWords(digits.substring(0, 4)));
                    chunks.push(digitsToWords(digits.substring(4, 7)));
                    chunks.push(digitsToWords(digits.substring(7)));
                } else if (digits.startsWith("024") || digits.startsWith("028")) {
                    chunks.push(digitsToWords(digits.substring(0, 3)));
                    chunks.push(digitsToWords(digits.substring(3, 6)));
                    chunks.push(digitsToWords(digits.substring(6)));
                } else {
                    chunks.push(digitsToWords(digits.substring(0, 4)));
                    chunks.push(digitsToWords(digits.substring(4, 7)));
                    chunks.push(digitsToWords(digits.substring(7)));
                }
            } else if (digits.length === 11) {
                // Cố định Hà Nội (024) / TP.HCM (028): 3 số - 4 số - 4 số
                // Ví dụ: 024.33820854 -> không hai bốn, ba ba tám hai, không tám năm bốn
                if (digits.startsWith("024") || digits.startsWith("028")) {
                    chunks.push(digitsToWords(digits.substring(0, 3)));
                    chunks.push(digitsToWords(digits.substring(3, 7)));
                    chunks.push(digitsToWords(digits.substring(7)));
                } else {
                    chunks.push(digitsToWords(digits.substring(0, 4)));
                    chunks.push(digitsToWords(digits.substring(4, 7)));
                    chunks.push(digitsToWords(digits.substring(7)));
                }
            }
            return chunks.join(", ");
        };

        // Bắt mọi dạng số điện thoại di động & cố định trong nước (10 hoặc 11 chữ số):
        // Bao gồm: 024.33820854, 024 33820854, (024) 33820854, 024.3756.2186, 0988.123456, 0988.123.456...
        t = t.replace(/(?:\(0\d{2,3}\)|0[1-9])(?:[\s.-]?\d){8,10}\b/g, replDomesticPhone);

        return t;
    }

    stripSourcesForSpeech(text) {
        if (!text) return "";
        let s = text;
        // 1. Ghi chú nguồn trong ngoặc đơn: *(Nguồn: Tuyển sinh PTIT)*, (Nguồn: ...)
        s = s.replace(/[*_~]*\(\s*(?:📌|🔍)?\s*Nguồn(?:\s+[^\s():]+)?\s*:[^)]+\)[*_~]*/gi, " ");
        // 2. Toàn bộ khối nguồn ở cuối văn bản (cả tài liệu nội bộ 📌 và nguồn internet 🔍)
        s = s.replace(/(?:\n+\s*---\s*)?\n*[#*>\-\s]*(?:📌|🔍)?\s*\*{0,2}Nguồn(?:\s+(?:trích\s+dẫn|tham\s+khảo|tài\s+liệu|từ\s+Internet))?\s*:\*{0,2}[\s\S]*$/i, " ");
        // 3. Các dòng trích dẫn lẻ còn sót (📄 Trang ..., 🔗 link...)
        s = s.replace(/^\s*[-*•]?\s*📄\s*Trang\s+\d+.*$/gim, " ");
        s = s.replace(/^\s*[-*•]?\s*🔗\s*.*$/gim, " ");
        s = s.replace(/^\s*[-*•]?\s*🔍\s*.*$/gim, " ");
        return s;
    }

    normalizeCodes(text) {
        if (!text) return "";
        const digitMap = {
            "0": "không", "1": "một", "2": "hai", "3": "ba", "4": "bốn",
            "5": "năm", "6": "sáu", "7": "bảy", "8": "tám", "9": "chín"
        };
        const digitsToWords = (dStr) => dStr.split("").filter(ch => digitMap[ch]).map(ch => digitMap[ch]).join(" ");
        const majorAcronyms = new Set(["CNTT", "ATTT", "DTVT", "ĐTVT", "KTPM", "KHMT", "TMĐT", "CLC", "PTIT", "BCVT", "ĐTB", "GPA", "ĐRL"]);

        const codePrefixes =
            "mã\\s+(?:chương\\s+trình(?:\\s+đào\\s+tạo)?|ngành(?:\\s+đào\\s+tạo)?|chuyên\\s+ngành|" +
            "xét\\s+tuyển|tuyển\\s+sinh|học\\s+phần|môn(?:\\s+học)?|sinh\\s+viên|học\\s+viên|" +
            "hồ\\s+sơ|trường|đào\\s+tạo|đơn\\s+vị|bưu\\s+chính|định\\s+danh|giao\\s+dịch|" +
            "tra\\s+cứu|lớp|khóa|tài\\s+khoản|otp|pin|bảo\\s+mật|thí\\s+sinh|hội\\s+đồng)|" +
            "mã\\s*số|mã(?=\\s*[:=-])|số\\s+báo\\s+danh|sbd|cccd|cmnd|mssv|msv|stk|số\\s+tài\\s+khoản";

        const pat1 = new RegExp(`\\b(${codePrefixes})(?:\\s*[:=-]\\s*|\\s+)([A-Za-z0-9][A-Za-z0-9_.-]{1,})(?=[\\s),.;:!?]|$)`, "gi");
        let t = text.replace(pat1, (match, prefix, code) => {
            if (majorAcronyms.has(code.toUpperCase())) return match;
            const hasDigit = /\d/.test(code);
            const isAllUpper = code === code.toUpperCase() && /[A-Z]/.test(code);
            if (!hasDigit && !isAllUpper) return match;
            if (/^\d{4}$/.test(code) && (code.startsWith("19") || code.startsWith("20")) && !match.includes(":")) {
                return match;
            }

            const cleanCode = /^\d+(?:\.\d+)+$/.test(code) ? code.replace(/\./g, "") : code;
            const tokens = cleanCode.match(/[A-Za-zÀ-ỹ]+|\d+/g) || [cleanCode];
            const formatted = tokens.map(tok => {
                if (/^\d+$/.test(tok)) {
                    return tok.length >= 4 ? digitsToWords(tok) : tok;
                }
                const tokIsUpper = tok === tok.toUpperCase() && /[A-Z]/.test(tok);
                if (tokIsUpper && tok.length <= 5 && !majorAcronyms.has(tok.toUpperCase())) {
                    return tok.toLowerCase().split("").join(" ");
                }
                return tok;
            });
            return `${prefix}: ${formatted.join(", ")}`;
        });

        const nonCodeUnits = "(?:vnđ|vnd|đồng|đ(?=[\\s/.,;!?]|$)|triệu|tỷ|nghìn|ngàn|xu|usd|người|sinh\\s+viên|thí\\s+sinh|học\\s+sinh|chỉ\\s+tiêu|tín\\s+chỉ|lượt|lần|hồ\\s+sơ|điểm|giây|phút|giờ|môn|bài|trang|năm|tháng|ngày|mét|km|kg|mb|gb)";
        const pat2 = new RegExp(`\\b(\\d{6,15})\\b(?!\\s*${nonCodeUnits})`, "gi");
        t = t.replace(pat2, (match, digits) => digitsToWords(digits));

        return t;
    }

    normalizeTextForSpeech(text) {
        if (!text) return "";

        let s = this.stripSourcesForSpeech(text);

        // 0.01. Chuẩn hóa ngày tháng năm TRƯỚC TIÊN (01/11/2026 -> ngày 1 tháng 11 năm 2026) để tránh bị dấu gạch chéo '/' biến thành 'trên'/'hoặc'
        s = this.normalizeDates(s);

        // 0.02. Chuẩn hóa số thập phân và đơn vị so sánh (1,8 tỷ VNĐ -> 1 phẩy 8 tỷ đồng, < 2s -> dưới 2 giây) TRƯỚC KHI ký tự <, > bị lọc
        s = this.normalizeDecimalsAndUnits(s);

        // 0.1. Loại bỏ các chú thích phụ đề tiếng Anh trong ngoặc đơn (VD: Introduction to Artificial Intelligence...)
        // để bộ đọc tiếng Việt không bị phát âm lẫn từ tiếng Anh (như chữ 'to' bị đọc thành tiếng Việt),
        // đồng thời bảo tồn nguyên vẹn tên miền website (VD: clc.ptit.edu.vn) và từ viết tắt (PTIT)
        s = this.stripEnglishSubtitles(s);

        // 0.2. Chuẩn hóa số điện thoại thành từng cụm chữ số tự nhiên ngắt nhịp TRƯỚC KHI regex tiền tệ quét qua
        s = this.normalizePhoneNumbers(s);

        // 0.25. Chuẩn hóa mã chương trình, mã ngành, mã học phần... thành chữ số tự nhiên (chống đọc kiểu tiền)
        s = this.normalizeCodes(s);

        // 1. Tránh lặp từ 'Học viện' và chuẩn hóa cách đọc PTIT (dạng thường 'bưu chính viễn thông' để Edge-TTS không ngắt nhịp tại chữ 'Viễn')
        s = s.replace(/Học\s+viện\s+(?:Công\s+nghệ\s+)?Bưu\s+chính\s+Viễn\s+thông\s*\(\s*PTIT\s*\)/gi, "Học viện Công nghệ bưu chính viễn thông");
        s = s.replace(/Cổng\s+thông\s+tin\s+(?:Học\s+viện\s+)?PTIT\b/gi, "Cổng thông tin bưu chính viễn thông");
        s = s.replace(/Học\s+viện\s+PTIT\b/gi, "Học viện bưu chính viễn thông");
        s = s.replace(/\bPTIT\b/g, "bưu chính viễn thông");

        s = s.replace(/\bBưu[\s-]+chính\s+Viễn[\s-]+thông\b/gi, "bưu chính viễn thông");
        s = s.replace(/\bBưu[\s-]+chính\b/gi, "bưu chính");
        s = s.replace(/\bViễn[\s-]+thông\b/gi, "viễn thông");

        // 1.1. Chuẩn hóa ngắt dòng và gạch đầu dòng (bullet points) thành dấu ngắt câu để đọc tách bạch
        s = s.replace(/(?<![.!?;:])\s*\n\s*[-*•+]\s*/g, ". ");
        s = s.replace(/^\s*[-*•+]\s*/gm, "");
        s = s.replace(/(?<![.!?;:,])\s*\n/g, ". ");

        // 2. Loại bỏ các khối code, markdown, link, ký tự đặc biệt
        s = s.replace(/```[\s\S]*?```/g, " ")
            .replace(/`[^`]*`/g, " ")
            .replace(/\|[^\n]+\|/g, " ")
            .replace(/[-:]{2,}\s*\|\s*[-:]{2,}/g, " ")
            .replace(/!\[.*?\]\(.*?\)/g, " ")
            .replace(/\[(.*?)\]\(.*?\)/g, "$1")
            .replace(/https?:\/\/\S+/g, " ")
            .replace(/[*_~#><]/g, " ")
            .replace(/⚠️|📌|🔍|📄|🔗|✅|❌|🎓|•/g, " ")
            .replace(/\$\s*\\ge(q)?\s*([^$]+)\$/g, "từ $2 trở lên")
            .replace(/\$\s*\\le(q)?\s*([^$]+)\$/g, "dưới hoặc bằng $2")
            .replace(/\$([^$]+)\$/g, "$1")
            .replace(/\$/g, " ");

        // 3. Chuẩn hóa số tiền và các số hàng triệu/nghìn có dấu chấm (VD: 1.410.000, 1.410.000 VNĐ, 550.000đ/tín chỉ)
        // Tránh lỗi Windows/Edge đọc "1.410.000" thành "một nghìn 4 trăm 10 không không không đồng"
        const currencyRegex = /\b(\d{1,3}(?:\.\d{3})+)(?:\s*(\/(?:tháng|năm|kỳ|học\s+kỳ|tín\s+chỉ|[^\s,.?!]+(?:\s+[^\s,.?!]+)?)|(?:VNĐ|VND|đồng|đ(?=[\s\/,.!?]|$))(?:\/(?:tháng|năm|kỳ|học\s+kỳ|tín\s+chỉ|[^\s,.?!]+(?:\s+[^\s,.?!]+)?))?))?/gi;
        s = s.replace(currencyRegex, (match, numStr, suffix) => {
            const rawDigits = numStr.replace(/\./g, "");
            const val = parseInt(rawDigits, 10);
            if (isNaN(val)) return match;

            let textNum = "";
            if (val >= 1000000000) {
                const ty = Math.floor(val / 1000000000);
                const trieu = Math.floor((val % 1000000000) / 1000000);
                textNum = ty + " tỷ";
                if (trieu > 0) textNum += " " + trieu + " triệu";
            } else if (val >= 1000000) {
                const trieu = Math.floor(val / 1000000);
                const nghin = Math.floor((val % 1000000) / 1000);
                textNum = trieu + " triệu";
                if (nghin > 0) {
                    const tramNghin = Math.floor(nghin / 100);
                    const chucNghin = nghin % 100;
                    if (tramNghin === 0 && chucNghin > 0) {
                        textNum += " không trăm " + chucNghin + " nghìn";
                    } else {
                        textNum += " " + nghin + " nghìn";
                    }
                }
            } else if (val >= 1000) {
                const nghin = Math.floor(val / 1000);
                const tram = val % 1000;
                textNum = nghin + " nghìn";
                if (tram > 0) textNum += " " + tram;
            } else {
                textNum = String(val);
            }

            const suf = (suffix || "").trim();
            const hasCurrency = /\b(?:vnđ|vnd|đồng)\b|đ(?:\b|\/)/i.test(suf) || /^\/(?:tháng|năm|kỳ|học\s+kỳ|tín\s+chỉ)/i.test(suf);
            let cleanSuf = suf.replace(/^(?:vnđ|vnd|đồng|đ)\s*/i, "").trim();
            if (cleanSuf.startsWith("/")) {
                cleanSuf = " một " + cleanSuf.substring(1).trim();
            }

            if (hasCurrency) {
                return cleanSuf ? textNum + " đồng trên" + cleanSuf : textNum + " đồng";
            }
            return cleanSuf ? textNum + " trên" + cleanSuf : textNum;
        });

        // 4. Mở rộng từ viết tắt chuyên ngành PTIT
        const abbrevs = [
            [/\bPTIT\b/g, "Học viện bưu chính viễn thông"],
            [/\bBCVT\b/g, "bưu chính viễn thông"],
            [/\bCNTT\b/g, "Công nghệ thông tin"],
            [/\bATTT\b/g, "An toàn thông tin"],
            [/\b(DTVT|ĐTVT)\b/g, "Điện tử viễn thông"],
            [/\bKTPM\b/g, "Kỹ thuật phần mềm"],
            [/\bKHMT\b/g, "Khoa học máy tính"],
            [/\bTMĐT\b/g, "Thương mại điện tử"],
            [/\b(TKĐPT|ĐPT)\b/g, "Đa phương tiện"],
            [/\bCLC\b/g, "Chất lượng cao"],
            [/(\d+)\s*(TC|tc|tín chỉ)\b/g, "$1 tín chỉ"],
            [/\bTC\b/g, "tín chỉ"],
            [/\b(HK1|HK\s*1|HKI)\b/g, "Học kỳ một"],
            [/\b(HK2|HK\s*2|HKII)\b/g, "Học kỳ hai"],
            [/\b(HK3|HK\s*3|HKIII)\b/g, "Học kỳ ba"],
            [/\b(ĐTB|GPA)\b/g, "Điểm trung bình"],
            [/\bSV\b/g, "sinh viên"],
            [/\bGV\b/g, "giảng viên"],
            [/\bKHTN\b/g, "Khoa học tự nhiên"],
            [/\bGDTC\b/g, "Giáo dục thể chất"],
            [/\bGDQP\b|\bGDQP-AN\b/g, "Giáo dục quốc phòng an ninh"],
            [/\bCTSV\b/g, "Công tác sinh viên"],
            [/\bĐRL\b/g, "Điểm rèn luyện"],
            [/\b(?:T\.P\.|TP\.|TP)\s+Hồ\s+Chí\s+Minh\b/g, "Thành phố Hồ Chí Minh"],
            [/\b(?:T\.P\.|TP\.|TP)\s+HCM\b/g, "Thành phố Hồ Chí Minh"],
            [/\b(?:T\.P\.|TP\.|TP)\s+Hà\s+Nội\b/g, "Thành phố Hà Nội"],
            [/\b(?:T\.P\.|TP\.|TP)\s+Đà\s+Nẵng\b/g, "Thành phố Đà Nẵng"],
            [/\b(?:T\.P\.|TP\.|TP)\s+Hải\s+Phòng\b/g, "Thành phố Hải Phòng"],
            [/\b(?:T\.P\.|TP\.|TP)\s+Cần\s+Thơ\b/g, "Thành phố Cần Thơ"],
            [/\b(?:T\.P\.|TP\.|TP)\s+Huế\b/g, "Thành phố Huế"],
            [/\b(?:T\.P\.|TP\.)\s*(?=[A-ZĐÀ-Ỹ])/g, "Thành phố "],
            [/\bTP\s+(?=[A-ZĐÀ-Ỹ][a-zà-ỹ]+)/g, "Thành phố "],
            [/\bTX\.\s*(?=[A-ZĐÀ-Ỹ])|\bTX\s+(?=[A-ZĐÀ-Ỹ][a-zà-ỹ]+)/g, "Thị xã "],
            [/\bTT\.\s*(?=[A-ZĐÀ-Ỹ])|\bTT\s+(?=[A-ZĐÀ-Ỹ][a-zà-ỹ]+)/g, "Thị trấn "]
        ];

        for (const [rgx, rep] of abbrevs) {
            s = s.replace(rgx, rep);
        }

        // Đảm bảo lại một lần nữa 'bưu chính viễn thông' viết thường liền mạch không có dấu gạch ngang
        s = s.replace(/\bBưu[\s-]+chính\s+Viễn[\s-]+thông\b/gi, "bưu chính viễn thông");
        s = s.replace(/\bBưu[\s-]+chính\b/gi, "bưu chính");
        s = s.replace(/\bViễn[\s-]+thông\b/gi, "viễn thông");

        // 5. Xử lý dấu gạch chéo '/' theo đúng ngữ cảnh (tránh đọc là 'phần')
        // 5.1. Đơn vị tính / tiền tệ: đ/tín chỉ, /tháng -> 'trên mỗi'
        s = s.replace(/(?:đ|VNĐ|VND|đồng)\s*\/\s*([a-zA-ZÀ-ỹ]+)/gi, " đồng trên mỗi $1");
        s = s.replace(/(\d+)\s*\/\s*(\d+)/g, "$1 trên $2");
        s = s.replace(/\/\s*(?:tín\s+chỉ|tháng|kỳ|học\s+kỳ|năm|người|sinh\s+viên|môn|buổi)\b/gi, " trên mỗi ");

        // 5.2. Chuẩn hóa tên miền website (VD: clc.ptit.edu.vn / it.ptit.edu.vn)
        s = s.replace(/\b([a-zA-Z0-9-]+)\.ptit\.edu\.vn\b/gi, (match, sub) => {
            let subClean = sub.toLowerCase();
            if (subClean === "clc") subClean = "c l c";
            else if (subClean === "it") subClean = "i t";
            else if (subClean === "sdh") subClean = "s d h";
            else if (subClean === "daotao") subClean = "đào tạo";
            else if (subClean === "giaovu") subClean = "giáo vụ";
            else if (subClean === "student") subClean = "sinh viên";
            else if (subClean === "tuyensinh") subClean = "tuyển sinh";
            return `${subClean} chấm p tit chấm edu chấm vn`;
        });
        s = s.replace(/\bptit\.edu\.vn\b/gi, "p tit chấm edu chấm vn");

        // 5.25. Chuẩn hóa số hiệu văn bản hành chính (Quyết định, Thông báo, Kế hoạch... VD: 1462/QĐ-HV, 25/TB-HV, 01/NQ-CP)
        // Dấu gạch chéo '/' ngăn cách số hiệu và ký hiệu văn bản -> chuyển thành dấu phẩy để ngắt nhịp tự nhiên (không đọc là 'hoặc')
        s = s.replace(/\b(\d+)\s*\/\s*([A-ZĐÀ-Ỹ]{2,}(?:-[A-ZĐÀ-Ỹ0-9]+)*)(?=[\s),.;:!?]|$)/g, (match, docNum, docSymbol) => {
            let cleanSym = docSymbol.replace(/-/g, " ");
            cleanSym = cleanSym.replace(/(^|\s)QĐ(?=\s|$)/g, "$1Quyết định");
            cleanSym = cleanSym.replace(/(^|\s)HV(?=\s|$)/g, "$1Học viện");
            cleanSym = cleanSym.replace(/(^|\s)TB(?=\s|$)/g, "$1Thông báo");
            cleanSym = cleanSym.replace(/(^|\s)KH(?=\s|$)/g, "$1Kế hoạch");
            cleanSym = cleanSym.replace(/(^|\s)NQ(?=\s|$)/g, "$1Nghị quyết");
            cleanSym = cleanSym.replace(/(^|\s)NĐ(?=\s|$)/g, "$1Nghị định");
            cleanSym = cleanSym.replace(/(^|\s)TT(?=\s|$)/g, "$1Thông tư");
            cleanSym = cleanSym.replace(/(^|\s)CT(?=\s|$)/g, "$1Chỉ thị");
            cleanSym = cleanSym.replace(/(^|\s)BCVT(?=\s|$)/g, "$1Bưu chính Viễn thông");
            cleanSym = cleanSym.replace(/(^|\s)(?:BGDĐT|BGD)(?=\s|$)/g, "$1Bộ Giáo dục và Đào tạo");
            cleanSym = cleanSym.replace(/(^|\s)BTTTT(?=\s|$)/g, "$1Bộ Thông tin và Truyền thông");
            return `${docNum}, ${cleanSym}`;
        });
        s = s.replace(/\b(\d+)\s*\/\s*(Quyết\s+định|Thông\s+báo|Kế\s+hoạch|Nghị\s+định|Nghị\s+quyết|Thông\s+tư)\b/gi, "$1, $2");

        // 5.3. Dấu gạch chéo giữa 2 tên miền hoặc lựa chọn: clc / it -> 'hoặc'
        s = s.replace(/([a-zA-ZÀ-ỹ0-9.-]+)\s*\/\s*([a-zA-ZÀ-ỹ0-9.-]+)/g, "$1 hoặc $2");
        s = s.replace(/\//g, " hoặc ");
        s = s.replace(/%/g, " phần trăm ");
        s = s.replace(/&/g, " và ");
        s = s.replace(/\s+/g, " ").trim();

        return s;
    }

    splitIntoSentences(text, maxChunkLen = 170) {
        if (!text) return [];

        // Tiền xử lý chuẩn hóa toàn bộ văn bản (từ viết tắt, số tiền)
        const clean = this.normalizeTextForSpeech(text);
        if (!clean) return [];

        // Chia theo dòng và dấu câu (. ! ? ;)
        const rawParts = clean.split(/[.!?;\n]+/);
        const subChunks = [];

        for (let part of rawParts) {
            part = part.trim();
            if (!part) continue;

            if (part.length <= maxChunkLen) {
                subChunks.push(part);
            } else {
                // Nếu câu dài quá 170 ký tự -> tách tiếp theo dấu phẩy, hai chấm hoặc khoảng trắng để stream trực tiếp không bị cắt (không cắt dấu phẩy trong số thập phân)
                const clauses = part.split(/(?<!\d)[,–—]+|:(?!\/\/)/);
                let temp = "";
                for (let cl of clauses) {
                    cl = cl.trim();
                    if (!cl) continue;
                    if (!temp) {
                        temp = cl;
                    } else if ((temp.length + 2 + cl.length) <= maxChunkLen) {
                        temp += ", " + cl;
                    } else {
                        subChunks.push(temp);
                        temp = cl;
                    }
                }
                if (temp) {
                    // Nếu 1 mệnh đề vẫn dài hơn maxChunkLen -> ưu tiên tách tại từ nối ngữ nghĩa để không chặt đôi từ ghép (vd: "viễn | thông")
                    const minSplit = Math.floor(maxChunkLen * 0.45);
                    const phraseBoundaries = [" của ", " tại ", " ở ", " về ", " và ", " hoặc ", " để ", " với ", " trong ", " theo ", " cho ", " là ", " nhưng ", " khi "];
                    while (temp.length > maxChunkLen) {
                        let cutIdx = -1;
                        for (const sep of phraseBoundaries) {
                            const idx = temp.lastIndexOf(sep, maxChunkLen);
                            if (idx >= minSplit && idx > cutIdx) cutIdx = idx;
                        }
                        if (cutIdx <= 0) cutIdx = temp.lastIndexOf(" ", maxChunkLen);
                        if (cutIdx <= 0) cutIdx = maxChunkLen;
                        subChunks.push(temp.substring(0, cutIdx).trim());
                        temp = temp.substring(cutIdx).trim();
                    }
                    if (temp) subChunks.push(temp);
                }
            }
        }

        // Gom các câu quá ngắn (< 30 ký tự) vào câu kế tiếp CHỈ KHI không phải là tiêu đề / mục danh sách có dấu hai chấm ':'
        const merged = [];
        let buffer = "";

        for (const s of subChunks) {
            if (!buffer) {
                buffer = s;
            } else if (!buffer.includes(":") && !s.includes(":") && (buffer.length < 25 || s.length < 12) && (buffer.length + 1 + s.length <= maxChunkLen)) {
                buffer += ". " + s;
            } else {
                merged.push(buffer);
                buffer = s;
            }
        }
        if (buffer) merged.push(buffer);

        return merged.length > 0 ? merged : [clean.substring(0, maxChunkLen)];
    }

    findLiveSentenceCutIndex(unprocessed, isFirstChunk = false) {
        if (!unprocessed) return -1;

        // Nếu mở đầu bằng dòng trống -> cắt bỏ dòng trống
        const leadingWsMatch = unprocessed.match(/^\s*\n/);
        if (leadingWsMatch) {
            return leadingWsMatch[0].length;
        }

        // Nếu đang ở dòng bảng Markdown (bắt đầu bằng '|') hoặc đường kẻ ngang -> chờ tới hết dòng '\n'
        const trimmedStart = unprocessed.replace(/^[ \t]+/, "");
        if (trimmedStart.startsWith("|") || /^[-*_]{3,}/.test(trimmedStart)) {
            const nlIdx = unprocessed.indexOf("\n");
            return nlIdx >= 0 ? nlIdx + 1 : -1;
        }

        const minPunctLen = isFirstChunk ? 22 : 42;
        const minClauseLen = isFirstChunk ? 32 : 95;

        for (let i = 0; i < unprocessed.length; i++) {
            const ch = unprocessed[i];
            const nextCh = unprocessed[i + 1] || "";

            // 1. Ngắt theo xuống dòng (đảm bảo từng dòng bullet/mục ngắt thành câu riêng)
            if (ch === "\n") {
                const lineText = unprocessed.slice(0, i).trim();
                if (!lineText || lineText.startsWith("|")) {
                    return i + 1;
                }
                if (lineText.length >= 10) {
                    return i + 1;
                }
            }

            // 2. Ngắt theo dấu kết câu (. ! ? ;) có khoảng trắng phía sau (không ngắt số tiền 1.410.000)
            if ((ch === "." || ch === "!" || ch === "?" || ch === ";") && /\s/.test(nextCh)) {
                if (ch === ".") {
                    const beforeDot = unprocessed.slice(0, i);
                    // Không ngắt sau số thứ tự đầu mục (1., 2.) hoặc từ viết tắt học hàm/địa danh
                    if (/(?:^|[\s(])(?:TS|PGS|GS|ThS|CN|KS|TP|Dr|Mr|Ms|Mrs|St|vs|v\.v|\d+)$/i.test(beforeDot)) {
                        continue;
                    }
                }
                if (i + 1 >= minPunctLen) {
                    return i + 2;
                }
            }

            // 3. Với câu đầu tiên (hoặc câu quá dài), ngắt sớm ở dấu phẩy/hai chấm để phát tiếng ngay lập tức
            if ((ch === "," || ch === ":") && (nextCh === " " || nextCh === "\n")) {
                if (i + 1 >= minClauseLen) {
                    return i + 2;
                }
            }
        }

        return -1;
    }

    feedLiveSpeech(rawText, isFinal = false, btnElement = null, activeToken = null) {
        if (!rawText) return activeToken;

        // Loại bỏ phần chân trang nguồn (cả tài liệu nội bộ lẫn tra Internet) và ghi chú (Nguồn: ...) khi đang stream
        rawText = this.stripSourcesForSpeech(rawText).trim();
        if (!rawText) return activeToken;

        // Nếu người dùng đã bấm "Dừng" trong lúc đang stream -> không tự phát tiếp nữa
        if (activeToken !== null && this.speechSessionToken !== activeToken) {
            return activeToken;
        }

        let cursor = activeToken === null ? 0 : (this.liveRawCursor || 0);
        const newSentences = [];
        let isFirst = activeToken === null && newSentences.length === 0;

        while (cursor < rawText.length) {
            const unprocessed = rawText.slice(cursor);
            const cutIdx = this.findLiveSentenceCutIndex(unprocessed, isFirst);
            if (cutIdx <= 0) break;

            const segment = unprocessed.slice(0, cutIdx);
            cursor += cutIdx;

            const pieces = this.splitIntoSentences(segment, 170);
            if (pieces.length > 0) {
                newSentences.push(...pieces);
                isFirst = false;
            }
        }

        if (isFinal && cursor < rawText.length) {
            const tail = rawText.slice(cursor);
            cursor = rawText.length;
            const tailPieces = this.splitIntoSentences(tail, 170);
            if (tailPieces.length > 0) {
                newSentences.push(...tailPieces);
            }
        }

        // Chưa đủ 1 mệnh đề/câu hoàn chỉnh để đọc
        if (activeToken === null && newSentences.length === 0) {
            return null;
        }

        // Khởi tạo phiên đọc trực tiếp ngay khi có câu đầu tiên
        if (activeToken === null) {
            this.stopCurrentSpeech();
            const sessionToken = this.speechSessionToken;
            this.liveRawCursor = cursor;
            this.isLiveStreamComplete = !!isFinal;
            this.currentUtteranceText = rawText;
            this.currentBotSpeakBtn = btnElement;

            const selectedSpeed = parseFloat(this.settings.voiceSpeed || 1.35);
            const voiceInfo = this.getActiveVoiceInfo();
            this.setVoiceBadgeSpeakingState(btnElement, true, voiceInfo.shortName);

            if (voiceInfo.mode === "native" && voiceInfo.voiceObj && window.speechSynthesis) {
                this.startNativeStreamingQueue(newSentences, voiceInfo, selectedSpeed, btnElement, sessionToken, !isFinal);
            } else {
                this.startSentenceStreamingQueue(newSentences, voiceInfo, selectedSpeed, btnElement, sessionToken, !isFinal);
            }
            return sessionToken;
        }

        // Cập nhật thêm câu mới vào hàng đợi đang phát
        this.liveRawCursor = cursor;
        this.currentUtteranceText = rawText;
        if (newSentences.length > 0) {
            this.sentenceQueue.push(...newSentences);
        }
        if (isFinal) {
            this.isLiveStreamComplete = true;
        }
        if ((newSentences.length > 0 || isFinal) && typeof this.onLiveSentencesUpdated === "function") {
            this.onLiveSentencesUpdated();
        }
        return activeToken;
    }

    async speakText(text, btnElement = null) {
        if (!text) return;

        this.stopCurrentSpeech();
        const sessionToken = this.speechSessionToken;
        this.currentUtteranceText = text;
        this.currentBotSpeakBtn = btnElement;
        this.isLiveStreamComplete = true;
        if (!this.activeAudioElements) {
            this.activeAudioElements = new Set();
        }

        // Đổi nút sang trạng thái "Dừng" ngay lập tức để người dùng có thể bấm dừng bất kỳ lúc nào
        if (btnElement) {
            btnElement.classList.add("active");
            const span = btnElement.querySelector("span");
            if (span) span.textContent = "Dừng";
            const icon = btnElement.querySelector("i");
            if (icon) icon.className = "fa-solid fa-stop";
        }

        const selectedSpeed = parseFloat(this.settings.voiceSpeed || 1.35);
        const voiceInfo = this.getActiveVoiceInfo();

        this.setVoiceBadgeSpeakingState(btnElement, true, voiceInfo.shortName);

        // Tách câu thành các đoạn ngắn (<= 170 ký tự) cho cả 2 chế độ:
        // Ngăn chặn triệt để lỗi Chromium dừng sau 15 giây hoặc treo khi đọc cả đoạn dài
        let sentences = this.splitIntoSentences(text, 170);
        if (sentences.length === 0) {
            this.stopCurrentSpeech();
            return;
        }

        // CHẾ ĐỘ 1: Nếu người dùng chọn hoặc trình duyệt có giọng tiếng Việt trực tiếp
        if (voiceInfo.mode === "native" && voiceInfo.voiceObj && window.speechSynthesis) {
            this.startNativeStreamingQueue(sentences, voiceInfo, selectedSpeed, btnElement, sessionToken, false);
            return;
        }

        // CHẾ ĐỘ 2: Đọc qua Backend (/api/tts - Edge-TTS / gTTS)
        await this.startSentenceStreamingQueue(sentences, voiceInfo, selectedSpeed, btnElement, sessionToken, false);
    }

    startNativeStreamingQueue(sentences, voiceInfo, speed, btnElement, sessionToken, isLiveStreaming = false) {
        this.sentenceQueue = sentences;
        this.sentenceIndex = 0;
        this.isPlayingSentenceQueue = true;
        this.isLiveStreamComplete = !isLiveStreaming;
        this.isWaitingForMoreSentences = false;

        if (btnElement) {
            btnElement.classList.add("active");
            const span = btnElement.querySelector("span");
            if (span) span.textContent = "Dừng";
            const icon = btnElement.querySelector("i");
            if (icon) icon.className = "fa-solid fa-stop";
        }
        this.setVoiceBadgeSpeakingState(btnElement, true, voiceInfo.shortName);

        const viVoice = voiceInfo.voiceObj;

        const playNextNative = () => {
            if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) return;
            if (this.sentenceIndex >= this.sentenceQueue.length) {
                if (!this.isLiveStreamComplete) {
                    this.isWaitingForMoreSentences = true;
                    return;
                }
                if (this.speechSessionToken === sessionToken) {
                    this.stopCurrentSpeech();
                }
                return;
            }

            this.isWaitingForMoreSentences = false;
            const sentenceText = this.sentenceQueue[this.sentenceIndex];
            const utterance = new SpeechSynthesisUtterance(sentenceText);
            utterance.lang = viVoice.lang || "vi-VN";
            utterance.voice = viVoice;
            utterance.rate = speed;
            this.currentUtterance = utterance;

            utterance.onend = () => {
                if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) return;
                this.sentenceIndex++;
                playNextNative();
            };

            utterance.onerror = () => {
                if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) return;
                this.sentenceIndex++;
                playNextNative();
            };

            try {
                window.speechSynthesis.resume();
                window.speechSynthesis.speak(utterance);
            } catch (e) {
                this.sentenceIndex++;
                playNextNative();
            }
        };

        this.onLiveSentencesUpdated = () => {
            if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) return;
            if (this.isWaitingForMoreSentences) {
                this.isWaitingForMoreSentences = false;
                playNextNative();
            }
        };

        try {
            window.speechSynthesis.cancel();
        } catch (e) { }
        setTimeout(() => playNextNative(), 80);
    }

    playViaNativeSpeech(text, voiceInfo, speed, btnElement, sessionToken) {
        let sentences = this.splitIntoSentences(text, 170);
        if (sentences.length === 0) {
            this.stopCurrentSpeech();
            return;
        }
        this.startNativeStreamingQueue(sentences, voiceInfo, speed, btnElement, sessionToken, false);
    }

    async startSentenceStreamingQueue(sentences, voiceInfo, speed, btnElement, sessionToken, isLiveStreaming = false) {
        this.sentenceQueue = sentences;
        this.sentenceIndex = 0;
        this.isPlayingSentenceQueue = true;
        this.isLiveStreamComplete = !isLiveStreaming;
        this.isWaitingForMoreSentences = false;
        this.prefetchAudios = new Map();
        this.ttsObjectUrls = [];
        this.ttsAbortController = new AbortController();
        const abortSignal = this.ttsAbortController.signal;

        if (!this.botAudioPlayer) {
            this.botAudioPlayer = new Audio();
            this.botAudioPlayer.preload = "auto";
        }

        // Hàm tải URL âm thanh cho từng câu (tuần tự, có cache, hủy ngay lập tức nếu đổi câu/dừng)
        const getSentenceAudioUrl = async (idx) => {
            if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) return null;
            if (idx >= this.sentenceQueue.length) return null;
            if (this.prefetchAudios.has(idx)) {
                return await this.prefetchAudios.get(idx);
            }

            const sentenceText = (this.sentenceQueue[idx] || "").trim();
            if (!sentenceText) return null;

            const loadPromise = (async () => {
                for (let attempt = 0; attempt < 3; attempt++) {
                    if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) return null;
                    const attemptCtrl = new AbortController();
                    const onGlobalAbort = () => attemptCtrl.abort();
                    abortSignal.addEventListener("abort", onGlobalAbort);
                    const attemptTimer = setTimeout(() => attemptCtrl.abort(), 8500);
                    try {
                        const selectedSpeed = parseFloat(this.settings.voiceSpeed || 1.35);
                        const resp = await fetch("/api/tts", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                text: sentenceText,
                                voice: voiceInfo.backendVoice || "vi-VN-HoaiMyNeural",
                                speed: selectedSpeed
                            }),
                            signal: attemptCtrl.signal
                        });
                        if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) return null;
                        if (resp.ok) {
                            const data = await resp.json();
                            if (data.audio_url && this.speechSessionToken === sessionToken && this.isPlayingSentenceQueue) {
                                // Tải trọn file MP3 về Blob để phát mượt từ RAM, không bị ngắt quãng
                                try {
                                    const audioResp = await fetch(data.audio_url, {
                                        cache: "no-store",
                                        signal: attemptCtrl.signal
                                    });
                                    if (audioResp.ok) {
                                        const buf = await audioResp.arrayBuffer();
                                        if (buf.byteLength > 512) {
                                            const blob = new Blob([buf], { type: "audio/mpeg" });
                                            const blobUrl = URL.createObjectURL(blob);
                                            if (this.ttsObjectUrls) this.ttsObjectUrls.push(blobUrl);
                                            return blobUrl;
                                        }
                                    }
                                } catch (e) {
                                    if (abortSignal.aborted) return null;
                                }
                                return `${data.audio_url}?t=${Date.now()}`;
                            }
                        }
                    } catch (err) {
                        if (abortSignal.aborted) return null;
                        console.warn(`[TTS Queue] Lỗi/timeout tải câu ${idx} (lần ${attempt + 1}):`, err.name || err);
                    } finally {
                        clearTimeout(attemptTimer);
                        abortSignal.removeEventListener("abort", onGlobalAbort);
                    }
                }
                return null;
            })();

            this.prefetchAudios.set(idx, loadPromise);
            return await loadPromise;
        };

        // Hiển thị trạng thái "Đang tạo giọng..." trong lúc chờ Backend tạo câu đầu tiên
        const ttsStartTime = performance.now();
        if (btnElement) {
            btnElement.classList.add("active");
            const span = btnElement.querySelector("span");
            if (span) span.textContent = "Đang tạo giọng...";
            const icon = btnElement.querySelector("i");
            if (icon) icon.className = "fa-solid fa-spinner fa-spin";
        }

        const markSpeakingActiveUI = () => {
            if (this.speechSessionToken !== sessionToken) return;
            if (btnElement) {
                btnElement.classList.add("active");
                const span = btnElement.querySelector("span");
                if (span) span.textContent = "Dừng";
                const icon = btnElement.querySelector("i");
                if (icon) icon.className = "fa-solid fa-stop";
            }
            this.setVoiceBadgeSpeakingState(btnElement, true, voiceInfo.shortName);
        };

        let loggedStart = false;
        let failedSentences = 0;
        let isCurrentAudioReady = false;

        const playNextSentence = async () => {
            if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) {
                return;
            }
            if (this.sentenceIndex >= this.sentenceQueue.length) {
                // Nếu LLM vẫn đang stream câu trả lời -> tạm chờ câu tiếp theo được đẩy vào hàng đợi
                if (!this.isLiveStreamComplete) {
                    this.isWaitingForMoreSentences = true;
                    return;
                }
                if (this.speechSessionToken === sessionToken) {
                    this.stopCurrentSpeech();
                }
                return;
            }

            this.isWaitingForMoreSentences = false;
            isCurrentAudioReady = false;
            const currentIdx = this.sentenceIndex;
            // Chỉ tải ưu tiên câu hiện tại trước (không bắn 3 request cùng lúc gây nghẽn gTTS/Edge-TTS ở câu 0)
            const srcUrl = await getSentenceAudioUrl(currentIdx);

            // Người dùng đã bấm Dừng hoặc sang câu mới -> ngắt ngay
            if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) {
                return;
            }

            if (!srcUrl) {
                failedSentences++;
                if (failedSentences >= 2 || (this.isLiveStreamComplete && currentIdx + 1 >= this.sentenceQueue.length)) {
                    this.stopCurrentSpeech();
                    this.showToast("Không tạo được giọng đọc từ máy chủ. Vui lòng bấm Đọc để thử lại.", "error");
                    return;
                }
                this.sentenceIndex++;
                playNextSentence();
                return;
            }
            failedSentences = 0;
            isCurrentAudioReady = true;

            // Ngay khi câu hiện tại đã có âm thanh, tải ngầm (prefetch) 2 câu kế tiếp để chuyển câu không bị khựng
            if (currentIdx + 1 < this.sentenceQueue.length) {
                getSentenceAudioUrl(currentIdx + 1);
            }
            if (currentIdx + 2 < this.sentenceQueue.length) {
                getSentenceAudioUrl(currentIdx + 2);
            }

            const audio = this.botAudioPlayer;
            this.currentBotAudio = audio;

            let hasAdvanced = false;
            const advanceToNextSentence = () => {
                if (hasAdvanced || this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) return;
                hasAdvanced = true;
                this.sentenceIndex++;
                playNextSentence();
            };

            try {
                audio.onended = null;
                audio.onerror = null;
                audio.onplaying = null;
                audio.pause();
            } catch (e) { }

            audio.muted = false;
            audio.volume = 1;
            audio.src = srcUrl;
            try {
                audio.defaultPlaybackRate = speed;
                audio.playbackRate = speed;
            } catch (e) { }

            audio.onloadedmetadata = () => {
                try {
                    audio.playbackRate = speed;
                } catch (e) { }
            };

            audio.oncanplay = () => {
                try {
                    audio.playbackRate = speed;
                } catch (e) { }
            };

            audio.onplaying = () => {
                if (this.speechSessionToken !== sessionToken) return;
                try {
                    audio.playbackRate = speed;
                } catch (e) { }
                if (!loggedStart) {
                    loggedStart = true;
                    console.log(`[TTS] Bắt đầu phát sau ${Math.round(performance.now() - ttsStartTime)}ms`);
                }
                markSpeakingActiveUI();
            };

            audio.onended = () => {
                advanceToNextSentence();
            };

            audio.onerror = (err) => {
                console.warn(`[TTS Audio error câu ${currentIdx}]`, err);
                advanceToNextSentence();
            };

            const tryPlayAudio = async (isRetry = false) => {
                if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) {
                    try { audio.pause(); audio.currentTime = 0; audio.removeAttribute("src"); } catch (e) { }
                    return;
                }
                try {
                    await audio.play();
                    if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) {
                        try { audio.pause(); audio.currentTime = 0; audio.removeAttribute("src"); } catch (e) { }
                        return;
                    }
                    if (!loggedStart) {
                        loggedStart = true;
                        console.log(`[TTS] Bắt đầu phát sau ${Math.round(performance.now() - ttsStartTime)}ms`);
                    }
                    markSpeakingActiveUI();
                } catch (playErr) {
                    if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) {
                        return;
                    }
                    // Nếu Chrome báo AbortError (do chuyển trạng thái pipeline âm thanh), thử phát lại sau 150ms thay vì im lặng thoát
                    if (!isRetry && playErr && playErr.name === "AbortError") {
                        await new Promise(r => setTimeout(r, 150));
                        if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) return;
                        return await tryPlayAudio(true);
                    }
                    console.warn(`[TTS Play error câu ${currentIdx}]`, playErr);
                    if (playErr && playErr.name === "NotAllowedError") {
                        this.stopCurrentSpeech();
                        this.showToast("Trình duyệt đang chặn tự phát âm thanh. Hãy bấm nút Đọc để nghe.", "info");
                        return;
                    }
                    advanceToNextSentence();
                }
            };

            await tryPlayAudio(false);
        };

        // Khi LLM vừa stream xong câu tiếp theo: tải trước (prefetch) ngay trong lúc câu hiện tại đang đọc,
        // hoặc phát tiếp ngay nếu câu trước đã đọc xong và đang chờ
        this.onLiveSentencesUpdated = () => {
            if (this.speechSessionToken !== sessionToken || !this.isPlayingSentenceQueue) return;
            if (isCurrentAudioReady && this.sentenceIndex + 1 < this.sentenceQueue.length && !this.prefetchAudios.has(this.sentenceIndex + 1)) {
                getSentenceAudioUrl(this.sentenceIndex + 1);
            }
            if (this.isWaitingForMoreSentences) {
                this.isWaitingForMoreSentences = false;
                playNextSentence();
            }
        };

        await playNextSentence();
    }

    // =========================================================================
    // MESSENGER-STYLE VOICE PLAYER & RECORDER
    // =========================================================================
    createMessengerVoicePlayer(msg) {
        const player = document.createElement("div");
        player.className = "messenger-voice-player";

        // Play/Pause button
        const playBtn = document.createElement("button");
        playBtn.type = "button";
        playBtn.className = "voice-bubble-play-btn";
        playBtn.setAttribute("title", "Nghe lại câu hỏi");
        playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';

        // Waveform container
        const waveWrap = document.createElement("div");
        waveWrap.className = "voice-bubble-wave-wrap";

        const waveBars = document.createElement("div");
        waveBars.className = "voice-bubble-wave-bars";

        waveWrap.appendChild(waveBars);

        // Audio Object logic
        const audio = new Audio(msg.audioUrl || "");

        // Dynamic organic soundwave bars to fill the full container width seamlessly
        let barElements = [];
        const renderWaveBars = () => {
            waveBars.innerHTML = "";
            barElements = [];

            // Calculate optimal bar count to fill width (each bar ~2.5-3px + ~2.5px gap = ~5.2px)
            const wrapWidth = waveWrap.clientWidth || 220;
            const barCount = Math.max(22, Math.min(80, Math.floor(wrapWidth / 5.2)));

            // Harmonic speech waveform pattern with realistic peaks and troughs
            const basePeaks = [
                0.28, 0.45, 0.72, 0.95, 0.62, 0.38, 0.58, 0.86, 1.0, 0.74,
                0.52, 0.82, 0.94, 0.64, 0.42, 0.75, 0.88, 0.6, 0.36, 0.54,
                0.8, 0.94, 0.68, 0.46, 0.65, 0.84, 0.98, 0.72, 0.48, 0.32
            ];

            for (let i = 0; i < barCount; i++) {
                const ratio = i / barCount;
                const idx = ratio * basePeaks.length;
                const i0 = Math.floor(idx) % basePeaks.length;
                const i1 = (i0 + 1) % basePeaks.length;
                const frac = idx - Math.floor(idx);
                const rawVal = basePeaks[i0] * (1 - frac) + basePeaks[i1] * frac;

                // Deterministic pseudo-random jitter based on index so it feels organic
                const jitter = ((Math.sin(i * 12.9898) * 43758.5453) % 1) * 0.14;
                const finalVal = Math.max(0.18, Math.min(1.0, rawVal + jitter));
                const heightPct = Math.round(finalVal * 100);

                const bar = document.createElement("span");
                bar.className = "voice-bar";
                bar.style.height = `${heightPct}%`;
                waveBars.appendChild(bar);
                barElements.push(bar);
            }

            // Sync active state if audio is already playing/paused mid-way
            if (audio && audio.currentTime > 0) {
                const dur = audio.duration || totalSec || 1;
                const pct = Math.min(100, Math.max(0, (audio.currentTime / dur) * 100));
                const activeBarIdx = Math.floor((pct / 100) * barElements.length);
                barElements.forEach((bar, idx) => {
                    if (idx <= activeBarIdx) bar.classList.add("active");
                    else bar.classList.remove("active");
                });
            }
        };

        // Initial render
        renderWaveBars();

        // Responsive re-flow whenever container width is determined or window resizes
        if (window.ResizeObserver) {
            let lastW = 0;
            const ro = new ResizeObserver((entries) => {
                for (const entry of entries) {
                    const newW = Math.round(entry.contentRect.width);
                    if (newW > 0 && Math.abs(newW - lastW) >= 10) {
                        lastW = newW;
                        renderWaveBars();
                    }
                }
            });
            ro.observe(waveWrap);
        }

        // Duration label
        const durationLabel = document.createElement("span");
        durationLabel.className = "voice-bubble-duration";
        const totalSec = msg.audioDuration || 0;
        const formatTime = (sec) => {
            const m = Math.floor(sec / 60);
            const s = Math.floor(sec % 60);
            return `${m}:${s < 10 ? '0' : ''}${s}`;
        };
        durationLabel.textContent = totalSec > 0 ? formatTime(totalSec) : "0:00";

        player.appendChild(playBtn);
        player.appendChild(waveWrap);
        player.appendChild(durationLabel);

        // Download link (chỉ hiển thị khi có file âm thanh)
        if (msg.audioUrl) {
            const downloadLink = document.createElement("a");
            downloadLink.className = "voice-bubble-dl-btn";
            downloadLink.href = msg.audioUrl;
            downloadLink.download = `voice_question_${Date.now()}.webm`;
            downloadLink.title = "Tải file âm thanh (.mp3 / .webm)";
            downloadLink.innerHTML = '<i class="fa-solid fa-download"></i>';
            player.appendChild(downloadLink);
        }

        audio.addEventListener("loadedmetadata", () => {
            if (!totalSec && audio.duration && !isNaN(audio.duration) && isFinite(audio.duration)) {
                durationLabel.textContent = formatTime(audio.duration);
            }
        });

        playBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            if (this.activeVoiceAudio && this.activeVoiceAudio !== audio) {
                this.activeVoiceAudio.pause();
                this.activeVoiceAudio.currentTime = 0;
                if (this.activeVoicePlayBtn) {
                    this.activeVoicePlayBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
                    this.activeVoicePlayBtn.classList.remove("playing");
                }
            }

            if (audio.paused) {
                try {
                    audio.playbackRate = parseFloat(this.settings.voiceSpeed || 1.35);
                } catch (e) { }
                audio.play().then(() => {
                    playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
                    playBtn.classList.add("playing");
                    this.activeVoiceAudio = audio;
                    this.activeVoicePlayBtn = playBtn;
                }).catch(err => {
                    console.warn("Audio play error:", err);
                });
            } else {
                audio.pause();
                playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
                playBtn.classList.remove("playing");
            }
        });

        audio.addEventListener("timeupdate", () => {
            const cur = audio.currentTime;
            const dur = audio.duration || totalSec || 1;
            const pct = Math.min(100, Math.max(0, (cur / dur) * 100));
            durationLabel.textContent = formatTime(cur);

            // Highlight wave bars directly to show playback progress on the soundwave
            const activeBarIdx = Math.floor((pct / 100) * barElements.length);
            barElements.forEach((bar, idx) => {
                if (idx <= activeBarIdx) bar.classList.add("active");
                else bar.classList.remove("active");
            });
        });

        audio.addEventListener("ended", () => {
            playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
            playBtn.classList.remove("playing");
            durationLabel.textContent = formatTime(totalSec || audio.duration || 0);
            barElements.forEach(bar => bar.classList.remove("active"));
            if (this.activeVoiceAudio === audio) {
                this.activeVoiceAudio = null;
                this.activeVoicePlayBtn = null;
            }
        });

        // Scrubbing on waveform click
        waveWrap.addEventListener("click", (e) => {
            const rect = waveWrap.getBoundingClientRect();
            const clickX = e.clientX - rect.left;
            const pct = Math.min(1, Math.max(0, clickX / rect.width));
            const dur = audio.duration || totalSec;
            if (dur && !isNaN(dur) && isFinite(dur)) {
                audio.currentTime = pct * dur;
                const activeBarIdx = Math.floor(pct * barElements.length);
                barElements.forEach((bar, idx) => {
                    if (idx <= activeBarIdx) bar.classList.add("active");
                    else bar.classList.remove("active");
                });
            }
        });

        return player;
    }

    // SPEECH RECOGNITION (STT) & MEDIA RECORDER
    initSpeechRecognition() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecordingVoice = false;
        this.recordStartTime = 0;
        this.voiceTranscript = "";
        this.audioStream = null;
        this.activeVoiceAudio = null;
        this.activeVoicePlayBtn = null;

        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRec) {
            this.recognition = new SpeechRec();
            this.recognition.lang = "vi-VN";
            this.recognition.continuous = false;
            this.recognition.interimResults = true;

            this.recognition.onstart = () => {
                // Recording status handled in startVoiceRecording
            };

            this.recognition.onresult = (event) => {
                let liveResult = "";
                for (let i = 0; i < event.results.length; i++) {
                    liveResult += event.results[i][0].transcript;
                }
                this.voiceTranscript = liveResult;
                this.userInput.value = liveResult;
                this.autoGrowTextarea();

                // Dừng ghi âm và gửi khi nhận kết quả hoàn chỉnh
                if (event.results[0] && event.results[0].isFinal) {
                    this.stopVoiceRecordingAndSend(liveResult);
                }
            };

            this.recognition.onerror = (event) => {
                console.warn("Speech recognition warning/error:", event.error);
                if (event.error === "not-allowed" || event.error === "service-not-allowed") {
                    this.showToast("Microphone bị từ chối truy cập.", "error");
                    this.stopVoiceRecordingAndSend();
                }
            };

            this.recognition.onend = () => {
                if (this.isRecordingVoice && this.voiceTranscript) {
                    this.stopVoiceRecordingAndSend(this.voiceTranscript);
                }
            };
        } else {
            console.log("SpeechRecognition not natively supported, MediaRecorder fallback active.");
        }
    }

    async toggleVoiceInput() {
        if (this.isRecordingVoice) {
            // Đang ghi âm -> Bấm lần 2 để dừng và gửi ngay
            await this.stopVoiceRecordingAndSend();
        } else {
            // Bắt đầu ghi âm
            await this.startVoiceRecording();
        }
    }

    async startVoiceRecording() {
        if (this.isRecordingVoice) return;

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            this.showToast("Trình duyệt không hỗ trợ ghi âm Microphone.", "error");
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.audioStream = stream;

            let mimeType = "audio/webm";
            if (!window.MediaRecorder || !MediaRecorder.isTypeSupported("audio/webm")) {
                if (window.MediaRecorder && MediaRecorder.isTypeSupported("audio/mp4")) {
                    mimeType = "audio/mp4";
                } else {
                    mimeType = "";
                }
            }

            this.mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) {
                    this.audioChunks.push(e.data);
                }
            };

            this.recordStartTime = Date.now();
            this.isRecordingVoice = true;
            this.voiceTranscript = "";
            this.mediaRecorder.start();

            if (this.voiceInputBtn) {
                this.voiceInputBtn.classList.add("listening");
                this.voiceInputBtn.title = "Đang ghi âm... Bấm lại mic để gửi ngay!";
            }
            this.showToast("🎙️ Đang ghi âm câu hỏi của bạn... Hãy nói!", "info");

            // Kích hoạt SpeechRecognition song song nếu hỗ trợ
            if (this.recognition) {
                try {
                    this.recognition.start();
                } catch (e) {
                    console.warn("SpeechRec start error:", e);
                }
            }
        } catch (err) {
            console.error("Microphone access error:", err);
            this.showToast("Không thể truy cập Microphone. Vui lòng cấp quyền micro.", "error");
            this.isRecordingVoice = false;
            if (this.voiceInputBtn) this.voiceInputBtn.classList.remove("listening");
        }
    }

    async stopVoiceRecordingAndSend(forcedTranscript = null) {
        if (!this.isRecordingVoice) return;
        this.isRecordingVoice = false;

        if (this.voiceInputBtn) {
            this.voiceInputBtn.classList.remove("listening");
            this.voiceInputBtn.title = "Nhập câu hỏi bằng giọng nói";
        }

        const durationMs = Date.now() - (this.recordStartTime || Date.now());
        const durationSec = Math.max(1, Math.round(durationMs / 1000));

        if (this.recognition) {
            try { this.recognition.stop(); } catch (e) { }
        }

        if (!this.mediaRecorder || this.mediaRecorder.state === "inactive") {
            if (this.audioStream) {
                this.audioStream.getTracks().forEach(t => t.stop());
                this.audioStream = null;
            }
            const textToSend = forcedTranscript || this.voiceTranscript || this.userInput.value.trim();
            if (textToSend) {
                this.handleSubmit({ text: textToSend });
            }
            return;
        }

        const recorder = this.mediaRecorder;
        const mimeType = recorder.mimeType || "audio/webm";

        recorder.onstop = async () => {
            if (this.audioStream) {
                this.audioStream.getTracks().forEach(t => t.stop());
                this.audioStream = null;
            }

            const audioBlob = new Blob(this.audioChunks, { type: mimeType });
            const localBlobUrl = URL.createObjectURL(audioBlob);
            let finalAudioUrl = localBlobUrl;

            // Tải file lên backend /api/upload-voice để lưu trữ vĩnh viễn
            try {
                const formData = new FormData();
                formData.append("audio", audioBlob, `voice_${Date.now()}.webm`);
                const uploadResp = await fetch("/api/upload-voice", {
                    method: "POST",
                    body: formData
                });
                if (uploadResp.ok) {
                    const resData = await uploadResp.json();
                    if (resData.audio_url) {
                        finalAudioUrl = resData.audio_url;
                    }
                }
            } catch (upErr) {
                console.warn("Upload voice audio error, using local blob:", upErr);
            }

            const rawTextToSend = forcedTranscript || this.voiceTranscript || this.userInput.value.trim() || "Câu hỏi bằng giọng nói";
            const textToSend = this.normalizeVoiceTranscript(rawTextToSend);
            this.userInput.value = "";
            this.autoGrowTextarea();

            this.handleSubmit({
                text: textToSend,
                audioUrl: finalAudioUrl,
                audioDuration: durationSec,
                isVoiceMessage: true
            });
        };

        try {
            recorder.stop();
        } catch (e) {
            console.warn("Error stopping media recorder:", e);
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


    // ==============================================================================
    // SCOPE SWITCHER & FILE UPLOAD MANAGEMENT
    // ==============================================================================

    initScopeSelector() {
        if (!this.scopeSelectorBtn || !this.scopePopupCard) return;

        this.scopeSelectorBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            const isOpen = this.scopePopupCard.classList.contains("show");
            document.querySelectorAll(".model-popup-card").forEach(p => p.classList.remove("show"));
            if (isOpen) {
                this.scopePopupCard.classList.remove("show");
            } else {
                this.scopePopupCard.classList.add("show");
            }
        });

        this.scopePopupCard.querySelectorAll(".scope-popup-item").forEach(item => {
            item.addEventListener("click", (e) => {
                e.stopPropagation();
                const scope = item.getAttribute("data-scope");
                this.setScope(scope);
                this.scopePopupCard.classList.remove("show");
            });
        });

        document.addEventListener("click", (e) => {
            if (this.scopePopupCard && !this.scopeSelectorWrapper.contains(e.target)) {
                this.scopePopupCard.classList.remove("show");
            }
        });
    }

    setScope(scope) {
        this.currentScope = scope;
        const labels = {
            "hybrid": "Kết hợp (Hybrid)",
            "user_only": "Chỉ tài liệu",
            "ptit_only": "Chỉ PTIT"
        };
        if (this.scopeBtnLabel) {
            this.scopeBtnLabel.textContent = labels[scope] || scope;
        }
        if (this.scopePopupCard) {
            this.scopePopupCard.querySelectorAll(".scope-popup-item").forEach(item => {
                item.classList.toggle("selected", item.getAttribute("data-scope") === scope);
            });
        }
    }

    initFileUpload() {
        if (!this.uploadFileBtn || !this.fileUploadInput) return;

        this.uploadFileBtn.addEventListener("click", () => {
            this.fileUploadInput.click();
        });

        this.fileUploadInput.addEventListener("change", async (e) => {
            const files = Array.from(e.target.files || []);
            if (files.length === 0) return;
            await this.uploadFiles(files);
            this.fileUploadInput.value = "";
        });
    }

    async uploadFiles(files) {
        const uniqueNames = new Set((this.uploadedFiles || []).map(f => f.filename));
        files.forEach(f => uniqueNames.add(f.name));
        if (uniqueNames.size > 3) {
            this.showToast(`Mỗi phiên chỉ được tải tối đa 3 file. Hiện tại bạn đã có ${this.uploadedFiles.length} file.`, "error");
            return;
        }

        for (const f of files) {
            if (f.size > 5 * 1024 * 1024) {
                this.showToast(`File '${f.name}' vượt quá 5MB. Vui lòng chọn file nhẹ hơn.`, "error");
                return;
            }
            const ext = f.name.split(".").pop().toLowerCase();
            if (!["pdf", "docx", "txt", "md"].includes(ext)) {
                this.showToast(`File '${f.name}' không hợp lệ. Chỉ chấp nhận .pdf, .docx, .txt, .md.`, "error");
                return;
            }
        }

        if (this.uploadedFilesBar) this.uploadedFilesBar.style.display = "flex";
        if (this.uploadStatusIndicator) {
            this.uploadStatusIndicator.style.display = "inline-flex";
            this.uploadStatusText.textContent = `Đang phân tích & tạo vector cho ${files.length} file...`;
        }

        const formData = new FormData();
        formData.append("session_id", this.currentSessionId);
        if (this.settings.apiKey) {
            formData.append("api_key", this.settings.apiKey);
        }
        for (const f of files) {
            formData.append("files", f);
        }

        try {
            const resp = await fetch("/api/upload", {
                method: "POST",
                body: formData
            });
            const data = await resp.json();

            if (!resp.ok || data.error) {
                this.showToast(data.error || "Lỗi tải lên tài liệu.", "error");
                return;
            }

            this.uploadedFiles = data.files || [];
            const prevPending = new Set(this.pendingAttachedFiles || []);
            files.forEach(f => prevPending.add(f.name));
            this.pendingAttachedFiles = Array.from(prevPending);
            this.renderUploadedFiles(this.uploadedFiles, true);
            this.setScope("hybrid");
            this.showToast(data.message || "Tải lên tài liệu thành công!", "success");
        } catch (err) {
            this.showToast("Không thể kết nối đến máy chủ khi tải tài liệu.", "error");
        } finally {
            if (this.uploadStatusIndicator) {
                this.uploadStatusIndicator.style.display = "none";
            }
        }
    }

    async fetchSessionDocs(sessionId) {
        if (!sessionId) return;
        try {
            const resp = await fetch(`/api/session-docs?session_id=${encodeURIComponent(sessionId)}`);
            if (resp.ok) {
                const data = await resp.json();
                this.uploadedFiles = data.files || [];
                this.renderUploadedFiles(this.uploadedFiles);
                if (this.uploadedFiles.length > 0) {
                    if (this.currentScope === "ptit_only") {
                        this.setScope("hybrid");
                    }
                } else {
                    this.setScope("ptit_only");
                }
            }
        } catch (e) {
            console.error("Lỗi lấy danh sách tài liệu phiên:", e);
        }
    }

    renderUploadedFiles(files, showBar = false) {
        if (!this.uploadedFilesList || !this.uploadedFilesBar) return;
        this.uploadedFilesList.innerHTML = "";

        const count = files ? files.length : 0;
        if (this.navDocsCountText) {
            this.navDocsCountText.textContent = `Tài liệu (${count})`;
        }

        if (!files || files.length === 0) {
            this.uploadedFilesBar.style.display = "none";
            if (this.scopeDocsCountBadge) this.scopeDocsCountBadge.textContent = "0 file";
            if (this.docsSidePanel && this.docsSidePanel.classList.contains("open")) {
                this.renderSidePanelDocsList();
            }
            return;
        }

        if (showBar) {
            this.uploadedFilesBar.style.display = "flex";
        } else {
            this.uploadedFilesBar.style.display = "none";
        }
        if (this.scopeDocsCountBadge) {
            this.scopeDocsCountBadge.textContent = `${files.length} file`;
        }
        if (this.docsSidePanel && this.docsSidePanel.classList.contains("open")) {
            this.renderSidePanelDocsList();
        }

        files.forEach(f => {
            const badge = document.createElement("div");
            badge.className = "file-badge";
            const ext = f.filename.split(".").pop().toLowerCase();
            let iconClass = "fa-file-lines";
            if (ext === "pdf") iconClass = "fa-file-pdf";
            else if (ext === "docx") iconClass = "fa-file-word";

            badge.innerHTML = `
                <i class="fa-solid ${iconClass} file-badge-icon"></i>
                <span class="file-badge-name" title="${f.filename}">${f.filename}</span>
                <span class="file-badge-meta">(${f.chunks_count || 1} chunks)</span>
                <button type="button" class="file-badge-remove" title="Xóa tài liệu này"><i class="fa-solid fa-xmark"></i></button>
            `;

            const removeBtn = badge.querySelector(".file-badge-remove");
            removeBtn.addEventListener("click", async (e) => {
                e.stopPropagation();
                await this.deleteSessionDoc(f.filename);
            });

            this.uploadedFilesList.appendChild(badge);
        });
    }

    openSidePanel() {
        if (!this.docsSidePanel) return;
        this.renderSidePanelDocsList();
        this.docsSidePanel.classList.add("open");
        if (this.docsSidePanelBackdrop) this.docsSidePanelBackdrop.classList.add("active");
    }

    closeSidePanel() {
        if (!this.docsSidePanel) return;
        this.docsSidePanel.classList.remove("open");
        if (this.docsSidePanelBackdrop) this.docsSidePanelBackdrop.classList.remove("active");
    }

    openUploadedDocsModal() {
        this.openSidePanel();
    }

    closeUploadedDocsModal() {
        this.closeSidePanel();
    }

    renderModalDocsList() {
        this.renderSidePanelDocsList();
    }

    renderSidePanelDocsList() {
        if (!this.sidePanelDocsList) return;
        this.sidePanelDocsList.innerHTML = "";

        const files = this.uploadedFiles || [];
        if (this.sidePanelDocsCountBadge) {
            this.sidePanelDocsCountBadge.textContent = `${files.length}/3 file`;
        }

        if (files.length === 0) {
            this.sidePanelDocsList.innerHTML = `
                <div class="side-panel-empty-docs">
                    <i class="fa-solid fa-folder-open"></i>
                    <h4>Chưa có tài liệu nào</h4>
                    <p>Hãy tải lên tài liệu môn học, đề cương (.pdf, .docx, .txt, .md) để hỏi đáp trực tiếp cùng AI.</p>
                </div>
            `;
            return;
        }

        files.forEach(f => {
            const item = document.createElement("div");
            item.className = "side-panel-doc-item";

            const ext = f.filename.split(".").pop().toLowerCase();
            let iconClass = "fa-file-lines";
            if (ext === "pdf") iconClass = "fa-file-pdf";
            else if (ext === "docx") iconClass = "fa-file-word";

            const dateStr = f.uploaded_at ? new Date(f.uploaded_at * 1000).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) : "";

            item.innerHTML = `
                <div class="side-panel-doc-left">
                    <div class="side-panel-doc-icon"><i class="fa-solid ${iconClass}"></i></div>
                    <div class="side-panel-doc-details">
                        <span class="side-panel-doc-name" title="${this.escapeHtml(f.filename)}">${this.escapeHtml(f.filename)}</span>
                        <div class="side-panel-doc-submeta">
                            <span><i class="fa-solid fa-layer-group"></i> ${f.chunks_count || 1} chunks</span>
                            ${dateStr ? `<span><i class="fa-regular fa-clock"></i> ${dateStr}</span>` : ""}
                        </div>
                    </div>
                </div>
                <div class="side-panel-doc-actions">
                    <button type="button" class="icon-btn btn-delete-doc" title="Xóa tài liệu này">
                        <i class="fa-regular fa-trash-can"></i>
                    </button>
                </div>
            `;

            const delBtn = item.querySelector(".btn-delete-doc");
            delBtn.addEventListener("click", async () => {
                await this.deleteSessionDoc(f.filename);
                this.renderSidePanelDocsList();
            });

            this.sidePanelDocsList.appendChild(item);
        });
    }

    async clearAllSessionDocs() {
        if (!this.uploadedFiles || this.uploadedFiles.length === 0) {
            this.showToast("Không có tài liệu nào để xóa.", "info");
            return;
        }
        try {
            const resp = await fetch("/api/session-docs", {
                method: "DELETE",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ session_id: this.currentSessionId })
            });
            if (resp.ok) {
                this.uploadedFiles = [];
                this.pendingAttachedFiles = [];
                this.renderUploadedFiles([], false);
                this.renderSidePanelDocsList();
                this.setScope("ptit_only");
                this.showToast("Đã xóa tất cả tài liệu trong phiên.", "success");
            }
        } catch (e) {
            this.showToast("Lỗi khi xóa tài liệu.", "error");
        }
    }

    async deleteSessionDoc(filename) {
        try {
            const resp = await fetch("/api/session-docs", {
                method: "DELETE",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    session_id: this.currentSessionId,
                    filename: filename
                })
            });
            if (resp.ok) {
                const data = await resp.json();
                this.uploadedFiles = data.files || [];
                if (this.pendingAttachedFiles) {
                    this.pendingAttachedFiles = this.pendingAttachedFiles.filter(fn => fn !== filename);
                }
                this.renderUploadedFiles(this.uploadedFiles, false);
                this.renderSidePanelDocsList();
                if (this.uploadedFiles.length === 0) {
                    this.setScope("ptit_only");
                }
                this.showToast(`Đã xóa tài liệu '${filename}'.`, "info");
            }
        } catch (e) {
            this.showToast("Lỗi khi xóa tài liệu.", "error");
        }
    }
}

// Instantiate on DOM Loaded
document.addEventListener("DOMContentLoaded", () => {
    window.ptitApp = new PTITChatApp();
});
