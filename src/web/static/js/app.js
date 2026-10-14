// Global State
let activeDocumentId = null;
window.activeDocumentId = null;

// API Base URL (defaults to Render API if hosted externally like Vercel)
const API_BASE_URL = window.location.hostname.includes('localhost') || window.location.hostname.includes('127.0.0.1') || window.location.hostname.includes('onrender.com')
    ? ''
    : 'https://macro-project-a63n.onrender.com';

// DOM Elements
const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('file-input');
const uploadProgress = document.getElementById('upload-progress');
const documentsList = document.getElementById('documents-list');
const emptyState = document.getElementById('empty-state');
const documentWorkspace = document.getElementById('document-workspace');
const viewerTitle = document.getElementById('viewer-title');
const viewerMeta = document.getElementById('viewer-meta');
const viewerContent = document.getElementById('viewer-content');
const chatContainer = document.getElementById('chat-container');
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const btnSummarize = document.getElementById('btn-summarize');
// Quiz Maker Elements
const quizQuestionCount = document.getElementById('quiz-question-count');
const quizDifficulty = document.getElementById('quiz-difficulty');
const btnGenerateQuiz = document.getElementById('btn-generate-quiz');
const quizStatus = document.getElementById('quiz-status');
const quizResults = document.getElementById('quiz-results');

