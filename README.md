# Workspace — AI Document Intelligence & Study Platform

A premium, production-grade AI Document Workspace powered by **FastAPI**, **Google Gemini**, **PyTorch GPU sentence-transformers**, and modern vanilla web standards. Transform your documents (PDF, TXT, DOCX, CSV) into interactive study companions with contextual retrieval-augmented generation (RAG), automated quiz generation, and realistic handwritten study notes.

---

## ✨ Features & Capabilities

### 🎨 Design System & Aesthetics
- **Design Tokens**: Modular CSS variables spanning brand gradients (`#4F46E5` &rarr; `#7C3AED` &rarr; `#EC4899`), glassmorphism surfaces (`backdrop-filter: blur(16px)`), spacing scale, typography, and layered shadows.
- **Dark & Light Modes**: Instant theme toggle with `localStorage` persistence and automatic synchronization with system `prefers-color-scheme`.
- **Animated Aurora Mesh**: Smooth, GPU-composited radial mesh gradient background for visual depth without layout thrashing.
- **Modern Typography**: Inter and Plus Jakarta Sans for UI elements, paired with JetBrains Mono for document IDs and code blocks.

### 📐 Ergonomic 3-Column Workspace Shell
- **Collapsible Sidebar**: Smooth width transitions, document dropzone with animated upload progress bar, and real-time library search filter.
- **Document & Quiz Tabs**: Seamless tab switcher (`Document | Quiz Maker | Study Notes`) keeping all workflows centralized and focused.
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
- **Rich Message Actions**: Markdown rendering, code block copy button, typewriter stream, suggested-question chips, copy response, and regenerate reply.
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
git clone https://github.com/your-username/macro-project.git
cd "Macro Project"

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

Create a `.env` file in the root directory:

```env
GEMINI_API_KEY=your_gemini_api_key_here
PORT=8000
```

### 4. Run the Application

```bash
python main.py
```

Open your browser at **`http://127.0.0.1:8000`** to access the workspace.
