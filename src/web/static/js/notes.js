/* ============================================================
   notes.js — Handwritten Notes feature for the RAG Workspace
   Hooks into the existing app via activeDocumentId global
   ============================================================ */
// Notes generation is securely handled by the backend API (/api/documents/{id}/notes)

// DOM refs
const notesModal = document.getElementById('notes-modal');
const notesLoading = document.getElementById('notes-loading');
const notesNotebook = document.getElementById('notes-notebook');
const notesBtnClose = document.getElementById('notes-btn-close');
const notesBtnPrint = document.getElementById('notes-btn-print');
const notesLoadingStep = document.getElementById('notes-loading-step');
const tabNotesNotebook = document.getElementById('tab-notes-notebook');
const tabNotesEmpty = document.getElementById('tab-notes-empty');
const tabBtnGenerateNotes = document.getElementById('tab-btn-generate-notes');
const tabBtnPrintNotes = document.getElementById('tab-btn-print-notes');

const LANGUAGE_DISPLAY_NAMES = {
    'en': 'English',
    'hi': 'Hindi',
    'es': 'Spanish',
    'ar': 'Arabic',
    'zh': 'Chinese',
    'ja': 'Japanese',
    'fr': 'French',
    'de': 'German',
    'ru': 'Russian',
    'ta': 'Tamil',
    'te': 'Telugu',
    'bn': 'Bengali',
    'mr': 'Marathi',
    'gu': 'Gujarati',
    'kn': 'Kannada',
    'ml': 'Malayalam',
    'pa': 'Punjabi',
    'ur': 'Urdu',
    'pt': 'Portuguese',
    'it': 'Italian'
};

function updateNotesLanguageSelector(langCode) {
    const langSelect = document.getElementById('notes-lang-select');
    if (!langSelect) return;

    const code = (langCode || 'en').toLowerCase().trim();
    langSelect.innerHTML = '';

    if (code === 'en') {
        const opt = document.createElement('option');
        opt.value = 'en';
        opt.textContent = 'English';
        langSelect.appendChild(opt);
    } else {
        const langName = LANGUAGE_DISPLAY_NAMES[code] || code.toUpperCase();

        const optBoth = document.createElement('option');
        optBoth.value = 'both';
        optBoth.textContent = `Both (${langName} & English)`;
        optBoth.selected = true;

        const optOriginal = document.createElement('option');
        optOriginal.value = 'original';
        optOriginal.textContent = `Original (${langName})`;

        const optEnglish = document.createElement('option');
        optEnglish.value = 'en';
        optEnglish.textContent = 'English';

        langSelect.appendChild(optBoth);
        langSelect.appendChild(optOriginal);
        langSelect.appendChild(optEnglish);
    }
}
window.updateNotesLanguageSelector = updateNotesLanguageSelector;

// ── Wire up button after DOM ready ──────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    updateNotesLanguageSelector(window.activeDocumentLanguage || 'en');

    const btnMakeNotes = document.getElementById('btn-make-notes');
    if (btnMakeNotes) {
        btnMakeNotes.addEventListener('click', handleMakeNotes);
    }
    if (tabBtnGenerateNotes) {
        tabBtnGenerateNotes.addEventListener('click', handleMakeNotes);
    }
    if (notesBtnClose) {
        notesBtnClose.addEventListener('click', () => {
            notesModal.style.display = 'none';
        });
    }
    if (notesBtnPrint) {
        notesBtnPrint.addEventListener('click', () => window.print());
    }
    if (tabBtnPrintNotes) {
        tabBtnPrintNotes.addEventListener('click', () => window.print());
    }
    if (notesModal) {
        notesModal.addEventListener('click', (e) => {
            if (e.target === notesModal) {
                notesModal.style.display = 'none';
            }
        });
    }
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && notesModal && notesModal.style.display === 'block') {
            notesModal.style.display = 'none';
        }
    });
});

