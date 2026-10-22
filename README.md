# Workspace — AI Document Intelligence & Study Platform

An AI Document Workspace built with **FastAPI**, **SQLite**, **Gemini/Groq/OpenRouter**, local sentence-transformer embeddings, and vanilla JavaScript. Transform your documents (PDF, TXT, DOCX, CSV) into interactive study companions with contextual retrieval-augmented generation (RAG), automated quiz generation, and realistic handwritten study notes.

---

## ✨ Features & Capabilities

### 🎨 Design System & Aesthetics
- **Design Tokens**: Modular CSS variables spanning brand gradients (`#4F46E5` &rarr; `#7C3AED` &rarr; `#EC4899`), glassmorphism surfaces (`backdrop-filter: blur(16px)`), spacing scale, typography, and layered shadows.
- **Dark & Light Modes**: Instant theme toggle with `localStorage` persistence and automatic synchronization with system `prefers-color-scheme`.
- **Animated Aurora Mesh**: Smooth, GPU-composited radial mesh gradient background for visual depth without layout thrashing.
- **Modern Typography**: Inter and Plus Jakarta Sans for UI elements, paired with JetBrains Mono for document IDs and code blocks.

### 📐 Ergonomic 3-Column Workspace Shell
- **Collapsible Sidebar**: Smooth width transitions, document dropzone with animated upload progress bar, and real-time library search filter.
- **Document & Quiz Tabs**: Seamless tab switcher (`Document | Quiz Maker | Study Notes | Study`) keeping all workflows centralized and focused.
- **Draggable AI Panel Resizer**: Interactive horizontal resize handle with width persistence across browser sessions.
- **Full Responsiveness**: Mobile-optimized shell with drawer navigation and full-width card stacks.

### 📄 Smart Document Viewer
- **Staggered Chunks**: Cards reveal smoothly with colored status markers, source page pills, and chunk indices.
- **In-Document Search**: High-performance debounced text search with real-time match counter pill and `<mark>` highlights.
- **Reading Progress Bar**: Subtle gradient progress bar anchored to the top of the viewer.
- **Quick Chunk Actions**: One-click "Copy chunk" and "Ask AI about this chunk" actions on every section.
- **Floating Scroll-to-Top**: Quick return to the document header.

### 🎓 Interactive Quiz Maker
- **Custom Segmented Controls**: Quick-select buttons for question counts (`5 | 10 | 15 | 20`) and difficulty (`Mixed | Easy | Medium | Hard`).
- **Interactive Question Cards**: Instant visual feedback (pulse green for correct, shake red for wrong), navigator pill badges, and expandable source citations.
- **Results & Mastery Review**: Circular SVG score counter animation, celebratory canvas confetti burst, and Retry / New Quiz workflows.

### 🤖 AI Assistant & Study Notes
- **Contextual Chat**: Grounded Q&A against document chunks via Gemini RAG.
- **Rich Message Actions**: Markdown rendering, code block copy button, provider answer streaming with a Stop button, suggested-question chips, copy response, and regenerate reply.
- **Handwritten Study Notes**: Realistic lined-paper notebook generation with customizable color themes and print/PDF export.

### ⚡ Delight & Keyboard Shortcuts
- **Command Palette (`Ctrl+K`)**: Rapidly switch documents, toggle themes, or jump to quizzes and summaries from a floating palette.
- **Shortcuts Modal (`?`)**: Quick on-screen modal documenting keyboard shortcuts.
- **Toast Notifications**: Non-intrusive alert toast system (`window.showToast()`) with auto-dismiss timers and pause-on-hover.
- **Accessibility & Motion**: Full ARIA roles, `aria-live` screen-reader regions, and strict adherence to `prefers-reduced-motion: reduce`.

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| <kbd>Ctrl</kbd> + <kbd>K</kbd> | Open Command Palette |
| <kbd>?</kbd> | Open Keyboard Shortcuts Help |
| <kbd>Ctrl</kbd> + <kbd>\</kbd> | Toggle Sidebar Collapse / Expand |
| <kbd>Ctrl</kbd> + <kbd>D</kbd> | Toggle Dark / Light Theme |
| <kbd>Enter</kbd> | Send Chat Message |
| <kbd>Shift</kbd> + <kbd>Enter</kbd> | Insert Newline in Chat |
| <kbd>Esc</kbd> | Close Any Open Modal or Palette |