// Toast Notification Helper
window.showToast = function(message, type = 'info', duration = 3500) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let iconClass = 'fa-circle-info';
    if (type === 'success') iconClass = 'fa-circle-check';
    if (type === 'error') iconClass = 'fa-circle-exclamation';

    toast.innerHTML = `
        <i class="fa-solid ${iconClass} toast-icon"></i>
        <div class="toast-message">${escapeHTML(message)}</div>
        <button type="button" class="toast-close" aria-label="Close notification"><i class="fa-solid fa-xmark"></i></button>
        <div class="toast-progress" style="transition: width ${duration}ms linear; width: 100%;"></div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        const prog = toast.querySelector('.toast-progress');
        if (prog) prog.style.width = '0%';
    }, 20);

    const closeToast = () => {
        if (toast.classList.contains('toast-hiding')) return;
        toast.classList.add('toast-hiding');
        setTimeout(() => toast.remove(), 250);
    };

    const closeBtn = toast.querySelector('.toast-close');
    if (closeBtn) closeBtn.addEventListener('click', closeToast);

    const timer = setTimeout(closeToast, duration);
    toast.addEventListener('mouseenter', () => clearTimeout(timer));
};

// Theme Management
function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    try {
        localStorage.setItem('theme', theme);
    } catch (e) {}
}

function setupTheme() {
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = savedTheme || (systemPrefersDark ? 'dark' : 'light');
    
    applyTheme(initialTheme);

    const themeToggleBtn = document.getElementById('theme-toggle');
    if (themeToggleBtn && !themeToggleBtn.dataset.bound) {
        themeToggleBtn.dataset.bound = 'true';
        themeToggleBtn.addEventListener('click', (e) => {
            e.preventDefault();
            const currentTheme = document.documentElement.dataset.theme || document.documentElement.getAttribute('data-theme') || 'light';
            const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
            applyTheme(nextTheme);
        });
    }

    if (window.matchMedia && !window._themeMediaBound) {
        window._themeMediaBound = true;
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (!localStorage.getItem('theme')) {
                applyTheme(e.matches ? 'dark' : 'light');
            }
        });
    }
}

// Initialize theme immediately to prevent flashing
setupTheme();

// Workspace Tabs Management
function setupWorkspaceTabs() {
    const tabBtnDoc = document.getElementById('tab-btn-document');
    const tabBtnQuiz = document.getElementById('tab-btn-quiz');
    const tabBtnNotes = document.getElementById('tab-btn-notes');
    const panelDoc = document.getElementById('tab-panel-document');
    const panelQuiz = document.getElementById('tab-panel-quiz');
    const panelNotes = document.getElementById('tab-panel-notes');

    function switchWorkspaceTab(activeBtn, activePanel) {
        [tabBtnDoc, tabBtnQuiz, tabBtnNotes].forEach(b => {
            if (b) {
                b.classList.toggle('active', b === activeBtn);
                b.setAttribute('aria-selected', b === activeBtn ? 'true' : 'false');
            }
        });
        [panelDoc, panelQuiz, panelNotes].forEach(p => {
            if (p) {
                p.classList.toggle('hidden', p !== activePanel);
            }
        });
    }

    if (tabBtnDoc && panelDoc) {
        tabBtnDoc.addEventListener('click', () => switchWorkspaceTab(tabBtnDoc, panelDoc));
    }

    if (tabBtnQuiz && panelQuiz) {
        tabBtnQuiz.addEventListener('click', () => switchWorkspaceTab(tabBtnQuiz, panelQuiz));
    }

    if (tabBtnNotes && panelNotes) {
        tabBtnNotes.addEventListener('click', () => {
            switchWorkspaceTab(tabBtnNotes, panelNotes);
        });
    }
}

// Collapsible Sidebar Management
function setupSidebarToggle() {
    const sidebar = document.querySelector('.sidebar');
    const toggleBtn = document.getElementById('sidebar-toggle');

    if (!sidebar || !toggleBtn) return;

    // Restore saved state
    if (localStorage.getItem('sidebar_collapsed') === 'true') {
        sidebar.classList.add('collapsed');
    }

    toggleBtn.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
        localStorage.setItem('sidebar_collapsed', sidebar.classList.contains('collapsed'));
    });
}

// Resizable AI Assistant Panel
function setupPanelResizer() {
    const resizer = document.getElementById('ai-panel-resizer');
    const aiPanel = document.querySelector('.ai-assistant');

    if (!resizer || !aiPanel) return;

    // Restore saved width
    const savedWidth = localStorage.getItem('ai_panel_width');
    if (savedWidth && window.innerWidth > 900) {
        aiPanel.style.width = `${Math.min(Math.max(parseInt(savedWidth), 280), 650)}px`;
    }

    let isResizing = false;

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        resizer.classList.add('is-resizing');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        const newWidth = window.innerWidth - e.clientX;
        if (newWidth >= 280 && newWidth <= 650) {
            aiPanel.style.width = `${newWidth}px`;
        }
    });

    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            resizer.classList.remove('is-resizing');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            localStorage.setItem('ai_panel_width', parseInt(aiPanel.style.width));
        }
    });
}

// Command Palette (Ctrl+K)
function setupCommandPalette() {
    const modal = document.getElementById('command-palette-modal');
    const input = document.getElementById('palette-search-input');
    const resultsList = document.getElementById('palette-results-list');
    const triggerBtn = document.getElementById('btn-cmd-palette-trigger');

    if (!modal || !input || !resultsList) return;

    let selectedIndex = 0;
    let currentItems = [];

    const getAvailableCommands = () => [
        {
            type: 'action',
            title: 'Toggle Theme (Dark / Light)',
            icon: 'fa-circle-half-stroke',
            hotkey: 'Ctrl+D',
            run: () => {
                const themeBtn = document.getElementById('theme-toggle');
                if (themeBtn) themeBtn.click();
            }
        },
        {
            type: 'action',
            title: 'Toggle Left Sidebar',
            icon: 'fa-bars-staggered',
            hotkey: 'Ctrl+\\',
            run: () => {
                const sidebarBtn = document.getElementById('sidebar-toggle');
                if (sidebarBtn) sidebarBtn.click();
            }
        },
        {
            type: 'action',
            title: 'Switch to Quiz Maker',
            icon: 'fa-graduation-cap',
            hotkey: '',
            run: () => {
                const tabQuiz = document.getElementById('tab-btn-quiz');
                if (tabQuiz) tabQuiz.click();
            }
        },
        {
            type: 'action',
            title: 'Summarize Document',
            icon: 'fa-bolt',
            hotkey: '',
            run: () => {
                if (btnSummarize) btnSummarize.click();
            }
        },
        {
            type: 'action',
            title: 'Make Study Notes',
            icon: 'fa-pen-nib',
            hotkey: '',
            run: () => {
                const btnNotes = document.getElementById('btn-make-notes');
                if (btnNotes) btnNotes.click();
            }
        },
        {
            type: 'action',
            title: 'Clear Chat History',
            icon: 'fa-trash-can',
            hotkey: '',
            run: () => {
                const btnClear = document.getElementById('btn-clear-chat');
                if (btnClear) btnClear.click();
            }
        },
        {
            type: 'action',
            title: 'Upload Document',
            icon: 'fa-cloud-arrow-up',
            hotkey: '',
            run: () => {
                if (fileInput) fileInput.click();
            }
        }
    ];

    const openPalette = () => {
        modal.classList.remove('hidden');
        input.value = '';
        selectedIndex = 0;
        renderPaletteResults('');
        input.focus();
    };

    const closePalette = () => {
        modal.classList.add('hidden');
    };

    const renderPaletteResults = (query) => {
        const q = (query || '').toLowerCase().trim();
        resultsList.innerHTML = '';
        currentItems = [];

        // Actions
        const actions = getAvailableCommands().filter(cmd =>
            !q || cmd.title.toLowerCase().includes(q)
        );

        // Documents
        const docs = (window.allDocuments || []).filter(doc =>
            !q || (doc.filename || '').toLowerCase().includes(q)
        ).map(doc => ({
            type: 'document',
            title: doc.filename,
            icon: 'fa-file-lines',
            hotkey: `${(doc.file_size / 1024).toFixed(1)} KB`,
            run: () => {
                openDocument(doc.id, doc.filename, (doc.file_size / 1024).toFixed(1));
            }
        }));

        currentItems = [...actions, ...docs];

        if (currentItems.length === 0) {
            resultsList.innerHTML = `
                <div style="padding:var(--space-4);text-align:center;color:var(--text-muted);font-size:var(--text-xs);">
                    No matching commands or documents found
                </div>
            `;
            return;
        }

        currentItems.forEach((item, index) => {
            const itemEl = document.createElement('div');
            itemEl.className = `palette-item ${index === selectedIndex ? 'active' : ''}`;
            itemEl.innerHTML = `
                <div class="palette-item-left">
                    <div class="palette-item-icon"><i class="fa-solid ${item.icon}"></i></div>
                    <span class="palette-item-title">${escapeHTML(item.title)}</span>
                </div>
                ${item.hotkey ? `<kbd class="kbd-badge">${escapeHTML(item.hotkey)}</kbd>` : ''}
            `;

            itemEl.addEventListener('click', () => {
                closePalette();
                item.run();
            });

            resultsList.appendChild(itemEl);
        });
    };

    input.addEventListener('input', () => {
        selectedIndex = 0;
        renderPaletteResults(input.value);
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (currentItems.length > 0) {
                selectedIndex = (selectedIndex + 1) % currentItems.length;
                updateActiveSelection();
            }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (currentItems.length > 0) {
                selectedIndex = (selectedIndex - 1 + currentItems.length) % currentItems.length;
                updateActiveSelection();
            }
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (currentItems[selectedIndex]) {
                closePalette();
                currentItems[selectedIndex].run();
            }
        } else if (e.key === 'Escape') {
            closePalette();
        }
    });

    const updateActiveSelection = () => {
        const items = resultsList.querySelectorAll('.palette-item');
        items.forEach((el, idx) => {
            el.classList.toggle('active', idx === selectedIndex);
            if (idx === selectedIndex) {
                el.scrollIntoView({ block: 'nearest' });
            }
        });
    };

    if (triggerBtn) {
        triggerBtn.addEventListener('click', openPalette);
    }

    modal.addEventListener('click', (e) => {
        if (e.target === modal) closePalette();
    });

    window.openCommandPalette = openPalette;
    window.closeCommandPalette = closePalette;
}

// Global Keyboard Shortcuts
function setupGlobalShortcuts() {
    const shortcutsModal = document.getElementById('shortcuts-help-modal');
    const shortcutsCloseBtn = document.getElementById('shortcuts-btn-close');

    const openShortcuts = () => {
        if (shortcutsModal) shortcutsModal.classList.remove('hidden');
    };

    const closeShortcuts = () => {
        if (shortcutsModal) shortcutsModal.classList.add('hidden');
    };

    if (shortcutsCloseBtn) {
        shortcutsCloseBtn.addEventListener('click', closeShortcuts);
    }

    if (shortcutsModal) {
        shortcutsModal.addEventListener('click', (e) => {
            if (e.target === shortcutsModal) closeShortcuts();
        });
    }

    window.openShortcutsModal = openShortcuts;
    window.closeShortcutsModal = closeShortcuts;

    document.addEventListener('keydown', (e) => {
        const isEditing = document.activeElement && ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName);

        // Ctrl+K or Cmd+K: Command Palette
        if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
            e.preventDefault();
            if (window.openCommandPalette) window.openCommandPalette();
            return;
        }

        // Ctrl+\: Toggle Sidebar
        if ((e.ctrlKey || e.metaKey) && e.key === '\\') {
            e.preventDefault();
            const sidebarBtn = document.getElementById('sidebar-toggle');
            if (sidebarBtn) sidebarBtn.click();
            return;
        }

        // Ctrl+D: Toggle Theme
        if ((e.ctrlKey || e.metaKey) && (e.key === 'd' || e.key === 'D')) {
            e.preventDefault();
            const themeBtn = document.getElementById('theme-toggle');
            if (themeBtn) themeBtn.click();
            return;
        }

        // Escape: Close any open modal
        if (e.key === 'Escape') {
            if (window.closeCommandPalette) window.closeCommandPalette();
            closeShortcuts();
            return;
        }

        // '?' when not typing in an input: Show shortcuts modal
        if (e.key === '?' && !isEditing && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            openShortcuts();
        }
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupTheme();
    setupWorkspaceTabs();
    setupSidebarToggle();
    setupPanelResizer();
    setupLibrarySearch();
    setupDocSearch();
    setupDocumentViewer();
    loadDocuments();
    setupUpload();
    setupChat();
    setupQuiz();
    setupCommandPalette();
    setupGlobalShortcuts();
});

// --- API Calls ---
async function fetchDocuments() {
    const res = await fetch(`${API_BASE_URL}/api/documents`);
    const data = await res.json();
    return data.documents;
}

async function fetchDocumentContent(docId) {
    const res = await fetch(`${API_BASE_URL}/api/documents/${docId}/content`);
    if (!res.ok) throw new Error("Failed to load document content");
    return await res.json();
}

async function deleteDocument(docId) {
    await fetch(`${API_BASE_URL}/api/documents/${docId}`, { method: 'DELETE' });
    if (activeDocumentId === docId) {
        closeDocument();
    }
    loadDocuments();
}

async function askQuestion(query, docId) {
    const res = await fetch(`${API_BASE_URL}/api/qa`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query, mode: "hybrid", top_k: 40, document_id: docId })
    });
    return await res.json();
}

async function summarizeDocument(docId) {
    const res = await fetch(`${API_BASE_URL}/api/documents/${docId}/summarize`, {
        method: 'POST'
    });
    return await res.json();
}

// Global Document Cache for Real-Time Search
window.allDocuments = [];

// Helper: Determine specific file type icon and color class
function getFileTypeIconInfo(filename, fileType) {
    const ext = (filename || '').split('.').pop().toLowerCase();
    if (ext === 'pdf' || fileType === 'pdf') {
        return { icon: 'fa-file-pdf', colorClass: 'doc-icon-pdf' };
    }
    if (['doc', 'docx'].includes(ext)) {
        return { icon: 'fa-file-word', colorClass: 'doc-icon-word' };
    }
    if (['txt', 'md', 'markdown'].includes(ext)) {
        return { icon: 'fa-file-lines', colorClass: 'doc-icon-txt' };
    }
    if (['csv', 'xlsx', 'xls'].includes(ext)) {
        return { icon: 'fa-file-excel', colorClass: 'doc-icon-txt' };
    }
    if (['json', 'py', 'js', 'html', 'css', 'sql'].includes(ext)) {
        return { icon: 'fa-file-code', colorClass: 'doc-icon-code' };
    }
    return { icon: 'fa-file-lines', colorClass: 'doc-icon-default' };
}

// --- UI Logic ---
async function loadDocuments() {
    // Show Skeleton Shimmer while loading
    if (documentsList && window.allDocuments.length === 0) {
        documentsList.innerHTML = `
            <li class="doc-skeleton-item shimmer"></li>
            <li class="doc-skeleton-item shimmer"></li>
            <li class="doc-skeleton-item shimmer"></li>
            <li class="doc-skeleton-item shimmer"></li>
        `;
    }
    try {
        const docs = await fetchDocuments();
        window.allDocuments = docs || [];
        renderDocumentsList(window.allDocuments);
    } catch (err) {
        console.error("Error loading documents:", err);
        if (documentsList) {
            documentsList.innerHTML = '<li class="library-empty"><p style="color:var(--danger)">Failed to load library</p></li>';
        }
    }
}

function renderDocumentsList(docs) {
    if (!documentsList) return;
    documentsList.innerHTML = '';
    
    // Update count badge
    const countBadge = document.getElementById('documents-count');
    if (countBadge) {
        countBadge.textContent = docs ? docs.length : 0;
    }

    const emptyLibraryEl = document.getElementById('library-empty-state');

    if (!docs || docs.length === 0) {
        if (emptyLibraryEl) emptyLibraryEl.classList.remove('hidden');
        return;
    }

    if (emptyLibraryEl) emptyLibraryEl.classList.add('hidden');

    docs.forEach(doc => {
        const li = document.createElement('li');
        li.className = `doc-item ${doc.id === activeDocumentId ? 'active' : ''}`;
        
        const sizeKB = (doc.file_size / 1024).toFixed(1);
        const iconInfo = getFileTypeIconInfo(doc.filename, doc.file_type);
        
        li.innerHTML = `
            <div class="doc-title" title="${escapeHTML(doc.filename)}">
                <i class="fa-solid ${iconInfo.icon} ${iconInfo.colorClass}"></i> 
                <span>${escapeHTML(doc.filename)}</span>
            </div>
            <div class="doc-meta">
                <span>${sizeKB} KB</span>
                <button class="delete-btn" title="Delete document" aria-label="Delete ${escapeHTML(doc.filename)}">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            </div>
        `;
        
        li.addEventListener('click', (e) => {
            if (e.target.closest('.delete-btn')) {
                e.stopPropagation();
                if (confirm(`Delete "${doc.filename}" from library?`)) {
                    deleteDocument(doc.id);
                }
            } else {
                openDocument(doc.id, doc.filename, sizeKB);
            }
        });
        
        documentsList.appendChild(li);
    });
}

// Real-Time Library Search Filtering
function setupLibrarySearch() {
    const searchInput = document.getElementById('library-search-input');
    const searchClear = document.getElementById('library-search-clear');

    if (!searchInput) return;

    const handleLibrarySearch = debounce((query) => {
        if (!query) {
            renderDocumentsList(window.allDocuments);
            return;
        }

        const normQuery = (query || '').normalize('NFKC').toLowerCase();
        const filtered = window.allDocuments.filter(doc => 
            (doc.filename || '').normalize('NFKC').toLowerCase().includes(normQuery)
        );
        renderDocumentsList(filtered);
    }, 120);

    searchInput.addEventListener('input', () => {
        const query = searchInput.value.trim();
        
        if (searchClear) {
            if (query) {
                searchClear.classList.remove('hidden');
            } else {
                searchClear.classList.add('hidden');
            }
        }

        handleLibrarySearch(query);
    });

    if (searchClear) {
        searchClear.addEventListener('click', () => {
            searchInput.value = '';
            searchClear.classList.add('hidden');
            renderDocumentsList(window.allDocuments);
            searchInput.focus();
        });
    }
}

// In-Document Text Search
function setupDocSearch() {
    const searchInput = document.getElementById('doc-search-input');
    const searchClear = document.getElementById('doc-search-clear');

    if (!searchInput) return;

    const handleDocSearch = debounce((query) => {
        renderDocumentContent(window.currentDocChunks, query);
    }, 150);

    searchInput.addEventListener('input', () => {
        const query = searchInput.value.trim();
        if (searchClear) {
            if (query) {
                searchClear.classList.remove('hidden');
            } else {
                searchClear.classList.add('hidden');
            }
        }
        handleDocSearch(query);
    });

    if (searchClear) {
        searchClear.addEventListener('click', () => {
            searchInput.value = '';
            searchClear.classList.add('hidden');
            renderDocumentContent(window.currentDocChunks, '');
            searchInput.focus();
        });
    }
}

// Document Viewer Controls (Reading Progress, Scroll to Top, Copy ID)
function setupDocumentViewer() {
    const copyIdBtn = document.getElementById('copy-doc-id');
    const copyIdText = document.getElementById('copy-doc-id-text');
    const progressBar = document.getElementById('reading-progress-bar');
    const scrollTopBtn = document.getElementById('btn-scroll-top');

    // Copy Doc ID handler
    if (copyIdBtn) {
        copyIdBtn.addEventListener('click', () => {
            if (!activeDocumentId) return;
            navigator.clipboard.writeText(activeDocumentId).then(() => {
                copyIdBtn.classList.add('copied');
                if (copyIdText) copyIdText.textContent = 'Copied!';
                setTimeout(() => {
                    copyIdBtn.classList.remove('copied');
                    if (copyIdText) copyIdText.textContent = 'Copy ID';
                }, 2000);
            });
        });
    }

    // Smooth, 60fps rAF-throttled scroll progress & Scroll-to-top handler
    if (viewerContent) {
        let isTicking = false;
        viewerContent.addEventListener('scroll', () => {
            if (!isTicking) {
                window.requestAnimationFrame(() => {
                    const scrollTop = viewerContent.scrollTop;
                    const scrollHeight = viewerContent.scrollHeight - viewerContent.clientHeight;
                    
                    if (scrollHeight > 0) {
                        const progress = Math.min(Math.max((scrollTop / scrollHeight) * 100, 0), 100);
                        if (progressBar) {
                            progressBar.style.width = `${progress}%`;
                        }
                    } else if (progressBar) {
                        progressBar.style.width = '0%';
                    }

                    // Scroll-to-top button visibility
                    if (scrollTopBtn) {
                        if (scrollTop > 180) {
                            scrollTopBtn.classList.remove('hidden');
                        } else {
                            scrollTopBtn.classList.add('hidden');
                        }
                    }
                    isTicking = false;
                });
                isTicking = true;
            }
        }, { passive: true });
    }

    // Scroll-to-top button click
    if (scrollTopBtn && viewerContent) {
        scrollTopBtn.addEventListener('click', () => {
            viewerContent.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }
}

async function openDocument(docId, filename, sizeKB) {
    activeDocumentId = docId;
    window.activeDocumentId = docId;
    window.activeDocumentFilename = filename;
    
    // Reset in-document search state
    const docSearchInput = document.getElementById('doc-search-input');
    const docSearchClear = document.getElementById('doc-search-clear');
    const docSearchCount = document.getElementById('doc-search-count');
    if (docSearchInput) docSearchInput.value = '';
    if (docSearchClear) docSearchClear.classList.add('hidden');
    if (docSearchCount) docSearchCount.classList.add('hidden');

    // Reset reading progress bar
    const progressBar = document.getElementById('reading-progress-bar');
    if (progressBar) progressBar.style.width = '0%';
    
    // Update Sidebar Selection
    document.querySelectorAll('.doc-item').forEach(el => el.classList.remove('active'));
    // We re-render or just find it. For now, re-render is fine, but we can rely on DOM.
    loadDocuments();
    
    // Toggle UI States
    emptyState.classList.add('hidden');
    documentWorkspace.classList.remove('hidden');

    // Auto-activate Document tab if previously on Quiz tab
    const tabBtnDoc = document.getElementById('tab-btn-document');
    if (tabBtnDoc && !tabBtnDoc.classList.contains('active')) {
        tabBtnDoc.click();
    }
    
    // Set Header
    viewerTitle.textContent = filename;
    viewerMeta.textContent = `Document ID: ${docId.substring(0, 8)}... • ${sizeKB} KB`;
    
    // Loading State for Content
    viewerContent.innerHTML = `
        <div class="skeleton-loader">
            <div class="line"></div>
            <div class="line"></div>
            <div class="line"></div>
            <div class="line"></div>
            <div class="line"></div>
        </div>
    `;
    
    // Reset Chat
    chatContainer.innerHTML = `
        <div class="chat-message ai-message">
            <div class="avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="message-content" dir="auto">Hello! I'm ready to answer any questions about <strong>${filename}</strong>.</div>
        </div>
    `;
    
    // Fetch and render content
    try {
        const data = await fetchDocumentContent(docId);
        window.currentDocWarning = data.warning || null;

        // Show detected language badge next to Document ID
        const langBadge = document.getElementById('viewer-lang-badge');
        const langText = document.getElementById('viewer-lang-text');
        const langCode = (data.language || (data.document && data.document.language) || 'en').toUpperCase();
        if (langBadge && langText) {
            langText.textContent = langCode;
            langBadge.classList.remove('hidden');
            langBadge.title = `Detected Language: ${langCode}`;
        }

        renderDocumentContent(data.chunks, '', data.warning);
    } catch (err) {
        viewerContent.innerHTML = `<p style="color: #ef4444;">Error loading document content.</p>`;
    }
}

function closeDocument() {
    activeDocumentId = null;
    window.activeDocumentId = null;
    window.activeDocumentFilename = null;
    window.currentDocWarning = null;
    const langBadge = document.getElementById('viewer-lang-badge');
    if (langBadge) langBadge.classList.add('hidden');
    emptyState.classList.remove('hidden');
    documentWorkspace.classList.add('hidden');
}

// Global cache of current document chunks for in-document search
window.currentDocChunks = [];
window.currentDocWarning = null;

function renderDocumentContent(chunks, searchQuery = '', warning = null) {
    window.currentDocChunks = chunks || [];
    const activeWarning = warning || window.currentDocWarning;
    viewerContent.innerHTML = '';
    
    if (activeWarning) {
        const warnDiv = document.createElement('div');
        warnDiv.className = 'doc-warning-banner';
        warnDiv.style.cssText = 'background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.35); border-radius: var(--radius-md, 8px); padding: 12px 16px; margin: 12px auto 20px auto; max-width: 800px; display: flex; align-items: center; gap: 12px; color: #f59e0b;';
        warnDiv.innerHTML = `
            <i class="fa-solid fa-triangle-exclamation" style="font-size: 1.25rem; flex-shrink: 0;"></i>
            <span style="font-size: 0.9rem; font-weight: 500;">${escapeHTML(activeWarning)}</span>
        `;
        viewerContent.appendChild(warnDiv);
    }
    
    if (!chunks || chunks.length === 0) {
        const emptyDiv = document.createElement('div');
        emptyDiv.className = 'empty-state-card glass-panel';
        emptyDiv.style.cssText = 'margin: var(--space-8) auto; max-width: 480px; text-align: center;';
        if (activeWarning) {
            emptyDiv.innerHTML = `
                <div class="empty-state-icon-wrapper" style="width: 48px; height: 48px; font-size: 1.25rem; background: rgba(245, 158, 11, 0.15); color: #f59e0b;">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                </div>
                <h3 style="color: #f59e0b;">Text Extraction Warning</h3>
                <p style="margin-top: 8px;">${escapeHTML(activeWarning)}</p>
            `;
        } else {
            emptyDiv.innerHTML = `
                <div class="empty-state-icon-wrapper" style="width: 48px; height: 48px; font-size: 1.25rem;">
                    <i class="fa-regular fa-file"></i>
                </div>
                <h3>No Content Available</h3>
                <p>This document appears to be empty or has no readable text chunks.</p>
            `;
        }
        viewerContent.appendChild(emptyDiv);
        return;
    }
    
    const rawQuery = (searchQuery || '').normalize('NFKC').trim();
    let totalMatches = 0;
    
    chunks.forEach((chunk, index) => {
        const chunkDiv = document.createElement('div');
        chunkDiv.className = 'viewer-chunk chunk-reveal';
        // Stagger entrance animation
        chunkDiv.style.animationDelay = `${Math.min(index * 0.04, 0.4)}s`;
        chunkDiv.dataset.chunkIndex = chunk.chunk_index;
        chunkDiv.dataset.pageNumber = chunk.page_number;
        
        // Chunk Header
        const headerDiv = document.createElement('div');
        headerDiv.className = 'viewer-chunk-header';
        
        // Page/Chunk Marker
        const markerSpan = document.createElement('div');
        markerSpan.className = 'viewer-page-marker';
        markerSpan.innerHTML = `
            <span class="marker-dot"></span>
            PAGE ${chunk.page_number} <span style="opacity:0.5">•</span> CHUNK ${chunk.chunk_index}
        `;
        
        // Action Buttons (Copy Chunk + Ask AI)
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'chunk-actions';
        
        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn-chunk-action';
        copyBtn.title = 'Copy chunk text to clipboard';
        copyBtn.innerHTML = `<i class="fa-regular fa-copy"></i> Copy`;
        copyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            navigator.clipboard.writeText(chunk.content).then(() => {
                copyBtn.classList.add('copied');
                copyBtn.innerHTML = `<i class="fa-solid fa-check"></i> Copied!`;
                setTimeout(() => {
                    copyBtn.classList.remove('copied');
                    copyBtn.innerHTML = `<i class="fa-regular fa-copy"></i> Copy`;
                }, 2000);
            });
        });
        
        const askAiBtn = document.createElement('button');
        askAiBtn.className = 'btn-chunk-action';
        askAiBtn.title = 'Ask AI to explain or summarize this chunk';
        askAiBtn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Ask AI`;
        askAiBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (chatInput) {
                const preview = chunk.content.substring(0, 100).replace(/\s+/g, ' ').trim();
                chatInput.value = `Explain this section from page ${chunk.page_number}: "${preview}..."`;
                chatInput.style.height = '48px';
                const newHeight = Math.min(Math.max(chatInput.scrollHeight, 48), 160);
                chatInput.style.height = `${newHeight}px`;
                chatInput.focus();
            }
        });
        
        actionsDiv.appendChild(copyBtn);
        actionsDiv.appendChild(askAiBtn);
        
        headerDiv.appendChild(markerSpan);
        headerDiv.appendChild(actionsDiv);
        
        // Chunk Body
        const bodyDiv = document.createElement('div');
        bodyDiv.className = 'viewer-chunk-body';
        bodyDiv.setAttribute('dir', 'auto');
        
        let contentHtml = escapeHTML((chunk.content || '').normalize('NFKC'));
        if (rawQuery) {
            const escapedForHtml = escapeHTML(rawQuery);
            const escapedRegex = escapedForHtml.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            try {
                const regex = new RegExp(`(${escapedRegex})`, 'giu');
                const matches = contentHtml.match(regex);
                if (matches) {
                    totalMatches += matches.length;
                }
                contentHtml = contentHtml.replace(regex, '<mark class="search-highlight">$1</mark>');
            } catch (e) {
                console.warn('Unicode search regex error:', e);
            }
        }
        
        bodyDiv.innerHTML = contentHtml.replace(/\n/g, '<br>');
        
        chunkDiv.appendChild(headerDiv);
        chunkDiv.appendChild(bodyDiv);

        // Long chunk collapsible behavior
        const isLongChunk = (chunk.content || '').length > 360 || (chunk.content || '').split('\n').length > 6;
        if (isLongChunk) {
            bodyDiv.classList.add('is-collapsible');
            if (rawQuery && contentHtml.includes('<mark class="search-highlight">')) {
                bodyDiv.classList.add('is-expanded');
            }

            const toggleBtn = document.createElement('button');
            toggleBtn.type = 'button';
            toggleBtn.className = 'btn-chunk-expand';
            toggleBtn.innerHTML = bodyDiv.classList.contains('is-expanded')
                ? '<i class="fa-solid fa-chevron-up"></i> Show less'
                : '<i class="fa-solid fa-chevron-down"></i> Show more';

            toggleBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const expanded = bodyDiv.classList.toggle('is-expanded');
                toggleBtn.innerHTML = expanded
                    ? '<i class="fa-solid fa-chevron-up"></i> Show less'
                    : '<i class="fa-solid fa-chevron-down"></i> Show more';
            });
            chunkDiv.appendChild(toggleBtn);
        }

        viewerContent.appendChild(chunkDiv);
    });

    // Update search count pill if search was active
    const searchCountPill = document.getElementById('doc-search-count');
    if (searchCountPill) {
        if (rawQuery) {
            searchCountPill.classList.remove('hidden');
            if (totalMatches > 0) {
                searchCountPill.textContent = `${totalMatches} ${totalMatches === 1 ? 'match' : 'matches'}`;
                searchCountPill.className = 'doc-search-count-pill has-matches';
            } else {
                searchCountPill.textContent = 'No matches';
                searchCountPill.className = 'doc-search-count-pill no-matches';
            }
        } else {
            searchCountPill.classList.add('hidden');
        }
    }
}


