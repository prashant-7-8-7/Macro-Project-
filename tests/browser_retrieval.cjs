/* Real upload, SQLite retrieval and chat transport; only the AI text is stubbed
   by browser_server.py. In particular, do not intercept /api/chat/stream here. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const base = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8000';

(async () => {
    const browser = await chromium.launch({ headless: true,
        executablePath: process.env.CHROMIUM_EXECUTABLE || undefined,
        args: ['--no-sandbox', '--disable-dev-shm-usage'] });
    try {
        const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/*', route => new URL(route.request().url()).origin !== new URL(base).origin
            ? route.abort() : route.continue());
        await page.goto(base);
        assert.equal(await page.locator('#ai-status-label').innerText(), 'Not checked');
        const filename = 'Network keyword regression.txt';
        await page.locator('#file-input').setInputFiles({ name: filename, mimeType: 'text/plain',
            buffer: Buffer.from('The data link layer provides framing and node-to-node delivery.\n\nCRC detects transmission errors using a generator polynomial.') });
        await page.getByText(filename, { exact: true }).first().click();
        await page.locator('#chat-search-mode').selectOption('keyword');
        await page.locator('#chat-answer-style').selectOption('6_marks');

        async function ask(text, chip) {
            const before = await page.locator('.ai-message').count();
            if (chip) {
                await page.locator('.suggested-chip').filter({ hasText: chip }).click();
            } else {
                await page.locator('#chat-input').fill(text);
                await page.locator('#btn-send').click();
            }
            await page.waitForFunction(count => document.querySelectorAll('.ai-message').length > count &&
                !document.getElementById('btn-send').disabled, before);
            return page.locator('.ai-message').last();
        }
        async function assertGrounded(message) {
            assert.match(await message.innerText(), /Data link layer/);
            assert.doesNotMatch(await message.innerText(), /No relevant documents/);
            assert.ok(await message.locator('.citation-source-btn').count());
            assert.equal(await page.locator('#ai-status-label').innerText(), 'AI answered');
            assert.equal(await page.locator('#ai-status').evaluate(el => el.classList.contains('online')), true);
        }
        await assertGrounded(await ask('what is data link layer'));
        for (let i = 0; i < 4; i++) await assertGrounded(await ask(null, 'Explain simply'));

        const missing = await ask('What is photosynthesis?');
        assert.match(await missing.innerText(), /No relevant documents/);
        assert.equal(await page.locator('#ai-status-label').innerText(), 'No matching text');
        assert.match(await page.locator('#ai-status').getAttribute('title'), /provider was not called/);
        assert.equal(await page.locator('#ai-status').evaluate(el => el.classList.contains('online')), false);
        await assertGrounded(await ask('what is data link layer'));

        await page.locator('#chat-new').click();
        await assertGrounded(await ask(null, 'Key points'));
        await page.locator('#chat-new').click();
        await assertGrounded(await ask(null, 'Main findings'));
        await page.locator('#chat-new').click();
        await assertGrounded(await ask(null, 'Explain simply'));
        await page.setViewportSize({ width: 390, height: 844 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        assert.deepEqual(errors, []);
        console.log('Retrieval UI passed: real upload, natural question, four repeated follow-ups, all three chips, scoped citations, and grey/green status explanations.');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
