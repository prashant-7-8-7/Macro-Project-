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

// Theme Management
function setupTheme() {
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = savedTheme || (systemPrefersDark ? 'dark' : 'light');
    
    document.documentElement.setAttribute('data-theme', initialTheme);

    const themeToggleBtn = document.getElementById('theme-toggle');
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
            const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', nextTheme);
            localStorage.setItem('theme', nextTheme);
        });
    }

    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (!localStorage.getItem('theme')) {
                const autoTheme = e.matches ? 'dark' : 'light';
                document.documentElement.setAttribute('data-theme', autoTheme);
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

    if (tabBtnDoc && tabBtnQuiz && panelDoc && panelQuiz) {
        tabBtnDoc.addEventListener('click', () => {
            tabBtnDoc.classList.add('active');
            tabBtnDoc.setAttribute('aria-selected', 'true');
            tabBtnQuiz.classList.remove('active');
            tabBtnQuiz.setAttribute('aria-selected', 'false');

            panelDoc.classList.remove('hidden');
            panelQuiz.classList.add('hidden');
        });

        tabBtnQuiz.addEventListener('click', () => {
            tabBtnQuiz.classList.add('active');
            tabBtnQuiz.setAttribute('aria-selected', 'true');
            tabBtnDoc.classList.remove('active');
            tabBtnDoc.setAttribute('aria-selected', 'false');

            panelQuiz.classList.remove('hidden');
            panelDoc.classList.add('hidden');
        });
    }

    if (tabBtnNotes) {
        tabBtnNotes.addEventListener('click', () => {
            if (typeof handleMakeNotes === 'function') {
                handleMakeNotes();
            } else {
                const makeNotesBtn = document.getElementById('btn-make-notes');
                if (makeNotesBtn) makeNotesBtn.click();
            }
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

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupTheme();
    setupWorkspaceTabs();
    setupSidebarToggle();
    setupPanelResizer();
    setupLibrarySearch();
    setupDocSearch();
    loadDocuments();
    setupUpload();
    setupChat();
    setupQuiz();
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

    searchInput.addEventListener('input', () => {
        const query = searchInput.value.trim().toLowerCase();
        
        if (searchClear) {
            if (query) {
                searchClear.classList.remove('hidden');
            } else {
                searchClear.classList.add('hidden');
            }
        }

        if (!query) {
            renderDocumentsList(window.allDocuments);
            return;
        }

        const filtered = window.allDocuments.filter(doc => 
            (doc.filename || '').toLowerCase().includes(query)
        );
        renderDocumentsList(filtered);
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

    searchInput.addEventListener('input', () => {
        const query = searchInput.value.trim();
        if (searchClear) {
            if (query) {
                searchClear.classList.remove('hidden');
            } else {
                searchClear.classList.add('hidden');
            }
        }
        renderDocumentContent(window.currentDocChunks, query);
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
            <div class="message-content">Hello! I'm ready to answer any questions about <strong>${filename}</strong>.</div>
        </div>
    `;
    
    // Fetch and render content
    try {
        const data = await fetchDocumentContent(docId);
        renderDocumentContent(data.chunks);
    } catch (err) {
        viewerContent.innerHTML = `<p style="color: #ef4444;">Error loading document content.</p>`;
    }
}

function closeDocument() {
    activeDocumentId = null;
    window.activeDocumentId = null;
    window.activeDocumentFilename = null;
    emptyState.classList.remove('hidden');
    documentWorkspace.classList.add('hidden');
}

// Global cache of current document chunks for in-document search
window.currentDocChunks = [];

function renderDocumentContent(chunks, searchQuery = '') {
    window.currentDocChunks = chunks || [];
    viewerContent.innerHTML = '';
    
    if (!chunks || chunks.length === 0) {
        viewerContent.innerHTML = `
            <div class="empty-state-card glass-panel" style="margin: var(--space-8) auto; max-width: 420px; text-align: center;">
                <div class="empty-state-icon-wrapper" style="width: 48px; height: 48px; font-size: 1.25rem;">
                    <i class="fa-regular fa-file"></i>
                </div>
                <h3>No Content Available</h3>
                <p>This document appears to be empty or has no readable text chunks.</p>
            </div>
        `;
        return;
    }
    
    const query = (searchQuery || '').trim().toLowerCase();
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
        
        let contentHtml = chunk.content;
        if (query) {
            // Escape special regex chars
            const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const regex = new RegExp(`(${escapedQuery})`, 'gi');
            const matches = contentHtml.match(regex);
            if (matches) {
                totalMatches += matches.length;
            }
            contentHtml = contentHtml.replace(regex, '<mark class="search-highlight">$1</mark>');
        }
        
        bodyDiv.innerHTML = contentHtml.replace(/\n/g, '<br>');
        
        chunkDiv.appendChild(headerDiv);
        chunkDiv.appendChild(bodyDiv);
        viewerContent.appendChild(chunkDiv);
    });

    // Update search count pill if search was active
    const searchCountPill = document.getElementById('doc-search-count');
    if (searchCountPill) {
        if (query) {
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
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSendChat();
    });
    
    btnSummarize.addEventListener('click', async () => {
        if (!activeDocumentId) return;
        
        appendMessage('user', 'Please summarize this document.');
        appendMessage('ai', '<div class="spinner" style="margin: 0; width: 16px; height: 16px;"></div> <em>Reading document...</em>', 'temp-loader');
        
        try {
            const res = await summarizeDocument(activeDocumentId);
            document.getElementById('temp-loader').remove();
            
            // Render markdown answer
            const rawHtml = marked.parse(res.answer);
            appendMessage('ai', rawHtml);
        } catch (err) {
            document.getElementById('temp-loader').remove();
            appendMessage('ai', `<span style="color: #ef4444;">Failed to generate summary. Make sure GEMINI_API_KEY is set.</span>`);
        }
    });
}

async function handleSendChat() {
    const text = chatInput.value.trim();
    if (!text || !activeDocumentId) return;
    
    chatInput.value = '';
    appendMessage('user', text);
    appendMessage('ai', '<div class="spinner" style="margin: 0; width: 16px; height: 16px;"></div> <em>Thinking...</em>', 'temp-loader');
    
    try {
        const res = await askQuestion(text, activeDocumentId);
        document.getElementById('temp-loader').remove();
        
        const rawHtml = marked.parse(res.answer);
        appendMessage('ai', rawHtml);
        
        if (res.citations && res.citations.length > 0) {
            renderCitations(res.citations);
        }
        
    } catch (err) {
        document.getElementById('temp-loader').remove();
        appendMessage('ai', `<span style="color: #ef4444;">An error occurred while answering.</span>`);
    }
}

function appendMessage(sender, contentHTML, id = null) {
    const div = document.createElement('div');
    div.className = `chat-message ${sender}-message`;
    if (id) div.id = id;
    
    const icon = sender === 'user' ? 'fa-user' : 'fa-robot';
    
    div.innerHTML = `
        <div class="avatar"><i class="fa-solid ${icon}"></i></div>
        <div class="message-content">${contentHTML}</div>
    `;
    
    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
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
                next > 50 ? 'Embedding chunks on GPU...' : 'Extracting text...'
            );
        }
    }, 600);
    
    try {
        const res = await fetch(`${API_BASE_URL}/api/upload`, {
            method: 'POST',
            body: formData
        });
        
        clearInterval(progressInterval);

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Upload failed");
        }
        
        updateProgress(100, '✓ Ingestion complete!');
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
    if (!btnGenerateQuiz) return;

    btnGenerateQuiz.addEventListener('click', generateQuiz);
}

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
        `<div class="spinner"></div> Generating and verifying your quiz...`,
        "loading"
    );

    btnGenerateQuiz.disabled = true;

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

        renderQuiz(data.questions);

    } catch (err) {
        console.error("Quiz generation error:", err);

        showQuizStatus(
            `Failed to generate quiz: ${err.message}`,
            "error"
        );

    } finally {
        btnGenerateQuiz.disabled = false;
    }
}


function showQuizStatus(message, type) {
    quizStatus.className = `quiz-status ${type}`;
    quizStatus.innerHTML = message;
    quizStatus.classList.remove('hidden');
}


function renderQuiz(questions) {
    quizResults.innerHTML = '';

    questions.forEach((question, index) => {

        const questionCard = document.createElement('div');
        questionCard.className = 'quiz-question-card';

        const optionsHTML = question.options.map(option => `
            <label class="quiz-option">
                <input
                    type="radio"
                    name="question-${index}"
                    value="${escapeHTML(option.label)}"
                >
                <span class="option-label">${escapeHTML(option.label)}</span>
            </label>
        `).join('');

        questionCard.innerHTML = `
            <div class="quiz-question-header">
                <span class="question-number">
                    Question ${index + 1}
                </span>

                <span class="verified-badge">
                    <i class="fa-solid fa-circle-check"></i>
                    Verified
                </span>
            </div>

            <h4 class="quiz-question">
                ${escapeHTML(question.question)}
            </h4>

            <div class="quiz-options">
                ${optionsHTML}
            </div>

            <div class="quiz-metadata">

                <span>
                    <i class="fa-solid fa-layer-group"></i>
                    ${escapeHTML(question.topic || 'General')}
                </span>

                <span>
                    <i class="fa-solid fa-signal"></i>
                    ${escapeHTML(question.difficulty || 'Mixed')}
                </span>

                <span>
                    <i class="fa-solid fa-brain"></i>
                    ${escapeHTML(question.bloom_level || 'Understand')}
                </span>

            </div>

            <div class="quiz-source">
                <i class="fa-solid fa-link"></i>
                Source: Page ${question.source_page || 1}
                • Chunk ${escapeHTML(String(question.source_chunk_id || 'N/A'))}
            </div>

            <button
                class="show-answer-btn"
                onclick="showQuizAnswer(this, ${index})"
            >
                Show Answer
            </button>

            <div class="quiz-answer hidden">
                <strong>
                    <i class="fa-solid fa-check"></i>
                    Correct Answer:
                </strong>

                ${escapeHTML(question.correct_answer)}
            </div>
        `;

        quizResults.appendChild(questionCard);
    });

    quizResults.classList.remove('hidden');

    quizResults.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
    });
}


function showQuizAnswer(button, index) {
    const card = button.closest('.quiz-question-card');
    const answer = card.querySelector('.quiz-answer');

    answer.classList.toggle('hidden');

    if (answer.classList.contains('hidden')) {
        button.textContent = 'Show Answer';
    } else {
        button.textContent = 'Hide Answer';
    }
}


// Prevent HTML injection when displaying generated content
function escapeHTML(value) {
    const div = document.createElement('div');
    div.textContent = value ?? '';
    return div.innerHTML;
}