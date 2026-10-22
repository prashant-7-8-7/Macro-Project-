# Regression checks

Default checks use disposable SQLite databases and mock cloud AI. They do not need keys or generate provider charges.

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

The scanned-PDF test runs real local OCR when Tesseract is installed; otherwise it skips. That test additionally needs Pillow and a DejaVuSans font. Model-dependent integration tests are excluded by default; use `python -m pytest -m integration` separately after configuring the required models.

## Browser checks

Install Playwright and its browser using `npm install --no-save playwright` and `npx playwright install chromium` (or set `CHROMIUM_EXECUTABLE` to an existing Chromium executable).

Use a **disposable** database and data directory. The controlled fixture seeds two documents and stubs AI on the server. It never calls real providers. In a first terminal from the repository root:

```bash
DB_PATH=/tmp/macro-browser.db DATA_DIR=/tmp/macro-browser-data PYTHONPATH=. python tests/browser_server.py
```

In another terminal:

```bash
node tests/browser_study.cjs
node tests/browser_upgrade.cjs
node tests/browser_retrieval.cjs
```

Use a new disposable path or remove the old fixture database before repeating the complete study scenario, which checks exact attempt/version counts. `browser_study.cjs` exercises saved streamed conversations, PDF highlights, quiz attempt history, weak-topic flashcards, review scheduling, notes editing/regeneration, subjects, and mobile layout. `browser_upgrade.cjs` checks escaping of filenames, user/AI content and source excerpts, Markdown rendering, citations, upload rejection, and mobile width. Browser tests block external assets and use local vendor scripts. Optional screenshots go to the system temporary directory.

The automated checks validate local behavior and HTTP protocol fixtures, not live provider account access, hosted persistence, or production load. Five model-dependent checks remain separate.

`browser_retrieval.cjs` uploads a real networking text file, asks "what is data link layer" using keyword mode, repeats the actual Explain simply chip four times, and checks all three chips in new conversations. Retrieval and chat requests use the real backend; only provider-generated text is stubbed. It also verifies grey/green status labels and a genuinely unmatched topic. Run this suite after the study suite when sharing the same fixture, because it adds another document.