// ── Main handler ─────────────────────────────────────────────
async function handleMakeNotes() {
    const docId = window.activeDocumentId || (typeof activeDocumentId !== 'undefined' ? activeDocumentId : null);
    if (!docId) {
        alert('Please select a document from the left library first.');
        return;
    }

    const detailSelect = document.getElementById('notes-detail-select');
    const langSelect = document.getElementById('notes-lang-select');
    const detailLevel = detailSelect ? detailSelect.value : 'standard';
    const notesLang = langSelect ? langSelect.value : 'original';

    showNotesLoading(true);

    try {
        // Step 1: Request backend to generate notes
        setStep('🤖 Generating notes with AI...');
        const baseUrl = (typeof API_BASE_URL !== 'undefined') ? API_BASE_URL : '';
        const res = await fetch(`${baseUrl}/api/documents/${docId}/notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                detail_level: detailLevel,
                language: notesLang
            })
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || errData.error || `HTTP ${res.status}`);
        }
        const data = await res.json();
        if (!data.notes) {
            throw new Error(data.error || 'Failed to generate notes. Check GEMINI_API_KEY.');
        }

        // Step 2: render
        setStep('🎨 Rendering your handwritten notes...');
        await sleep(300);

        renderNotes(data.notes);
        showNotesLoading(false);

        // Switch workspace view to Study Notes tab if available
        const tabBtnNotes = document.getElementById('tab-btn-notes');
        const panelNotes = document.getElementById('tab-panel-notes');
        const panelDoc = document.getElementById('tab-panel-document');
        const panelQuiz = document.getElementById('tab-panel-quiz');
        const tabBtnDoc = document.getElementById('tab-btn-document');
        const tabBtnQuiz = document.getElementById('tab-btn-quiz');

        if (tabBtnNotes && panelNotes) {
            [tabBtnDoc, tabBtnQuiz, tabBtnNotes].forEach(b => {
                if (b) {
                    b.classList.toggle('active', b === tabBtnNotes);
                    b.setAttribute('aria-selected', b === tabBtnNotes ? 'true' : 'false');
                }
            });
            [panelDoc, panelQuiz, panelNotes].forEach(p => {
                if (p) {
                    p.classList.toggle('hidden', p !== panelNotes);
                }
            });
        }

        notesModal.style.display = 'block';

    } catch (err) {
        showNotesLoading(false);
        alert('Notes Error: ' + err.message);
        console.error(err);
    }
}

// ── Gemini Call with multi-model fallback ───────────────────
async function callGemini(text, docTitle) {
    const MAX_CHARS = 14000;
    const truncated = text.length > MAX_CHARS
        ? text.slice(0, MAX_CHARS) + '\n\n[Document truncated]'
        : text;

    const prompt = buildPrompt(truncated, docTitle);
    let lastError = null;

    for (const model of CANDIDATE_MODELS) {
        for (let attempt = 1; attempt <= 2; attempt++) {
            setStep(`🤖 Generating notes with AI (${model})...`);
            const url = `https://openrouter.ai/api/v1/chat/completions`;

            try {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${GEMINI_API_KEY}`,
                        'HTTP-Referer': window.location.href,
                        'X-Title': 'RAG System'
                    },
                    body: JSON.stringify({
                        model: model,
                        messages: [{ role: 'user', content: prompt }],
                        temperature: 0.4,
                        max_tokens: 4096
                    })
                });

                if (res.ok) {
                    const data = await res.json();
                    const raw = data?.choices?.[0]?.message?.content || '';
                    return parseJSON(raw);
                }

                const errData = await res.json().catch(() => ({}));
                const errMsg = errData?.error?.message || `HTTP ${res.status}`;
                lastError = new Error(errMsg);

                // If high demand or overloaded, try next model or retry
                if (res.status === 503 || res.status === 429) {
                    setStep(`⏳ Server busy on ${model}, trying alternate model...`);
                    await sleep(1000);
                    break; // Move to next model
                }
            } catch (networkErr) {
                lastError = networkErr;
                await sleep(1000);
            }
        }
    }

    throw lastError || new Error('Unable to connect to Groq API. Please check your network or try again.');
}

// ── Prompt Builder ───────────────────────────────────────────
function buildPrompt(text, docTitle) {
    const titleHint = docTitle ? `Title suggestion: "${docTitle}"` : '';
    return `You are an expert student note-maker. Generate structured study notes in JSON from the document below.
${titleHint}

RULES:
1. Use ONLY information from the document.
2. Return ONLY valid JSON — no markdown fences.
3. Generate 5-8 sections.
4. For "color": use one of: green, blue, red, orange, purple, teal (alternate them).
5. For "layout": "full" (text+bullets), "split" (text+bullets LEFT, keyBox RIGHT), "comparison" (two-column compare).

JSON structure:
{
  "title": "Topic Title",
  "subject": "Subject Name",
  "quote": "Key quote under 100 chars",
  "sections": [
    {
      "number": 1,
      "heading": "Section Heading",
      "color": "green",
      "layout": "split",
      "content": "1-3 sentence explanation. Use **bold** for key terms.",
      "bullets": ["Point one", "Point two"],
      "keyBox": { "title": "⭐ Key Idea", "items": ["item 1", "item 2"] },
      "comparison": null,
      "tip": "Remember: important tip"
    }
  ],
  "keyTakeaways": ["Takeaway 1", "Takeaway 2", "Takeaway 3"],
  "remember": ["Fact 1", "Fact 2"]
}

For comparison layout set "comparison": {"left":{"title":"A","items":[...]},"right":{"title":"B","items":[...]}} and "bullets": null, "keyBox": null.

DOCUMENT:
${text}

Return ONLY the JSON object.`;
}


function parseJSON(raw) {
    let s = String(raw || '').trim();

    // Remove Markdown code fences if Gemini adds them.
    s = s
        .replace(/^```(?:json)?\s*/i, '')
        .replace(/\s*```\s*$/i, '')
        .trim();

    // Extract the outer JSON object.
    const start = s.indexOf('{');
    const end = s.lastIndexOf('}');

    if (start === -1 || end === -1 || end <= start) {
        throw new Error('AI did not return a JSON object. Please try again.');
    }

    s = s.slice(start, end + 1);

    try {
        const data = JSON.parse(s);

        if (!data.title || !Array.isArray(data.sections) || !data.sections.length) {
            throw new Error('AI returned incomplete notes. Try again.');
        }

        return data;
    } catch (error) {
        console.error('Invalid Gemini JSON:', s);
        console.error('JSON parsing error:', error);

        throw new Error(
            'Gemini returned malformed JSON. Please generate the notes again.'
        );
    }
}
// ── Notes Renderer ───────────────────────────────────────────
function renderNotes(data) {
    if (!data) return;
    window.activeNotesData = data;

    if (tabNotesEmpty) {
        tabNotesEmpty.style.display = 'none';
    }

    const targets = [notesNotebook, tabNotesNotebook].filter(Boolean);
    targets.forEach(container => {
        container.innerHTML = '';
        container.appendChild(createNotebookElement(data));
    });
}

function createNotebookElement(data) {
    // Outer notebook wrapper with shadow
    const wrap = document.createElement('div');
    wrap.style.cssText = 'position:relative;filter:drop-shadow(0 16px 48px rgba(0,0,0,.5));';

    // Spiral rings
    const spiral = document.createElement('div');
    spiral.className = 'nf-spiral';
    for (let i = 0; i < 28; i++) {
        const r = document.createElement('div');
        r.className = 'nf-ring';
        spiral.appendChild(r);
    }

    // Page
    const page = document.createElement('div');
    page.className = 'nf-page';
    page.appendChild(spiral);

    // Coverage Bar
    const coverage = data.coverage;
    let coverageHtml = '';
    if (coverage) {
        const isFull = !coverage.failed_sections || coverage.failed_sections.length === 0;
        coverageHtml = `
            <div class="nf-coverage-bar ${isFull ? 'nf-coverage-success' : 'nf-coverage-warning'}" id="notes-coverage-bar">
                <div class="nf-coverage-row">
                    <span class="nf-coverage-badge">
                        ${isFull ? '📘' : '⚠️'} ${esc(coverage.coverage_text || '')}
                    </span>
                </div>
                ${!isFull && coverage.skipped_pages_text ? `
                    <div class="nf-skipped-row">
                        <span class="nf-skipped-text">${esc(coverage.skipped_pages_text)}</span>
                        <button class="nf-btn-retry" type="button" title="Retry only the skipped sections">
                            🔄 Retry Skipped Sections (${coverage.failed_sections.length})
                        </button>
                    </div>
                ` : ''}
            </div>
        `;
    }

    // Header
    page.insertAdjacentHTML('beforeend', `
        <div class="nf-page-header">
            <div class="nf-subject">${esc(data.subject || 'Study Notes')} ✱</div>
            <div class="nf-title">${esc(data.title)}</div>
            ${data.quote ? `<div class="nf-quote">"${esc(data.quote)}"</div>` : ''}
            ${coverageHtml}
        </div>
    `);

    // Wire up retry button if present
    const retryBtn = page.querySelector('.nf-btn-retry');
    if (retryBtn) {
        retryBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const docId = window.activeDocumentId || (typeof activeDocumentId !== 'undefined' ? activeDocumentId : null);
            if (!docId) {
                alert('Please select a document first.');
                return;
            }
            await handleRetryFailedSections(docId, data);
        });
    }

    // Sections (Dual View or Single View)
    if (data.dual_notes) {
        const origLangName = data.dual_notes.original_lang_name || 'Original';
        const origNotes = data.dual_notes.original || data;
        const engNotes = data.dual_notes.english || data;
        const origSections = origNotes.sections || [];
        const engSections = engNotes.sections || [];

        // Dual Mode Toolbar
        const dualToolbar = document.createElement('div');
        dualToolbar.className = 'nf-dual-toolbar';
        dualToolbar.innerHTML = `
            <div class="nf-dual-tabs" role="tablist">
                <button type="button" class="nf-dual-tab-btn active" data-view="both">
                    <i class="fa-solid fa-table-columns"></i> Side-by-Side
                </button>
                <button type="button" class="nf-dual-tab-btn" data-view="original">
                    <i class="fa-solid fa-language"></i> ${esc(origLangName)}
                </button>
                <button type="button" class="nf-dual-tab-btn" data-view="english">
                    <i class="fa-solid fa-globe"></i> English
                </button>
            </div>
        `;
        page.appendChild(dualToolbar);

        const dualContainer = document.createElement('div');
        dualContainer.className = 'nf-dual-container';

        const maxSections = Math.max(origSections.length, engSections.length);
        const rowElements = [];

        for (let i = 0; i < maxSections; i++) {
            const origSec = origSections[i];
            const engSec = engSections[i];

            const row = document.createElement('div');
            row.className = 'nf-dual-row';

            const leftCol = document.createElement('div');
            leftCol.className = 'nf-dual-col nf-dual-orig';
            leftCol.setAttribute('dir', 'auto');
            leftCol.innerHTML = `<div class="nf-dual-col-header" dir="auto">${esc(origLangName)}</div>`;
            if (origSec) leftCol.appendChild(buildSection(origSec, i));

            const rightCol = document.createElement('div');
            rightCol.className = 'nf-dual-col nf-dual-eng';
            rightCol.setAttribute('dir', 'auto');
            rightCol.innerHTML = `<div class="nf-dual-col-header" dir="auto">English</div>`;
            if (engSec) rightCol.appendChild(buildSection(engSec, i));

            row.appendChild(leftCol);
            row.appendChild(rightCol);
            dualContainer.appendChild(row);
            rowElements.push({ row, leftCol, rightCol });
        }

        page.appendChild(dualContainer);

        dualToolbar.querySelectorAll('.nf-dual-tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                dualToolbar.querySelectorAll('.nf-dual-tab-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const view = btn.dataset.view;

                rowElements.forEach(({ row, leftCol, rightCol }) => {
                    if (view === 'both') {
                        row.style.gridTemplateColumns = '1fr 1fr';
                        leftCol.style.display = 'flex';
                        rightCol.style.display = 'flex';
                    } else if (view === 'original') {
                        row.style.gridTemplateColumns = '1fr';
                        leftCol.style.display = 'flex';
                        rightCol.style.display = 'none';
                    } else if (view === 'english') {
                        row.style.gridTemplateColumns = '1fr';
                        leftCol.style.display = 'none';
                        rightCol.style.display = 'flex';
                    }
                });
            });
        });
    } else {
        // Sections
        (data.sections || []).forEach((sec, i) => {
            page.appendChild(buildSection(sec, i));
        });
    }

    // Footer
    if ((data.keyTakeaways && data.keyTakeaways.length) || (data.remember && data.remember.length)) {
        page.appendChild(buildFooter(data.keyTakeaways, data.remember));
    }

    wrap.appendChild(page);
    return wrap;
}

async function handleRetryFailedSections(docId, existingNotes) {
    const coverage = existingNotes && existingNotes.coverage;
    if (!coverage || !coverage.failed_sections || !coverage.failed_sections.length) {
        return;
    }

    const sectionIndices = coverage.failed_sections.map(s => s.section_index);
    showNotesLoading(true);
    setStep(`🔄 Retrying ${sectionIndices.length} skipped section(s)...`);

    try {
        const baseUrl = (typeof API_BASE_URL !== 'undefined') ? API_BASE_URL : '';
        const res = await fetch(`${baseUrl}/api/documents/${docId}/notes/retry`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                section_indices: sectionIndices,
                existing_notes: existingNotes,
                detail_level: existingNotes.detail_level || 'standard'
            })
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || errData.error || `HTTP ${res.status}`);
        }

        const data = await res.json();
        if (data.notes) {
            renderNotes(data.notes);
        }
        showNotesLoading(false);
    } catch (err) {
        showNotesLoading(false);
        alert('Retry failed: ' + err.message);
        console.error(err);
    }
}

function buildSection(sec, idx) {
    const color = sec.color || 'green';
    const wrapper = document.createElement('div');
    wrapper.className = `nf-section nf-${color}`;
    wrapper.style.animationDelay = `${idx * 70}ms`;

    // Header row
    wrapper.innerHTML = `
        <div class="nf-sec-header">
            <div class="nf-num">${sec.number || idx + 1}</div>
            <div class="nf-heading" dir="auto">${esc(sec.heading)}</div>
        </div>
    `;

    // Body
    const body = document.createElement('div');
    body.className = 'nf-body' + (sec.layout === 'split' && sec.keyBox ? ' split' : '');

    if (sec.layout === 'comparison' && sec.comparison) {
        body.appendChild(buildComparison(sec.comparison));
    } else if (sec.layout === 'split' && sec.keyBox) {
        const left = document.createElement('div');
        if (sec.content) left.appendChild(buildText(sec.content));
        if (sec.bullets && sec.bullets.length) left.appendChild(buildBullets(sec.bullets));
        body.appendChild(left);
        body.appendChild(buildKeyBox(sec.keyBox));
    } else {
        if (sec.content) body.appendChild(buildText(sec.content));
        if (sec.bullets && sec.bullets.length) body.appendChild(buildBullets(sec.bullets));
        if (sec.keyBox) body.appendChild(buildKeyBox(sec.keyBox));
    }

    if (sec.tip) {
        const tip = document.createElement('div');
        tip.className = 'nf-tip';
        tip.setAttribute('dir', 'auto');
        tip.innerHTML = `<span>💡</span><span dir="auto">${esc(sec.tip)}</span>`;
        body.appendChild(tip);
    }

    wrapper.appendChild(body);

    const hr = document.createElement('hr');
    hr.className = 'nf-divider';
    wrapper.appendChild(hr);

    return wrapper;
}

function buildText(content) {
    const p = document.createElement('p');
    p.className = 'nf-text';
    p.setAttribute('dir', 'auto');
    p.innerHTML = esc(content).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    return p;
}

function buildBullets(items) {
    const ul = document.createElement('ul');
    ul.className = 'nf-bullets';
    ul.setAttribute('dir', 'auto');
    items.forEach(b => {
        const li = document.createElement('li');
        li.setAttribute('dir', 'auto');
        li.innerHTML = esc(b).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        ul.appendChild(li);
    });
    return ul;
}

function buildKeyBox(kb) {
    const box = document.createElement('div');
    box.className = 'nf-key';
    box.setAttribute('dir', 'auto');
    box.innerHTML = `<div class="nf-key-title" dir="auto">${esc(kb.title || '⭐ Key Concept')}</div>`;
    const ul = document.createElement('ul');
    ul.setAttribute('dir', 'auto');
    (kb.items || []).forEach(item => {
        const li = document.createElement('li');
        li.setAttribute('dir', 'auto');
        li.innerHTML = esc(item).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        ul.appendChild(li);
    });
    box.appendChild(ul);
    return box;
}

function buildComparison(cmp) {
    const box = document.createElement('div');
    box.className = 'nf-cmp';
    box.setAttribute('dir', 'auto');

    const left = document.createElement('div');
    left.className = 'nf-cmp-col';
    left.setAttribute('dir', 'auto');
    left.innerHTML = `<div class="nf-cmp-title" dir="auto">${esc(cmp.left.title)}</div>`;
    const lu = document.createElement('ul');
    lu.setAttribute('dir', 'auto');
    (cmp.left.items || []).forEach(i => { const li = document.createElement('li'); li.setAttribute('dir', 'auto'); li.textContent = i; lu.appendChild(li); });
    left.appendChild(lu);

    const divider = document.createElement('div');
    divider.className = 'nf-cmp-div';

    const right = document.createElement('div');
    right.className = 'nf-cmp-col';
    right.setAttribute('dir', 'auto');
    right.innerHTML = `<div class="nf-cmp-title" dir="auto">${esc(cmp.right.title)}</div>`;
    const ru = document.createElement('ul');
    ru.setAttribute('dir', 'auto');
    (cmp.right.items || []).forEach(i => { const li = document.createElement('li'); li.setAttribute('dir', 'auto'); li.textContent = i; ru.appendChild(li); });
    right.appendChild(ru);

    box.appendChild(left); box.appendChild(divider); box.appendChild(right);
    return box;
}

function buildFooter(takeaways, remember) {
    const footer = document.createElement('div');
    footer.className = 'nf-footer';

    if (takeaways && takeaways.length) {
        const box = document.createElement('div');
        box.className = 'nf-takeaway';
        box.setAttribute('dir', 'auto');
        box.innerHTML = '<h3 dir="auto">✅ Key Takeaways</h3>';
        const ul = document.createElement('ul');
        ul.setAttribute('dir', 'auto');
        takeaways.forEach(t => { const li = document.createElement('li'); li.setAttribute('dir', 'auto'); li.textContent = t; ul.appendChild(li); });
        box.appendChild(ul);
        footer.appendChild(box);
    }

    if (remember && remember.length) {
        const box = document.createElement('div');
        box.className = 'nf-remember';
        box.setAttribute('dir', 'auto');
        box.innerHTML = '<h3 dir="auto">⭐ Remember</h3>';
        const ul = document.createElement('ul');
        ul.setAttribute('dir', 'auto');
        remember.forEach(r => { const li = document.createElement('li'); li.setAttribute('dir', 'auto'); li.textContent = r; ul.appendChild(li); });
        box.appendChild(ul);
        footer.appendChild(box);
    }

    return footer;
}

// ── Helpers ──────────────────────────────────────────────────
function showNotesLoading(show) {
    notesLoading.style.display = show ? 'flex' : 'none';
}

function setStep(text) {
    notesLoadingStep.textContent = text;
}

function esc(str) {
    if (typeof str !== 'string') return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