---

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python 3.10+), Uvicorn, SQLAlchemy, SQLite
- **AI & RAG**: Google Gemini API (`google-genai`), PyTorch GPU Embeddings (`sentence-transformers`), Scikit-learn cosine similarity
- **Frontend**: Vanilla HTML5, CSS3 (CSS Variables, Flexbox, Glassmorphism), Modern Vanilla JavaScript (ES6+), Marked.js, FontAwesome

---

## 🚀 Getting Started

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/prashant-7-8-7/Macro-Project-.git
cd Macro-Project-

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

*(Optional: For CUDA GPU acceleration, install the PyTorch build corresponding to your CUDA version)*

### 3. Configure Environment Variables

Copy `.env.example` to `.env` in the root directory, then configure at least one eligible provider. No credentials belong in frontend files:

```env
# The OpenRouter free router uses only free models.
OPENROUTER_API_KEY=your_openrouter_api_key
PORT=8000
```

### 4. Run the Application

```bash
python main.py
```

Open your browser at **`http://127.0.0.1:8000`** to access the workspace.

### Workflow reliability improvements

This update keeps the existing Gemini/Groq/OpenRouter workflow and environment variables.

- Quizzes rotate source sampling across long documents and avoid stems from previous retry attempts.
- A valid chunk ID alone no longer verifies an answer. Answer wording and any supplied supporting excerpt must occur together in a source chunk; page/chunk references are corrected from the matched source.
- New quiz questions include an escaped supporting excerpt in the existing explanation panel. This is a text-evidence check, not a guarantee of semantic correctness.
- Identical active notes requests share one job. At most two notes jobs run simultaneously, with eight pending/running requests allowed and retryable HTTP 429 responses when full.
- Uploads use isolated temporary paths, configurable size limits, and cleanup. Document/chunk indexing commits atomically.
- Document filters are applied before retrieval limits. Long AI calls run outside the main async request loop.
- Chat HTML is sanitized, citations navigate to source chunks, and provider credentials stay with their own services.

Existing local/Render/Vercel API routing is retained. An optional `window.WORKSPACE_API_URL` override can point a separately hosted frontend at another backend. `CORS_ORIGINS` optionally restricts allowed frontend origins; existing deployments need no new configuration.

Run regression checks with `pip install -r requirements-dev.txt` followed by `python -m pytest -q`. Tests use disposable SQLite databases. Model-dependent checks are excluded by default; run them separately with `python -m pytest -q -m integration` after configuring the models/API. Optional browser checks use `node tests/browser_upgrade.cjs` with Playwright/Chromium installed and the application running.


### Study workflow upgrades

The existing interface, providers, SQLite database, and deployment entry points are retained. There is no Ollama dependency.

- **Saved conversations:** completed answers and citations persist across restarts. Follow-up questions receive the last six messages as context. Choose General, Explain simply, 2/6/10 marks, or Formulas. Answer lengths are prompt guidance, not guaranteed marking schemes.
- **Subjects and document scope:** create a subject and choose its documents. In chat, expand “Choose documents” to compare up to 20 documents. Changing scope starts a fresh conversation. Subjects organize documents without duplicating them.
- **Quiz progress:** completed attempts are scored by the server and saved once. Retry creates a separate attempt using the same questions without another AI call. “Focus on weak topics” samples chunks associated with earlier mistakes. The Study tab shows topic accuracy and recent attempts.
- **Flashcard review:** create cards from mistakes without an AI call, or generate source-checked cards. Reveal an answer and rate Again, Hard, Good, or Easy. Again returns after ten minutes; other ratings schedule later days. This is a simple revision schedule, not a scientifically calibrated mastery score.
- **Editable notes:** generated notes save on the server even if the browser closes after starting a job. Edit a section, regenerate only that section, and restore earlier saved versions. Keep the page open until a selected-section retry is saved. Jobs themselves are in memory and do not survive a server restart.
- **PDF evidence:** uploaded PDFs retain an original copy. Citation buttons show the actual page and highlight matching native text or OCR words where possible. Older uploads need uploading again to retain their originals. TXT/DOCX citations still navigate to extracted text.
- **Local OCR:** optional Tesseract reads scanned PDF pages; no OCR service or API key is required. Install Tesseract and its language packs locally, then set `OCR_LANGUAGES` (for example `eng+hin`). Docker includes English and Hindi. The default `OCR_MAX_PAGES=10` limits OCR work per upload; poor scans and missing language packs show extraction warnings.
- **Streaming:** chat displays real provider deltas and supports Stop. Failed/stopped partial responses are not deliberately saved as completed answers or cached; the submitted user message remains in history. Cached completed answers arrive immediately.