// --- Chat & QA Logic ---
function setupChat() {
    btnSend.addEventListener('click', handleSendChat);
    
    // Auto-resizing textarea & Keydown Handling (Enter to send, Shift+Enter for newline)
    if (chatInput) {
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendChat();
            }
        });
        
        const autoResizeChatInput = () => {
            chatInput.style.height = '48px';
            const scrollH = chatInput.scrollHeight;
            const newHeight = Math.min(Math.max(scrollH, 48), 160);
            chatInput.style.height = `${newHeight}px`;
            if (scrollH > 160) {
                chatInput.style.overflowY = 'auto';
            } else {
                chatInput.style.overflowY = 'hidden';
            }
        };

        chatInput.addEventListener('input', autoResizeChatInput);
    }

    // Suggested Question Chips Click Handler
    const suggestedChips = document.querySelectorAll('.suggested-chip');
    suggestedChips.forEach(chip => {
        chip.addEventListener('click', () => {
            const query = chip.dataset.query;
            if (query && activeDocumentId) {
                chatInput.value = query;
                chatInput.style.height = '48px';
                const newHeight = Math.min(Math.max(chatInput.scrollHeight, 48), 160);
                chatInput.style.height = `${newHeight}px`;
                handleSendChat();
            } else if (!activeDocumentId) {
                alert('Please select a document first.');
            }
        });
    });
    
    btnSummarize.addEventListener('click', async () => {
        if (!activeDocumentId) return;
        
        btnSummarize.classList.add('is-loading');
        btnSummarize.innerHTML = '<i class="fa-solid fa-spinner"></i> Summarizing...';
        appendMessage('user', 'Please summarize this document.');
        showTypingIndicator();
        
        try {
            const res = await summarizeDocument(activeDocumentId);
            hideTypingIndicator();
            
            // Render markdown answer
            const rawHtml = marked.parse(res.answer);
            appendMessage('ai', rawHtml);
        } catch (err) {
            hideTypingIndicator();
            appendMessage('ai', `<span style="color: #ef4444;">Failed to generate summary. Make sure GEMINI_API_KEY is set.</span>`);
        } finally {
            btnSummarize.classList.remove('is-loading');
            btnSummarize.innerHTML = '<i class="fa-solid fa-bolt"></i> Summarize';
        }
    });

    const btnClearChat = document.getElementById('btn-clear-chat');
    if (btnClearChat) {
        btnClearChat.addEventListener('click', () => {
            if (confirm('Clear all chat messages for this document?')) {
                const filename = window.activeDocumentFilename || 'this document';
                chatContainer.innerHTML = `
                    <div class="chat-message ai-message">
                        <div class="avatar"><i class="fa-solid fa-robot"></i></div>
                        <div class="message-content" dir="auto">
                            Hello! I'm ready to answer any questions about <strong>${filename}</strong>.
                        </div>
                    </div>
                `;
            }
        });
    }
}

