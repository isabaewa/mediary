/** Реальные пользовательские действия. Адрес и сессия поступают только от тестового сервера. */
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

const config = process.env;
const root = config.MEDIARY_TEST_URL;
const medicationPath = `/medications/${config.MEDIARY_TEST_MEDICATION}/edit/`;
const entryPath = `/diary/${config.MEDIARY_TEST_ENTRY}/edit/`;

async function waitForProgress(page, value) {
    await page.waitForFunction(expected => {
        return document.getElementById('day-progress-bar').value === expected;
    }, value);
}

const scenarios = {
    async medication(page) {
        await page.goto(root + medicationPath);
        assert.equal(await page.locator('.dose-slot:visible').count(), 2);
        await page.locator('.dose-step[data-step="1"]').click();
        assert.equal(await page.locator('.dose-slot:visible').count(), 3);
        await page.locator('[name="intake_mode"][value="occasional"]').check();
        assert.equal(await page.locator('#schedule-details').isVisible(), false);
        assert.equal(await page.locator('#id_daily_doses').isDisabled(), true);
        await Promise.all([
            page.waitForURL(root + '/medications/'),
            page.locator('#mainForm [type="submit"]').click(),
        ]);
    },

    async health(page) {
        await page.goto(root + entryPath);
        assert.equal(await page.locator('#pain_num').innerText(), '3');
        assert.equal(await page.locator('.pain-block[data-val="3"]').getAttribute('aria-pressed'), 'true');
        await page.locator('.mood-btn[data-val="Отличное"]').click();
        await page.locator('#id_condition').evaluate(element => {
            element.value = 'Отличное';
            element.dispatchEvent(new Event('change', {bubbles: true}));
        });
        assert.equal(await page.locator('.cond-btn[aria-pressed="true"]').count(), 1);
        assert.equal(await page.locator('.cond-btn[data-val="Отличное"]').getAttribute('aria-pressed'), 'true');
        await page.locator('[name="has_pain"][value="no"]').check();
        assert.equal(await page.locator('#pain_num').innerText(), '0');
        assert.equal(await page.locator('.pain-block[aria-pressed="true"]').count(), 0);
        await Promise.all([
            page.waitForURL(root + '/'),
            page.locator('#mainForm [type="submit"]').click(),
        ]);
    },

    async toggle(page) {
        await page.goto(root + '/');
        const url = page.url();
        const button = page.locator('.pill-button').last();
        await button.click();
        await waitForProgress(page, 2);
        assert.equal(page.url(), url);
        assert.equal(await page.locator('#day-progress-text').innerText(), 'Принято 2 из 2');
        await button.click();
        await waitForProgress(page, 1);
        assert.equal(page.url(), url);
        assert.equal(await button.getAttribute('aria-pressed'), 'false');
    },

    async retry(page) {
        await page.goto(root + '/');
        const pattern = '**/intake/*/toggle/';
        await page.route(pattern, route => route.abort());
        const button = page.locator('.pill-button').last();
        await button.click();
        await page.locator('.intake-error').waitFor();
        assert.equal(await button.isDisabled(), false);
        assert.equal(await button.getAttribute('aria-pressed'), 'false');
        assert.equal(await page.locator('progress').getAttribute('value'), '1');
        await page.unroute(pattern);
        await button.click();
        await waitForProgress(page, 2);
    },

    async quick(page) {
        await page.goto(root + '/');
        await page.locator('.quick-open').click();
        const value = await page.locator('[name="taken_at"]').inputValue();
        // Границы рассчитаны сервером Django; браузер намеренно использует другой пояс.
        assert.ok(value >= config.MEDIARY_TEST_TIME_MIN && value <= config.MEDIARY_TEST_TIME_MAX);
        await page.locator('#quick-new').click();
        await page.locator('[name="name"]').fill('New browser test medication');
        await page.locator('[name="dosage"]').fill('Test dosage');
        await page.locator('[name="reason"]').fill('Synthetic reason');
        await Promise.all([
            page.waitForEvent('load'),
            page.locator('#quick-form [type="submit"]').click(),
        ]);
        assert.equal(await page.locator('#day-progress-text').innerText(), 'Принято 1 из 2');
        assert.equal(await page.locator('.extra-intakes').getByText('New browser test medication', {exact: true}).count(), 1);
    },

    async native(page) {
        await page.goto(root + entryPath);
        assert.equal(await page.locator('#id_mood').isVisible(), true);
        await page.locator('#id_mood').selectOption('Плохое');
        await page.locator('[name="has_pain"][value="yes"]').check();
        await page.locator('#id_pain_intensity').fill('6');
        await Promise.all([
            page.waitForURL(root + '/'),
            page.locator('#mainForm [type="submit"]').click(),
        ]);
    },
};

async function main() {
    const scenario = process.argv[2];
    assert.ok(root && scenarios[scenario], 'Запускайте сценарии через manage.py test browser_tests.');
    const channel = config.MEDIARY_BROWSER_CHANNEL;
    const browser = await chromium.launch({
        headless: true,
        channel: channel && channel !== 'chromium' ? channel : undefined,
    });
    try {
        const context = await browser.newContext({
            viewport: {width: Number(config.MEDIARY_TEST_WIDTH), height: Number(config.MEDIARY_TEST_HEIGHT)},
            reducedMotion: 'reduce', timezoneId: 'America/New_York',
            javaScriptEnabled: scenario !== 'native',
        });
        await context.addCookies([{
            name: config.MEDIARY_TEST_COOKIE_NAME,
            value: config.MEDIARY_TEST_SESSION,
            url: root,
        }]);
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(String(error)));
        await scenarios[scenario](page);
        assert.deepEqual(errors, []);
        await context.close();
    } finally {
        await browser.close();
    }
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