### Chat troubleshooting

- Keyword search extracts topic terms from natural questions, prefers chunks matching every topic term, and then relaxes to any topic term if needed. "What is data link layer?" no longer requires filler words such as "what" and "is" to appear in the same chunk. SQL document filters apply before either search limit.
- Topic-free follow-ups such as "Explain simply" reuse the latest user topic, even after several saved no-context replies. Assistant messages are kept out of retrieval queries. New topic questions search their own terms; document overview chips use representative excerpts from the selected documents. Those excerpts are samples, not an exhaustive full-document summary.
- The AI dot describes the latest response rather than testing the provider connection. Its text label distinguishes **Not checked**, **Searching documents**, **Generating answer**, **AI answered**, and **No matching text**. The last state means no AI request was made. A green dot can also follow a completed cached answer; it is not a live connectivity check.
- A `200 OK` for `/api/chat/stream` means streaming began; an upstream provider can still fail after headers are sent. The chat now distinguishes an output limit, timeout, interrupted connection, rejected key, provider error, and rate limit. The server logs the provider and failure category without API keys or document text.
- If an answer reaches its output limit, select **Explain in 2 minutes** or **2-mark answer**, or ask a narrower question. General answers are prompted to stay around 350 words. `AI_MAX_OUTPUT_TOKENS` defaults to 4096 and is bounded to 256–16384; increasing it may help longer answers but does not guarantee completion or override provider limits. No automatic continuation consumes an extra request.
- Interrupted answers keep safe Markdown formatting and display a separate status message. They remain unsaved and uncached.
- If hybrid search is slow, select **Document search → Keywords · skip embedding model**. This uses SQLite text search without loading or running the embedding model; wording matters more and cross-language/semantic matching is weaker. Hybrid remains the default. New startup timing logs help distinguish embedding initialization from the total search time.
- Requests for Chrome's `/.well-known/appspecific/com.chrome.devtools.json` and optional `.js.map` debugging files can return 404 without affecting chat.

### Free-tier configuration and limits

OpenRouter is pinned to `openrouter/free`; a paid model override is ignored. Gemini and Groq are disabled unless their respective `*_FREE_TIER_CONFIRMED=true` flags are set in `.env`. Set those flags only after checking that your account **and selected model** have free access without paid overflow in the provider console. The application cannot inspect external account billing, and a confirmation flag does not enforce a provider's billing settings. No application can promise unlimited free API access.

Local daily request caps default to Gemini 20, Groq 50, and OpenRouter 40. They reset at midnight UTC, count attempted calls, and apply to chat, quizzes, summaries, flashcards, and notes together. A provider HTTP 429 pauses that provider locally for one hour. Only other configured, eligible free providers can be tried. Exhausting all available quota produces a readable error or the existing unavailable/partial-generation result. It never selects a paid OpenRouter model. The Study tab shows configuration and local usage; provider dashboards remain authoritative for real quota and billing.

Completed responses are cached in SQLite for up to 30 days using a hash of provider, model, credential, and prompt. Repeating a cached request avoids another provider call. Cache entries, conversations, notes versions, quiz answers, cards, and OCR coordinates are local data. Back up the SQLite database and `data/originals` together; both require persistent storage when hosting. This remains a single-user prototype without authentication or per-user isolation; shared public hosting requires adding those controls.

Embedding fallback now uses deterministic character hashing so it stays consistent after a restart. It is lexical retrieval, with weaker cross-language matching than the sentence transformer. New documents record their embedding backend. Run `python reindex.py` after changing embedding models/backends or upgrading an older index, so existing vectors match the active backend; keyword retrieval continues to work while old incompatible vectors are skipped.

For reproducible checks and browser fixture setup, see [tests/README.md](tests/README.md). No real provider requests are made by the default tests.