async function handleSendChat() {
    const text = chatInput.value.trim();
    if (!text || !activeDocumentId) return;
    
    window.lastUserQuestion = text;
    chatInput.value = '';
    // Auto reset textarea height if resized
    chatInput.style.height = '48px';
    chatInput.style.overflowY = 'hidden';
    appendMessage('user', text);
    showTypingIndicator();
    
    try {
        const res = await askQuestion(text, activeDocumentId);
        hideTypingIndicator();
        
        const rawHtml = marked.parse(res.answer);
        appendMessage('ai', rawHtml);
        
        if (res.citations && res.citations.length > 0) {
            renderCitations(res.citations);
        }
        
    } catch (err) {
        hideTypingIndicator();
        appendMessage('ai', `<span style="color: #ef4444;">An error occurred while answering.</span>`);
    }
}

function showTypingIndicator() {
    hideTypingIndicator();
    const div = document.createElement('div');
    div.className = 'chat-message ai-message';
    div.id = 'ai-typing-loader';
    div.innerHTML = `
        <div class="avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="message-content">
            <div class="typing-indicator" title="AI is thinking...">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
            </div>
        </div>
    `;
    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function hideTypingIndicator() {
    const loader = document.getElementById('ai-typing-loader');
    if (loader) loader.remove();
    const tempLoader = document.getElementById('temp-loader');
    if (tempLoader) tempLoader.remove();
}

function enhanceCodeBlocks(container) {
    if (!container) return;
    const preBlocks = container.querySelectorAll('pre');
    preBlocks.forEach(pre => {
        if (pre.querySelector('.btn-code-copy')) return;
        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn-code-copy';
        copyBtn.innerHTML = '<i class="fa-regular fa-copy"></i> Copy';
        copyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const code = pre.querySelector('code');
            const textToCopy = code ? code.innerText : pre.innerText;
            navigator.clipboard.writeText(textToCopy).then(() => {
                copyBtn.classList.add('copied');
                copyBtn.innerHTML = '<i class="fa-solid fa-check"></i> Copied!';
                setTimeout(() => {
                    copyBtn.classList.remove('copied');
                    copyBtn.innerHTML = '<i class="fa-regular fa-copy"></i> Copy';
                }, 2000);
            });
        });
        pre.appendChild(copyBtn);
    });
}

