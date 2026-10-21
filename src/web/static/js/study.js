/* Study features share the existing workspace and backend; all AI stays server-side. */
(() => {
    const $ = id => document.getElementById(id);
    const state = { sessionId: null, controller: null, busy: false, scope: [], subjectIds: null,
        cards: [], cardIndex: 0, pdfPage: 1, pdfPages: 1, pdfUrl: null, pdfDocument: null };
    const docId = () => window.activeDocumentId;
    const esc = value => escapeHTML(String(value ?? ''));
    const notify = (text, type = 'info') => window.showToast?.(text, type);
    async function api(path, options = {}) {
        const response = await fetch(`${API_BASE_URL}/api${path}`, {
            ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
        });
        return readApiResponse(response);
    }
    const post = (path, body) => api(path, { method: 'POST', body: JSON.stringify(body) });
    const safeAction = fn => async (...args) => {
        try { await fn(...args); } catch (error) { notify(error.message, 'error'); }
    };
    const bind = (id, event, fn) => $(id)?.addEventListener(event, safeAction(fn));
    function scope() { return [...new Set([docId(), ...state.scope].filter(Boolean))].sort(); }
    function welcome() {
        chatContainer.replaceChildren();
        appendMessage('ai', 'Ask a question, select an exam answer format, or choose documents to compare. Your completed conversations are saved.');
    }
    function renderScope() {
        const container = $('chat-document-scope');
        if (!container) return;
        container.replaceChildren();
        for (const doc of window.allDocuments || []) {
            const label = document.createElement('label'); label.className = 'study-check';
            const input = document.createElement('input'); input.type = 'checkbox'; input.value = doc.id;
            input.checked = scope().includes(doc.id); input.disabled = doc.id === docId();
            input.addEventListener('change', safeAction(async () => {
                if (input.checked && scope().length >= 20) { input.checked = false; throw new Error('Select up to 20 documents.'); }
                window.studyStopChat();
                state.scope = input.checked ? [...state.scope, doc.id] : state.scope.filter(id => id !== doc.id);
                state.sessionId = null; welcome(); await loadSessions(false);
            }));
            label.append(input, document.createTextNode(doc.filename)); container.append(label);
        }
    }
    async function loadSessions(restore = true) {
        if (!docId()) return;
        const openDoc = docId();
        const result = await api(`/documents/${openDoc}/conversations`);
        if (openDoc !== docId()) return;
        const sessions = result.sessions.filter(s => JSON.stringify(JSON.parse(s.scope_json)) === JSON.stringify(scope()));
        const select = $('chat-sessions'); select.replaceChildren(new Option('New conversation', ''));
        sessions.forEach(s => select.add(new Option(s.title, s.id)));
        if (restore && sessions.length) {
            state.sessionId = sessions[0].id;
            await restoreSession(state.sessionId);
        }
        select.value = state.sessionId || '';
    }
    async function restoreSession(ident) {
        if (!ident) { state.sessionId = null; welcome(); return; }
        const currentDoc = docId();
        const result = await api(`/conversations/${ident}`);
        if (currentDoc !== docId()) return;
        state.sessionId = ident; welcome();
        if (result.messages.length) chatContainer.replaceChildren();
        for (const message of result.messages) {
            appendMessage(message.role === 'user' ? 'user' : 'ai', message.role === 'user' ? message.content : marked.parse(message.content));
            if (message.role === 'assistant' && message.citations?.length) renderCitations(message.citations);
        }
    }
    window.studyStopChat = () => state.controller?.abort();
    window.studyDeleteConversation = safeAction(async () => {
        if (!state.sessionId || !confirm('Delete this saved conversation?')) return;
        window.studyStopChat();
        await api(`/conversations/${state.sessionId}`, { method: 'DELETE' });
        state.sessionId = null; welcome(); await loadSessions(false);
    });
    window.studySendChat = safeAction(async () => {
        const text = chatInput.value.trim();
        if (!text || !docId() || state.busy) return;
        state.busy = true; state.controller = new AbortController();
        const controller = state.controller;
        const openDoc = docId();
        window.lastUserQuestion = text; chatInput.value = ''; chatInput.style.height = '48px';
        appendMessage('user', text); hideTypingIndicator();
        const node = appendMessage('ai', '', `stream-${Date.now()}`);
        const content = node.querySelector('.message-content');
        $('chat-stop').classList.remove('hidden'); $('btn-send').disabled = true;
        let answer = '', completed = false;
        try {
            const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: state.controller.signal,
                body: JSON.stringify({ document_id: openDoc, document_ids: scope(), session_id: state.sessionId,
                    query: text, answer_style: $('chat-answer-style').value })
            });
            if (!response.ok) await readApiResponse(response);
            if (!response.body) throw new Error('Streaming is not supported in this browser.');
            const reader = response.body.getReader(), decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { value, done } = await reader.read();
                buffer += decoder.decode(value, { stream: !done });
                const packets = buffer.split('\n\n'); buffer = packets.pop();
                for (const packet of packets) {
                    if (controller.signal.aborted || openDoc !== docId()) return;
                    const dataLine = packet.split('\n').find(line => line.startsWith('data: '));
                    if (!dataLine) continue;
                    const event = JSON.parse(dataLine.slice(6));
                    if (event.type === 'session') state.sessionId = event.session_id;
                    if (event.type === 'delta') {
                        answer += event.text; content.textContent = answer;
                        chatContainer.scrollTop = chatContainer.scrollHeight;
                    }
                    if (event.type === 'error') throw new Error(event.message);
                    if (event.type === 'done') {
                        completed = true;
                        content.innerHTML = DOMPurify.sanitize(marked.parse(answer), { USE_PROFILES: {html: true}, FORBID_TAGS: ['img', 'style', 'form', 'input'], FORBID_ATTR: ['style'] });
                        enhanceCodeBlocks(node); attachAiMessageActions(node);
                        if (event.citations?.length) renderCitations(event.citations);
                        updateAiStatus(event.ai_available);
                    }
                }
                if (done) break;
            }
            if (!completed) throw new Error('The connection ended before the answer was completed.');
        } catch (error) {
            content.textContent = answer + (error.name === 'AbortError' ? '\n\nStopped. The partial answer was not saved.' : `\n\n${error.message}`);
            updateAiStatus(false);
        } finally {
            state.busy = false; state.controller = null; $('chat-stop').classList.add('hidden'); $('btn-send').disabled = false;
            if (openDoc === docId()) await loadSessions(false);
        }
    });
    window.studyFilterDocuments = docs => state.subjectIds ? docs.filter(d => state.subjectIds.includes(d.id)) : docs;
    async function loadSubjects() {
        const selected = $('subject-filter').value;
        const result = await api('/subjects');
        $('subject-filter').replaceChildren(new Option('All documents', ''));
        result.subjects.forEach(subject => $('subject-filter').add(new Option(`${subject.name} (${subject.document_count})`, subject.id)));
        $('subject-filter').value = selected;
    }
    async function filterSubject() {
        const ident = $('subject-filter').value;
        state.subjectIds = ident ? (await api(`/subjects/${ident}/documents`)).document_ids : null;
        renderDocumentsList(window.allDocuments);
    }
    async function manageSubject() {
        const ident = $('subject-filter').value;
        if (!ident) throw new Error('Create or select a subject first.');
        const selected = (await api(`/subjects/${ident}/documents`)).document_ids;
        $('subject-document-options').replaceChildren();
        for (const doc of window.allDocuments) {
            const label = document.createElement('label'); label.className = 'study-check';
            const input = document.createElement('input'); input.type = 'checkbox'; input.value = doc.id; input.checked = selected.includes(doc.id);
            label.append(input, document.createTextNode(doc.filename)); $('subject-document-options').append(label);
        }
        $('subject-dialog').showModal();
    }
    window.studySaveAttempt = safeAction(async () => {
        if (!window.currentQuizId || window.studyAttemptSaved) return;
        const quizId = window.currentQuizId;
        window.studyAttemptSaved = true;
        try {
            const answers = Object.fromEntries(Object.entries(window.quizUserAnswers).map(([index, value]) => [index, value.chosen]));
            await post('/study/attempts', { quiz_id: quizId, answers });
            notify('Quiz result saved to your study progress.', 'success');
            await loadProgress();
        } catch (error) { window.studyAttemptSaved = false; throw error; }
    });
    window.studyBeginRetake = async () => {
        try {
            if (window.currentQuizId) {
                const result = await post(`/study/quizzes/${window.currentQuizId}/retake`, {});
                window.currentQuizId = result.quiz_id;
            }
            window.studyAttemptSaved = false;
            return true;
        } catch (error) { notify(error.message, 'error'); return false; }
    };
    async function loadProgress() {
        if (!docId()) return;
        const openDoc = docId(), data = await api(`/documents/${openDoc}/progress`);
        if (docId() !== openDoc) return;
        const percentage = data.total ? Math.round(100 * data.correct / data.total) : 0;
        $('study-progress').innerHTML = `<div class="study-stat">${percentage}%</div><p>${data.attempt_count} saved attempts · ${data.correct} correct out of ${data.total} answers</p>` +
            (data.topics.length ? `<table class="study-table"><thead><tr><th>Topic</th><th>Correct</th><th>Accuracy</th></tr></thead><tbody>${data.topics.map(t => `<tr><td>${esc(t.topic)}</td><td>${t.correct}/${t.total}</td><td>${t.accuracy}%</td></tr>`).join('')}</tbody></table>` : '<p>Complete a quiz to see topic strengths and areas to revise.</p>') +
            (data.attempts.length ? `<details><summary>Recent attempts</summary>${data.attempts.slice(0, 10).map(a => `<p>${esc(a.created_at)} · ${a.correct}/${a.total}</p>`).join('')}</details>` : '');
    }
    async function loadCards() {
        if (!docId()) return;
        const openDoc = docId(), result = await api(`/documents/${openDoc}/flashcards?due_only=true`);
        if (openDoc !== docId()) return;
        state.cards = result.cards; state.cardIndex = 0; showCard();
    }
    function showCard() {
        const card = state.cards[state.cardIndex], target = $('flashcard-review');
        if (!card) { target.innerHTML = '<p>No cards are due. Create cards from a completed quiz or generate new cards.</p>'; return; }
        target.innerHTML = `<p>Due card ${state.cardIndex + 1} of ${state.cards.length}</p><div class="flashcard-front" dir="auto">${esc(card.question)}</div><button id="card-reveal" type="button">Show answer</button><div id="card-back" class="hidden"><div class="flashcard-answer" dir="auto">${esc(card.answer)}</div>${card.source_quote ? `<blockquote class="quiz-source-quote">${esc(card.source_quote)}</blockquote>` : ''}<p>Source page ${card.source_page || 1}</p><div class="study-row">${['again','hard','good','easy'].map(r => `<button type="button" data-rating="${r}">${r[0].toUpperCase() + r.slice(1)}</button>`).join('')}</div></div>`;
        $('card-reveal').onclick = () => { $('card-back').classList.remove('hidden'); $('card-reveal').hidden = true; };
        target.querySelectorAll('[data-rating]').forEach(button => button.onclick = safeAction(async () => {
            target.querySelectorAll('[data-rating]').forEach(b => b.disabled = true);
            await post(`/flashcards/${card.id}/review`, { rating: button.dataset.rating });
            state.cardIndex++; showCard();
        }));
    }
    async function usage() {
        const data = await api('/ai/usage');
        $('ai-usage').innerHTML = data.providers.map(provider => `<p><strong>${esc(provider.provider)}</strong> · ${!provider.configured ? 'No key configured' : !provider.confirmed_free ? 'Free-tier confirmation needed in setup' : `${provider.requests}/${provider.daily_limit} local daily requests`}${provider.blocked_until * 1000 > Date.now() ? ' · Waiting for quota reset' : ''}</p>`).join('');
    }
    async function versions() {
        if (!docId()) return;
        const openDoc = docId(), data = await api(`/documents/${openDoc}/notes/versions`);
        if (openDoc !== docId()) return;
        $('notes-versions').replaceChildren(new Option('Choose saved version', ''));
        data.versions.forEach(v => $('notes-versions').add(new Option(`${v.label} · ${v.created_at}`, v.id)));
    }
    function editorTarget() {
        const notes = window.activeNotesData;
        return notes?.dual_notes ? notes.dual_notes[$('editor-view').value] : notes;
    }
    function editorSections() {
        const target = editorTarget();
        if (!target?.sections?.length) throw new Error('Generate or restore study notes first.');
        $('editor-section').replaceChildren();
        target.sections.forEach((section, index) => $('editor-section').add(new Option(section.heading || `Section ${index + 1}`, index)));
        fillEditor();
    }
    function fillEditor() {
        const section = editorTarget()?.sections?.[Number($('editor-section').value)];
        if (!section) return;
        $('editor-heading').value = section.heading || '';
        $('editor-content').value = section.content || section.explanation || '';
        $('editor-bullets').value = (section.bullets || []).join('\n');
        $('editor-tip').value = section.tip || '';
    }
    async function saveEditedNotes() {
        const target = editorTarget(), section = target.sections[Number($('editor-section').value)];
        section.heading = $('editor-heading').value.trim(); section.content = $('editor-content').value;
        section.bullets = $('editor-bullets').value.split('\n').map(v => v.trim()).filter(Boolean); section.tip = $('editor-tip').value;
        if (window.activeNotesData.dual_notes && $('editor-view').value === 'original') window.activeNotesData.sections = target.sections;
        await post(`/documents/${docId()}/notes/versions`, { notes: window.activeNotesData, label: 'Edited section: ' + section.heading.slice(0, 80) });
        renderNotes(window.activeNotesData); await versions(); $('editor-status').textContent = 'Saved as a new version. Earlier versions remain available.';
    }
    async function regenerateSection() {
        const target = editorTarget(), section = target.sections[Number($('editor-section').value)];
        const openDoc = docId(); $('editor-regenerate').disabled = true; $('editor-status').textContent = 'Regenerating only this section…';
        try {
            const result = await post(`/documents/${openDoc}/notes/retry?background=true`, {
                section_indices: [Number(section.number || Number($('editor-section').value) + 1)], existing_notes: target,
                detail_level: $('notes-detail-select').value,
                language: $('editor-view').value === 'english' && window.activeNotesData.dual_notes ? 'en' : (target.language || window.activeDocumentLanguage || 'en')
            });
            const finished = result.job_id ? await pollNotesJob(openDoc, result.job_id, job => { $('editor-status').textContent = job.current_step || 'Regenerating…'; }) : result;
            if (docId() !== openDoc) return;
            if (window.activeNotesData.dual_notes) {
                window.activeNotesData.dual_notes[$('editor-view').value] = finished.notes;
                if ($('editor-view').value === 'original') window.activeNotesData.sections = finished.notes.sections;
            } else window.activeNotesData = finished.notes;
            await post(`/documents/${openDoc}/notes/versions`, { notes: window.activeNotesData, label: 'Regenerated selected section' });
            renderNotes(window.activeNotesData); await versions(); editorSections(); $('editor-status').textContent = 'Section regenerated and saved as a new version.';
        } finally { $('editor-regenerate').disabled = false; }
    }
    async function previewPdf(page = 1, excerpt = '', documentId = docId()) {
        if (!documentId) return;
        const response = await fetch(`${API_BASE_URL}/api/documents/${documentId}/pages/${page}?excerpt=${encodeURIComponent(excerpt.slice(0, 350))}`);
        if (!response.ok) await readApiResponse(response);
        const blob = await response.blob();
        if (state.pdfUrl) URL.revokeObjectURL(state.pdfUrl);
        state.pdfUrl = URL.createObjectURL(blob); state.pdfDocument = documentId;
        state.pdfPage = page; state.pdfPages = Number(response.headers.get('X-Page-Count') || page);
        $('pdf-page').value = page; $('pdf-page').max = state.pdfPages;
        $('pdf-page-image').src = state.pdfUrl; $('pdf-preview').classList.remove('hidden');
        $('pdf-evidence-status').textContent = `Page ${page} of ${state.pdfPages}` + (excerpt ? response.headers.get('X-Evidence-Highlighted') === 'true' ? ' · Supporting text highlighted' : ' · Read the cited text alongside this page' : '');
    }
    window.studyPreviewCitation = safeAction(async citation => {
        const targetDoc = citation.document_id || docId();
        document.getElementById('tab-btn-document').click();
        const target = window.allDocuments.find(d => d.id === targetDoc);
        if (target?.file_type === 'pdf') {
            await previewPdf(Number(citation.page_number) || 1, citation.excerpt || '', targetDoc);
            $('pdf-preview').scrollIntoView({ block: 'nearest' });
        } else if (targetDoc !== docId() && target) {
            await openDocument(target.id, target.filename, Math.round(target.file_size / 1024));
        }
        const chunk = [...viewerContent.querySelectorAll('.viewer-chunk')].find(el =>
            citation.chunk_index != null ? el.dataset.chunkIndex === String(citation.chunk_index) : el.dataset.pageNumber === String(citation.page_number));
        if (chunk && targetDoc === docId()) { chunk.tabIndex = -1; chunk.focus({ preventScroll: true }); chunk.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
    });
    window.addEventListener('document-opened', safeAction(async () => {
        const openDoc = docId();
        state.sessionId = null; state.scope = []; $('pdf-preview').classList.add('hidden');
        $('notes-editor').close();
        window.activeNotesData = null; $('tab-notes-notebook')?.replaceChildren();
        renderScope();
        await Promise.allSettled([loadSessions(), loadProgress(), loadCards(), versions()]);
        if (docId() !== openDoc) return;
        const saved = $('notes-versions').options[1];
        if (saved) {
            const result = await api(`/documents/${openDoc}/notes/versions/${saved.value}`);
            if (docId() === openDoc) { renderNotes(result.notes); $('notes-versions').value = saved.value; }
        }
    }));
    window.addEventListener('library-loaded', renderScope);
    window.addEventListener('notes-generated', safeAction(async event => {
        if (!event.detail.persisted) await post(`/documents/${event.detail.documentId}/notes/versions`, { notes: event.detail.notes, label: 'Generated study notes' });
        if (event.detail.documentId === docId()) await versions();
    }));
    document.addEventListener('DOMContentLoaded', () => {
        bind('subject-filter', 'change', filterSubject);
        bind('subject-create', 'click', async () => {
            const name = prompt('Subject name (for example, Operating Systems):'); if (!name?.trim()) return;
            const subject = await post('/subjects', { name: name.trim() }); await loadSubjects(); $('subject-filter').value = subject.id; await filterSubject(); await manageSubject();
        });
        bind('subject-manage', 'click', manageSubject);
        bind('subject-save', 'click', async () => {
            const ids = [...$('subject-document-options').querySelectorAll('input:checked')].map(i => i.value);
            await api(`/subjects/${$('subject-filter').value}/documents`, { method: 'PUT', body: JSON.stringify({ document_ids: ids }) });
            $('subject-dialog').close(); await loadSubjects(); await filterSubject();
        });
        bind('chat-new', 'click', async () => { window.studyStopChat(); state.sessionId = null; $('chat-sessions').value = ''; welcome(); });
        bind('chat-sessions', 'change', async () => { window.studyStopChat(); await restoreSession($('chat-sessions').value); });
        bind('chat-stop', 'click', window.studyStopChat);
        bind('tab-btn-study', 'click', async () => { await Promise.all([loadProgress(), loadCards(), usage()]); });
        bind('cards-from-mistakes', 'click', async () => { const result = await post(`/documents/${docId()}/flashcards/from-mistakes`, {}); notify(`${result.added} cards added.`, 'success'); await loadCards(); });
        bind('cards-generate', 'click', async () => {
            $('cards-generate').disabled = true;
            try { const result = await post(`/documents/${docId()}/flashcards/generate`, { count: 8 }); notify(`${result.added} cards added. ${result.message}`); await loadCards(); }
            finally { $('cards-generate').disabled = false; }
        });
        bind('cards-refresh', 'click', loadCards); bind('usage-refresh', 'click', usage);
        bind('notes-versions', 'change', async () => {
            const openDoc = docId(), version = $('notes-versions').value;
            if (!version) return;
            const result = await api(`/documents/${openDoc}/notes/versions/${version}`);
            if (docId() === openDoc && $('notes-versions').value === version) renderNotes(result.notes);
        });
        bind('notes-edit-open', 'click', () => { $('editor-view').value = 'original'; $('editor-view').disabled = !window.activeNotesData?.dual_notes; editorSections(); $('editor-status').textContent = ''; $('notes-editor').showModal(); });
        bind('editor-view', 'change', editorSections); bind('editor-section', 'change', fillEditor);
        bind('editor-save', 'click', saveEditedNotes); bind('editor-regenerate', 'click', regenerateSection);
        bind('pdf-preview-toggle', 'click', async () => { if (!$('pdf-preview').classList.contains('hidden')) $('pdf-preview').classList.add('hidden'); else await previewPdf(1); });
        bind('pdf-prev', 'click', () => previewPdf(Math.max(1, state.pdfPage - 1), '', state.pdfDocument));
        bind('pdf-next', 'click', () => previewPdf(Math.min(state.pdfPages, state.pdfPage + 1), '', state.pdfDocument));
        bind('pdf-page', 'change', () => previewPdf(Math.max(1, Math.min(state.pdfPages, Number($('pdf-page').value) || 1)), '', state.pdfDocument));
        safeAction(loadSubjects)();
    });
})();
