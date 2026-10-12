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

// ── Wire up button after DOM ready ──────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const btnMakeNotes = document.getElementById('btn-make-notes');
    if (btnMakeNotes) {
        btnMakeNotes.addEventListener('click', handleMakeNotes);
    }
    if (notesBtnClose) {
        notesBtnClose.addEventListener('click', () => {
            notesModal.style.display = 'none';
        });
    }
    if (notesBtnPrint) {
        notesBtnPrint.addEventListener('click', () => window.print());
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

    showNotesLoading(true);

    try {
        // Step 1: Request backend to generate notes
        setStep('🤖 Generating notes with AI...');
        const baseUrl = (typeof API_BASE_URL !== 'undefined') ? API_BASE_URL : '';
        const res = await fetch(`${baseUrl}/api/documents/${docId}/notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
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
    notesNotebook.innerHTML = '';

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

    // Header
    page.insertAdjacentHTML('beforeend', `
        <div class="nf-page-header">
            <div class="nf-subject">${esc(data.subject || 'Study Notes')} ✱</div>
            <div class="nf-title">${esc(data.title)}</div>
            ${data.quote ? `<div class="nf-quote">"${esc(data.quote)}"</div>` : ''}
        </div>
    `);

    // Sections
    data.sections.forEach((sec, i) => {
        page.appendChild(buildSection(sec, i));
    });

    // Footer
    if ((data.keyTakeaways && data.keyTakeaways.length) || (data.remember && data.remember.length)) {
        page.appendChild(buildFooter(data.keyTakeaways, data.remember));
    }

    wrap.appendChild(page);
    notesNotebook.appendChild(wrap);
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
            <div class="nf-heading">${esc(sec.heading)}</div>
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
        tip.innerHTML = `<span>💡</span><span>${esc(sec.tip)}</span>`;
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
    p.innerHTML = esc(content).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    return p;
}

function buildBullets(items) {
    const ul = document.createElement('ul');
    ul.className = 'nf-bullets';
    items.forEach(b => {
        const li = document.createElement('li');
        li.innerHTML = esc(b).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        ul.appendChild(li);
    });
    return ul;
}

function buildKeyBox(kb) {
    const box = document.createElement('div');
    box.className = 'nf-key';
    box.innerHTML = `<div class="nf-key-title">${esc(kb.title || '⭐ Key Concept')}</div>`;
    const ul = document.createElement('ul');
    (kb.items || []).forEach(item => {
        const li = document.createElement('li');
        li.innerHTML = esc(item).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        ul.appendChild(li);
    });
    box.appendChild(ul);
    return box;
}

function buildComparison(cmp) {
    const box = document.createElement('div');
    box.className = 'nf-cmp';

    const left = document.createElement('div');
    left.className = 'nf-cmp-col';
    left.innerHTML = `<div class="nf-cmp-title">${esc(cmp.left.title)}</div>`;
    const lu = document.createElement('ul');
    (cmp.left.items || []).forEach(i => { const li = document.createElement('li'); li.textContent = i; lu.appendChild(li); });
    left.appendChild(lu);

    const divider = document.createElement('div');
    divider.className = 'nf-cmp-div';

    const right = document.createElement('div');
    right.className = 'nf-cmp-col';
    right.innerHTML = `<div class="nf-cmp-title">${esc(cmp.right.title)}</div>`;
    const ru = document.createElement('ul');
    (cmp.right.items || []).forEach(i => { const li = document.createElement('li'); li.textContent = i; ru.appendChild(li); });
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
        box.innerHTML = '<h3>✅ Key Takeaways</h3>';
        const ul = document.createElement('ul');
        takeaways.forEach(t => { const li = document.createElement('li'); li.textContent = t; ul.appendChild(li); });
        box.appendChild(ul);
        footer.appendChild(box);
    }

    if (remember && remember.length) {
        const box = document.createElement('div');
        box.className = 'nf-remember';
        box.innerHTML = '<h3>⭐ Remember</h3>';
        const ul = document.createElement('ul');
        remember.forEach(r => { const li = document.createElement('li'); li.textContent = r; ul.appendChild(li); });
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