function attachAiMessageActions(messageDiv) {
    const content = messageDiv.querySelector('.message-content');
    if (!content) return;
    
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'message-actions';
    
    // Copy response button
    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn-message-action';
    copyBtn.title = 'Copy response text';
    copyBtn.innerHTML = '<i class="fa-regular fa-copy"></i> Copy';
    copyBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const clone = content.cloneNode(true);
        const actionEl = clone.querySelector('.message-actions');
        if (actionEl) actionEl.remove();
        navigator.clipboard.writeText(clone.innerText.trim()).then(() => {
            copyBtn.classList.add('copied');
            copyBtn.innerHTML = '<i class="fa-solid fa-check"></i> Copied!';
            setTimeout(() => {
                copyBtn.classList.remove('copied');
                copyBtn.innerHTML = '<i class="fa-regular fa-copy"></i> Copy';
            }, 2000);
        });
    });
    
    // Regenerate response button
    const regenBtn = document.createElement('button');
    regenBtn.className = 'btn-message-action';
    regenBtn.title = 'Regenerate response';
    regenBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Regenerate';
    regenBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (window.lastUserQuestion && activeDocumentId) {
            chatInput.value = window.lastUserQuestion;
            handleSendChat();
        }
    });
    
    actionsDiv.appendChild(copyBtn);
    if (window.lastUserQuestion) {
        actionsDiv.appendChild(regenBtn);
    }
    content.appendChild(actionsDiv);
}

