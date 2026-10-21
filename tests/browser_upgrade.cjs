/* Run with the app on port 8000 and Playwright + Chromium installed.
   AI responses and document data are stubbed; uploads/health use the real server. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const base = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8000';

(async () => {
    const browser = await chromium.launch({ headless: true,
        executablePath: process.env.CHROMIUM_EXECUTABLE || undefined,
        args: ['--no-sandbox', '--disable-dev-shm-usage'] });
    try {
        const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/*', route => {
            if (new URL(route.request().url()).origin !== new URL(base).origin) return route.abort();
            return route.continue();
        });
        const filename = '<img src=x onerror="window.__xss=1">.txt';
        await page.route('**/api/documents', route => route.fulfill({ json: { documents: [
            { id: 'test-doc', filename, file_type: 'txt', file_size: 1234 }
        ] } }));
        await page.route('**/api/documents/test-doc/content', route => route.fulfill({ json: {
            document: { id: 'test-doc', filename }, language: 'en', chunks: [
                { chunk_index: 4, page_number: 3, content: 'Solar panels convert sunlight into electricity. <img src=x onerror="window.__xss=1">' }
            ]
        } }));
        await page.route('**/api/chat/stream', route => route.fulfill({ contentType: 'text/event-stream', body: [
            {type:'session',session_id:'test-session'},
            {type:'delta',text:'**Verified answer** <img src=x onerror="window.__xss=1"> [bad](javascript:alert(1)) [Source 1]'},
            {type:'done',ai_available:true,citations:[{id:1,filename,document_id:'test-doc',page_number:3,chunk_index:4}]}
        ].map(event=>'data: '+JSON.stringify(event)+'\n\n').join('') }));
        await page.route('**/api/documents/test-doc/conversations', route => route.fulfill({json:{sessions:[]}}));
        await page.route('**/api/quiz/generate', route => route.fulfill({ json: {
            generated_count: 1, verified_count: 1, rejected_count: 0,
            questions: [{ question: 'Which language focuses on memory safety?', correct_answer: 'Rust',
                options: [{ label: 'Rust', is_correct: true }, { label: 'BASIC', is_correct: false },
                    { label: 'Python', is_correct: false }, { label: 'Fortran', is_correct: false }],
                source_page: 3, source_chunk_id: '0', status: 'verified',
                source_quote: 'Rust <img src=x onerror="window.__xss=1"> focuses on memory safety.' }]
        } }));

        await page.goto(base);
        await page.locator('.doc-item').click();
        await page.locator('.viewer-chunk').waitFor();
        assert.equal(await page.locator('.doc-title').getAttribute('title'), filename);
        assert.equal(await page.locator('.doc-title img, .viewer-chunk img').count(), 0);
        assert.equal(await page.locator('.chat-message img').count(), 0);

        await page.locator('#chat-input').fill('<img src=x onerror="window.__xss=1"> How do solar panels work?');
        await page.locator('#btn-send').click();
        await page.locator('.citation-source-btn').waitFor();
        assert.equal(await page.locator('.user-message img, .ai-message img, .ai-message a[href^="javascript:"]').count(), 0);
        assert.match(await page.locator('.user-message').innerText(), /<img/);
        assert.equal(await page.evaluate(() => window.__xss), undefined);
        assert.equal(await page.locator('.ai-message strong').filter({ hasText: 'Verified answer' }).count(), 1);
        await page.locator('.citation-source-btn').click();
        assert.equal(await page.evaluate(() => document.activeElement.dataset.chunkIndex), '4');
        assert.equal(await page.locator('#ai-status').evaluate(el => el.classList.contains('online')), true);
        await page.locator('#tab-btn-quiz').click();
        await page.locator('#btn-generate-quiz').click();
        await page.locator('.btn-toggle-explanation').click();
        await page.locator('.quiz-source-quote').waitFor();
        assert.match(await page.locator('.quiz-source-quote').innerText(), /<img/);
        assert.equal(await page.locator('.quiz-source-quote img').count(), 0);
        assert.match(await page.locator('.quiz-metadata').innerText(), /Chunk 0/);
        await page.locator('#tab-btn-document').click();

        const dialogPromise = page.waitForEvent('dialog');
        await page.locator('#file-input').setInputFiles({ name: 'invalid.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('test') });
        const dialog = await dialogPromise;
        assert.match(dialog.message(), /Supported files/);
        await dialog.accept();
        assert.equal((await page.request.get(`${base}/api/health`)).status(), 200);
        await page.setViewportSize({ width: 390, height: 844 });
        await page.waitForFunction(() => Math.abs(document.querySelector('.sidebar').getBoundingClientRect().width - innerWidth) < 1);
        const titleBox = await page.locator('#viewer-title').boundingBox();
        assert.ok(titleBox.x + titleBox.width <= 390, 'Long document titles must fit the mobile viewport');
        await page.screenshot({ path: process.env.BROWSER_SCREENSHOT || '/tmp/macro-workspace-mobile.png', fullPage: true });
        assert.deepEqual(errors, []);
        console.log('Browser checks passed: safe filenames/chat/excerpts, Markdown, quiz source display, source navigation, upload rejection, health, and mobile layout.');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
