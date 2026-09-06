// Global State
let activeDocumentId = null;

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

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadDocuments();
    setupUpload();
    setupChat();
});

// --- API Calls ---
async function fetchDocuments() {
    const res = await fetch('/api/documents');
    const data = await res.json();
    return data.documents;
}

async function fetchDocumentContent(docId) {
    const res = await fetch(`/api/documents/${docId}/content`);
    if (!res.ok) throw new Error("Failed to load document content");
    return await res.json();
}

async function deleteDocument(docId) {
    await fetch(`/api/documents/${docId}`, { method: 'DELETE' });
    if (activeDocumentId === docId) {
        closeDocument();
    }
    loadDocuments();
}

async function askQuestion(query, docId) {
    const res = await fetch('/api/qa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query, mode: "hybrid", top_k: 40, document_id: docId })
    });
    return await res.json();
}

async function summarizeDocument(docId) {
    const res = await fetch(`/api/documents/${docId}/summarize`, {
        method: 'POST'
    });
    return await res.json();
}

// --- UI Logic ---
async function loadDocuments() {
    try {
        const docs = await fetchDocuments();
        renderDocumentsList(docs);
    } catch (err) {
        console.error("Error loading documents:", err);
    }
}

function renderDocumentsList(docs) {
    documentsList.innerHTML = '';
    docs.forEach(doc => {
        const li = document.createElement('li');
        li.className = `doc-item ${doc.id === activeDocumentId ? 'active' : ''}`;
        
        const sizeKB = (doc.file_size / 1024).toFixed(1);
        
        li.innerHTML = `
            <div class="doc-title">
                <i class="fa-solid fa-file-${doc.file_type === 'pdf' ? 'pdf' : 'lines'}"></i> 
                ${doc.filename}
            </div>
            <div class="doc-meta">
                <span>${sizeKB} KB</span>
                <button class="delete-btn" title="Delete"><i class="fa-solid fa-trash"></i></button>
            </div>
        `;
        
        li.addEventListener('click', (e) => {
            if (e.target.closest('.delete-btn')) {
                e.stopPropagation();
                if (confirm(`Delete ${doc.filename}?`)) deleteDocument(doc.id);
            } else {
                openDocument(doc.id, doc.filename, sizeKB);
            }
        });
        
        documentsList.appendChild(li);
    });
}

async function openDocument(docId, filename, sizeKB) {
    activeDocumentId = docId;
    
    // Update Sidebar Selection
    document.querySelectorAll('.doc-item').forEach(el => el.classList.remove('active'));
    // We re-render or just find it. For now, re-render is fine, but we can rely on DOM.
    loadDocuments();
    
    // Toggle UI States
    emptyState.classList.add('hidden');
    documentWorkspace.classList.remove('hidden');
    
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
    emptyState.classList.remove('hidden');
    documentWorkspace.classList.add('hidden');
}

function renderDocumentContent(chunks) {
    viewerContent.innerHTML = '';
    if (!chunks || chunks.length === 0) {
        viewerContent.innerHTML = '<p>No content extracted for this document.</p>';
        return;
    }
    
    chunks.forEach(chunk => {
        const chunkDiv = document.createElement('div');
        chunkDiv.className = 'viewer-chunk';
        
        const pageMarker = document.createElement('div');
        pageMarker.className = 'viewer-page-marker';
        pageMarker.textContent = `Page ${chunk.page_number} (Chunk ${chunk.chunk_index})`;
        
        const textDiv = document.createElement('div');
        // Simple formatting
        textDiv.innerHTML = chunk.content.replace(/\\n/g, '<br>');
        
        chunkDiv.appendChild(pageMarker);
        chunkDiv.appendChild(textDiv);
        viewerContent.appendChild(chunkDiv);
    });
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
    uploadZone.addEventListener('click', () => fileInput.click());
    
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.querySelector('.upload-prompt').style.borderColor = 'var(--accent)';
    });
    
    uploadZone.addEventListener('dragleave', () => {
        uploadZone.querySelector('.upload-prompt').style.borderColor = 'var(--border)';
    });
    
    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.querySelector('.upload-prompt').style.borderColor = 'var(--border)';
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
    
    uploadZone.querySelector('.upload-prompt').classList.add('hidden');
    uploadProgress.classList.remove('hidden');
    
    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!res.ok) throw new Error("Upload failed");
        
        await loadDocuments();
        
    } catch (err) {
        alert("Error uploading file: " + err.message);
    } finally {
        uploadProgress.classList.add('hidden');
        uploadZone.querySelector('.upload-prompt').classList.remove('hidden');
        fileInput.value = ''; // reset
    }
}