function appendMessage(sender, contentHTML, id = null) {
    const div = document.createElement('div');
    div.className = `chat-message ${sender}-message`;
    if (id) div.id = id;
    
    const icon = sender === 'user' ? 'fa-user' : 'fa-robot';
    
    div.innerHTML = `
        <div class="avatar"><i class="fa-solid ${icon}"></i></div>
        <div class="message-content" dir="auto">${contentHTML}</div>
    `;
    
    if (sender === 'ai' && !id) {
        enhanceCodeBlocks(div);
        attachAiMessageActions(div);
    }
    
    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    return div;
}

function renderCitations(citations) {
    const template = document.getElementById('citation-template');
    const citationNode = template.content.cloneNode(true);
    const ul = citationNode.querySelector('.citation-list');
    
    citations.forEach(cit => {
        const li = document.createElement('li');
        li.textContent = `[${cit.id}] Page ${cit.page_number} (Relevance: ${(cit.score).toFixed(2)})`;
        ul.appendChild(li);
    });
    
    // Append inside the last AI message
    const lastAiMessage = chatContainer.querySelector('.ai-message:last-child .message-content');
    if (lastAiMessage) {
        lastAiMessage.appendChild(citationNode);
    }
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// --- Upload Logic ---
function setupUpload() {
    if (!uploadZone || !fileInput) return;

    uploadZone.addEventListener('click', () => fileInput.click());
    
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('drag-over');
    });
    
    uploadZone.addEventListener('dragleave', (e) => {
        // Prevent child elements from flickering dragleave
        if (!uploadZone.contains(e.relatedTarget)) {
            uploadZone.classList.remove('drag-over');
        }
    });
    
    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) {
            handleFileUpload(e.dataTransfer.files[0]);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFileUpload(e.target.files[0]);
        }
    });
}

async function handleFileUpload(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    const uploadPrompt = uploadZone.querySelector('.upload-prompt');
    const progressBar = document.getElementById('upload-progress-bar');
    const progressPercent = document.getElementById('upload-progress-percent');
    const progressText = document.getElementById('upload-progress-text');

    if (uploadPrompt) uploadPrompt.classList.add('hidden');
    if (uploadProgress) uploadProgress.classList.remove('hidden');

    const updateProgress = (pct, text) => {
        if (progressBar) progressBar.style.width = `${pct}%`;
        if (progressPercent) progressPercent.textContent = `${pct}%`;
        if (progressText && text) progressText.textContent = text;
    };

    updateProgress(20, 'Uploading file...');

    // Simulate progressive processing feedback
    const progressInterval = setInterval(() => {
        const current = parseInt(progressPercent ? progressPercent.textContent : '20');
        if (current < 85) {
            const next = current + Math.floor(Math.random() * 15) + 5;
            updateProgress(
                Math.min(next, 85),
                next > 50 ? 'Creating neural embeddings...' : 'Extracting text...'
            );
        }
    }, 600);
    
    try {
        const res = await fetch(`${API_BASE_URL}/api/upload`, {
            method: 'POST',
            body: formData
        });
        
        clearInterval(progressInterval);

        const uploadData = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(uploadData.detail || "Upload failed");
        }
        
        updateProgress(100, '✓ Ingestion complete!');
        if (uploadData.warning) {
            window.showToast(uploadData.warning, 'error', 6000);
        }
        await new Promise(r => setTimeout(r, 400));
        await loadDocuments();
        
    } catch (err) {
        clearInterval(progressInterval);
        console.error("Upload error:", err);
        // Visual error shake
        uploadZone.classList.add('shake');
        setTimeout(() => uploadZone.classList.remove('shake'), 500);
        alert("Error uploading file: " + err.message);
    } finally {
        if (uploadProgress) uploadProgress.classList.add('hidden');
        if (uploadPrompt) uploadPrompt.classList.remove('hidden');
        if (fileInput) fileInput.value = ''; // reset
        if (progressBar) progressBar.style.width = '0%';
    }
}
// =====================================================
// QUIZ MAKER
// =====================================================

function setupQuiz() {
    setupSegmentedControls();
    if (!btnGenerateQuiz) return;
    btnGenerateQuiz.addEventListener('click', generateQuiz);
}

function setupSegmentedControls() {
    const countBtns = document.querySelectorAll('#quiz-count-segments .segment-btn');
    countBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            countBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            if (quizQuestionCount) {
                quizQuestionCount.value = btn.dataset.value;
            }
        });
    });

    const diffBtns = document.querySelectorAll('#quiz-difficulty-segments .segment-btn');
    diffBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            diffBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            if (quizDifficulty) {
                quizDifficulty.value = btn.dataset.value;
            }
        });
    });
}

// Global Quiz State
window.currentQuizQuestions = [];
window.quizUserAnswers = {};
window.currentQuizIndex = 0;

async function generateQuiz() {
    if (!activeDocumentId) {
        showQuizStatus("Please select a document first.", "error");
        return;
    }

    const numQuestions = parseInt(quizQuestionCount.value);
    const difficulty = quizDifficulty.value;

    // Reset previous results
    quizResults.innerHTML = '';
    quizResults.classList.add('hidden');

    showQuizStatus(
        `<div class="spinner"></div> Generating and verifying your quiz with AI...`,
        "loading"
    );

    btnGenerateQuiz.disabled = true;
    btnGenerateQuiz.classList.add('is-loading');
    btnGenerateQuiz.innerHTML = '<span class="btn-shine"></span><i class="fa-solid fa-spinner"></i> <span>Generating...</span>';

    try {
        const res = await fetch(`${API_BASE_URL}/api/quiz/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                document_id: activeDocumentId,
                num_questions: numQuestions,
                difficulty: difficulty
            })
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || "Quiz generation failed.");
        }

        if (!data.questions || data.questions.length === 0) {
            showQuizStatus(
                `No questions could be verified. Generated: ${data.generated_count}, Rejected: ${data.rejected_count}.`,
                "error"
            );
            return;
        }

        showQuizStatus(
            `✓ ${data.verified_count} verified questions generated`,
            "success"
        );

        window.currentQuizQuestions = data.questions;
        window.quizUserAnswers = {};
        window.currentQuizIndex = 0;
        renderQuiz(data.questions);

    } catch (err) {
        console.error("Quiz generation error:", err);

        showQuizStatus(
            `Failed to generate quiz: ${err.message}`,
            "error"
        );

    } finally {
        btnGenerateQuiz.disabled = false;
        btnGenerateQuiz.classList.remove('is-loading');
        btnGenerateQuiz.innerHTML = '<span class="btn-shine"></span><i class="fa-solid fa-wand-magic-sparkles"></i> <span>Generate Quiz</span>';
    }
}


function showQuizStatus(message, type) {
    quizStatus.className = `quiz-status ${type}`;
    quizStatus.innerHTML = message;
    quizStatus.classList.remove('hidden');
}


function renderQuiz(questions) {
    quizResults.innerHTML = '';
    window.currentQuizQuestions = questions || [];
    window.quizUserAnswers = {};

    if (!questions || questions.length === 0) return;

    // Tracker & Navigator Header
    const trackerContainer = document.createElement('div');
    trackerContainer.className = 'quiz-progress-tracker glass-panel';
    trackerContainer.style.padding = 'var(--space-4) var(--space-5)';
    trackerContainer.style.borderRadius = 'var(--radius-xl)';

    trackerContainer.innerHTML = `
        <div class="quiz-progress-labels">
            <span id="quiz-progress-text">Answered 0 of ${questions.length} questions</span>
            <span id="quiz-score-badge" class="badge badge-brand hidden">Score: 0/${questions.length}</span>
        </div>
        <div class="quiz-progress-track">
            <div id="quiz-progress-fill" class="quiz-progress-fill" style="width: 0%;"></div>
        </div>
        <div class="quiz-navigator" id="quiz-navigator"></div>
    `;

    quizResults.appendChild(trackerContainer);

    // Build Navigator Pills
    const navContainer = trackerContainer.querySelector('#quiz-navigator');
    questions.forEach((_, i) => {
        const pill = document.createElement('button');
        pill.type = 'button';
        pill.className = `nav-question-pill ${i === 0 ? 'active' : ''}`;
        pill.dataset.questionIndex = i;
        pill.textContent = i + 1;
        pill.addEventListener('click', () => {
            const targetCard = document.getElementById(`quiz-card-${i}`);
            if (targetCard) {
                targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                document.querySelectorAll('.nav-question-pill').forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
            }
        });
        navContainer.appendChild(pill);
    });

    // Render Question Cards
    questions.forEach((question, index) => {
        const card = document.createElement('div');
        card.className = 'quiz-question-card';
        card.id = `quiz-card-${index}`;

        const letters = ['A', 'B', 'C', 'D', 'E', 'F'];
        const optionsList = question.options || [];

        const optionsHTML = optionsList.map((opt, optIdx) => {
            const rawLabel = typeof opt === 'string' ? opt : (opt.label || '');
            const letter = letters[optIdx] || String(optIdx + 1);
            return `
                <div class="quiz-option-card" data-question-index="${index}" data-option-value="${escapeHTML(rawLabel)}">
                    <div class="option-letter-badge">${letter}</div>
                    <div class="option-text" dir="auto">${escapeHTML(rawLabel)}</div>
                </div>
            `;
        }).join('');

        const explanationText = question.explanation || question.rationale || 'Source grounding verified from document context.';

        card.innerHTML = `
            <div class="quiz-question-header">
                <span class="question-number-pill">QUESTION ${index + 1} OF ${questions.length}</span>
                <span class="verified-badge"><i class="fa-solid fa-circle-check"></i> Verified Grounding</span>
            </div>
            <h4 class="quiz-question" dir="auto">${escapeHTML(question.question)}</h4>
            <div class="quiz-options">
                ${optionsHTML}
            </div>
            <div class="quiz-metadata" style="display:flex;gap:var(--space-3);font-size:11px;color:var(--text-tertiary);margin-top:var(--space-1);flex-wrap:wrap;">
                <span><i class="fa-solid fa-layer-group"></i> ${escapeHTML(question.topic || 'General')}</span>
                <span><i class="fa-solid fa-signal"></i> ${escapeHTML(question.difficulty || 'Mixed')}</span>
                <span><i class="fa-solid fa-link"></i> Page ${question.source_page || 1} • Chunk ${escapeHTML(String(question.source_chunk_id || 'N/A'))}</span>
            </div>
            <div class="quiz-explanation-accordion">
                <button type="button" class="btn-toggle-explanation" onclick="toggleExplanation(${index})">
                    <i class="fa-solid fa-chevron-down"></i> Explanation & Source Context
                </button>
                <div class="quiz-explanation-body hidden" id="explanation-${index}" dir="auto">
                    <strong><i class="fa-solid fa-lightbulb"></i> Answer Analysis:</strong>
                    <p style="margin:4px 0 0;" dir="auto">${escapeHTML(explanationText)}</p>
                    <p style="margin:6px 0 0;font-weight:600;color:var(--brand-indigo);" dir="auto">Correct: ${escapeHTML(question.correct_answer)}</p>
                </div>
            </div>
        `;

        quizResults.appendChild(card);
    });

    // Wire up option clicks
    const allOptionCards = quizResults.querySelectorAll('.quiz-option-card');
    allOptionCards.forEach(optCard => {
        optCard.addEventListener('click', () => {
            const qIdx = parseInt(optCard.dataset.questionIndex);
            const val = optCard.dataset.optionValue;
            handleOptionSelect(qIdx, val, optCard);
        });
    });

    quizResults.classList.remove('hidden');
    quizResults.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function handleOptionSelect(qIdx, selectedValue, clickedCard) {
    if (window.quizUserAnswers[qIdx] !== undefined) return;

    const question = window.currentQuizQuestions[qIdx];
    if (!question) return;

    const card = document.getElementById(`quiz-card-${qIdx}`);
    const options = card.querySelectorAll('.quiz-option-card');
    options.forEach(o => o.classList.add('locked'));

    const correctAns = (question.correct_answer || '').trim().toLowerCase();
    const chosen = selectedValue.trim().toLowerCase();

    // Flexible match
    const isCorrect = (chosen === correctAns) ||
                      correctAns.startsWith(chosen.substring(0, 2)) ||
                      chosen.includes(correctAns) ||
                      correctAns.includes(chosen);

    if (isCorrect) {
        clickedCard.classList.add('correct');
        window.quizUserAnswers[qIdx] = { correct: true, chosen: selectedValue };
    } else {
        clickedCard.classList.add('wrong');
        options.forEach(o => {
            const oVal = (o.dataset.optionValue || '').trim().toLowerCase();
            if (oVal === correctAns || correctAns.includes(oVal) || oVal.includes(correctAns)) {
                o.classList.add('correct');
            }
        });
        window.quizUserAnswers[qIdx] = { correct: false, chosen: selectedValue };
    }

    // Automatically reveal explanation
    const explanationBody = document.getElementById(`explanation-${qIdx}`);
    const toggleBtn = card.querySelector('.btn-toggle-explanation');
    if (explanationBody) explanationBody.classList.remove('hidden');
    if (toggleBtn) toggleBtn.classList.add('expanded');

    // Update navigator pill
    const navPill = document.querySelector(`.nav-question-pill[data-question-index="${qIdx}"]`);
    if (navPill) {
        navPill.classList.add(isCorrect ? 'answered-correct' : 'answered-wrong');
    }

    // Update progress bar
    updateQuizProgress();
}

function toggleExplanation(qIdx) {
    const body = document.getElementById(`explanation-${qIdx}`);
    const card = document.getElementById(`quiz-card-${qIdx}`);
    const btn = card ? card.querySelector('.btn-toggle-explanation') : null;
    if (body) {
        body.classList.toggle('hidden');
        if (btn) btn.classList.toggle('expanded', !body.classList.contains('hidden'));
    }
}

function updateQuizProgress() {
    const total = window.currentQuizQuestions.length;
    const answeredCount = Object.keys(window.quizUserAnswers).length;
    const correctCount = Object.values(window.quizUserAnswers).filter(a => a.correct).length;

    const fill = document.getElementById('quiz-progress-fill');
    const text = document.getElementById('quiz-progress-text');
    const scoreBadge = document.getElementById('quiz-score-badge');

    if (fill) fill.style.width = `${(answeredCount / total) * 100}%`;
    if (text) text.textContent = `Answered ${answeredCount} of ${total} questions`;
    if (scoreBadge) {
        scoreBadge.classList.remove('hidden');
        scoreBadge.textContent = `Score: ${correctCount}/${total}`;
    }

    if (answeredCount === total) {
        renderQuizResultsSummary(correctCount, total);
    }
}

function showQuizAnswer(button, index) {
    toggleExplanation(index);
}

function renderQuizResultsSummary(correctCount, total) {
    const existingSummary = document.getElementById('quiz-results-summary-card');
    if (existingSummary) existingSummary.remove();

    const percentage = Math.round((correctCount / total) * 100);
    const summaryCard = document.createElement('div');
    summaryCard.className = 'quiz-results-summary glass-panel';
    summaryCard.id = 'quiz-results-summary-card';

    let messageTitle = 'Quiz Completed!';
    let messageSubtitle = 'You answered all questions.';
    if (percentage === 100) {
        messageTitle = '🎉 Perfect Score!';
        messageSubtitle = 'Mastery achieved! You nailed every single question.';
    } else if (percentage >= 80) {
        messageTitle = '🌟 Outstanding Job!';
        messageSubtitle = 'Excellent comprehension of the source document.';
    } else if (percentage >= 60) {
        messageTitle = '👍 Good Effort!';
        messageSubtitle = 'Solid understanding. Review the explanations below to master the rest.';
    } else {
        messageTitle = '📚 Keep Practicing!';
        messageSubtitle = 'Review the source pages and try again to improve your score.';
    }

    const radius = 54;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (percentage / 100) * circumference;

    summaryCard.innerHTML = `
        <div style="font-size:1.75rem;font-weight:800;color:var(--text-primary);margin-bottom:2px;">${messageTitle}</div>
        <p style="color:var(--text-secondary);font-size:var(--text-sm);max-width:440px;">${messageSubtitle}</p>
        
        <div class="score-counter-circle">
            <svg viewBox="0 0 120 120">
                <defs>
                    <linearGradient id="scoreGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stop-color="#4f46e5" />
                        <stop offset="50%" stop-color="#7c3aed" />
                        <stop offset="100%" stop-color="#ec4899" />
                    </linearGradient>
                </defs>
                <circle class="score-circle-bg" cx="60" cy="60" r="${radius}" />
                <circle class="score-circle-fill" id="score-circle-bar" cx="60" cy="60" r="${radius}"
                        stroke-dasharray="${circumference}"
                        stroke-dashoffset="${circumference}" />
            </svg>
            <div style="position:absolute;display:flex;flex-direction:column;align-items:center;">
                <span class="score-circle-text" id="score-counter-text">0%</span>
                <span class="score-circle-subtext">${correctCount} of ${total} correct</span>
            </div>
        </div>

        <div class="quiz-results-actions">
            <button type="button" class="btn-primary" id="btn-quiz-retry" style="padding:0.6rem 1.4rem;border-radius:var(--radius-lg);font-weight:600;">
                <i class="fa-solid fa-rotate-left"></i> Retry Quiz
            </button>
            <button type="button" class="btn-primary-outline" id="btn-quiz-new" style="padding:0.6rem 1.4rem;border-radius:var(--radius-lg);font-weight:600;">
                <i class="fa-solid fa-plus"></i> New Quiz
            </button>
        </div>
    `;

    quizResults.appendChild(summaryCard);
    summaryCard.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Animate score counter & circle
    setTimeout(() => {
        const circleBar = document.getElementById('score-circle-bar');
        if (circleBar) {
            circleBar.style.strokeDashoffset = `${offset}`;
        }

        const counterText = document.getElementById('score-counter-text');
        if (counterText) {
            let start = 0;
            const duration = 1200;
            const startTime = performance.now();

            function updateCounter(currentTime) {
                const elapsed = currentTime - startTime;
                const progress = Math.min(elapsed / duration, 1);
                const currentVal = Math.round(progress * percentage);
                counterText.textContent = `${currentVal}%`;
                if (progress < 1) {
                    requestAnimationFrame(updateCounter);
                }
            }
            requestAnimationFrame(updateCounter);
        }
    }, 150);

    // Confetti burst for high scores
    if (percentage >= 70) {
        triggerConfettiBurst();
    }

    // Button event listeners
    const retryBtn = summaryCard.querySelector('#btn-quiz-retry');
    if (retryBtn) {
        retryBtn.addEventListener('click', () => {
            window.quizUserAnswers = {};
            renderQuiz(window.currentQuizQuestions);
        });
    }

    const newBtn = summaryCard.querySelector('#btn-quiz-new');
    if (newBtn) {
        newBtn.addEventListener('click', () => {
            const controls = document.querySelector('.quiz-controls');
            if (controls) {
                controls.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            if (btnGenerateQuiz) btnGenerateQuiz.focus();
        });
    }
}

// Lightweight vanilla canvas confetti burst
function triggerConfettiBurst() {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        return;
    }

    const canvas = document.createElement('canvas');
    canvas.style.position = 'fixed';
    canvas.style.top = '0';
    canvas.style.left = '0';
    canvas.style.width = '100vw';
    canvas.style.height = '100vh';
    canvas.style.pointerEvents = 'none';
    canvas.style.zIndex = '9999';
    document.body.appendChild(canvas);

    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    const ctx = canvas.getContext('2d');

    const colors = ['#4f46e5', '#7c3aed', '#ec4899', '#10b981', '#f59e0b', '#3b82f6'];
    const particles = [];

    for (let i = 0; i < 90; i++) {
        particles.push({
            x: canvas.width / 2 + (Math.random() * 200 - 100),
            y: canvas.height * 0.4 + (Math.random() * 100 - 50),
            vx: (Math.random() - 0.5) * 14,
            vy: (Math.random() - 0.8) * 16,
            size: Math.random() * 8 + 4,
            color: colors[Math.floor(Math.random() * colors.length)],
            rotation: Math.random() * 360,
            rotationSpeed: (Math.random() - 0.5) * 12,
            alpha: 1
        });
    }

    let animationFrame;
    const startTime = performance.now();

    function render(time) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        let alive = false;

        particles.forEach(p => {
            p.x += p.vx;
            p.y += p.vy;
            p.vy += 0.35;
            p.rotation += p.rotationSpeed;
            p.alpha -= 0.012;

            if (p.alpha > 0) {
                alive = true;
                ctx.save();
                ctx.globalAlpha = Math.max(p.alpha, 0);
                ctx.translate(p.x, p.y);
                ctx.rotate((p.rotation * Math.PI) / 180);
                ctx.fillStyle = p.color;
                ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
                ctx.restore();
            }
        });

        if (alive && time - startTime < 3500) {
            animationFrame = requestAnimationFrame(render);
        } else {
            cancelAnimationFrame(animationFrame);
            canvas.remove();
        }
    }

    requestAnimationFrame(render);
}

// Prevent HTML injection when displaying generated content
function escapeHTML(value) {
    const div = document.createElement('div');
    div.textContent = value ?? '';
    return div.innerHTML;
}

// Lightweight debounce utility for high-frequency input and search handlers
function debounce(fn, delay = 150) {
    let timer = null;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}