/** Реальные пользовательские действия. Адрес и сессия поступают только от тестового сервера. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
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
    async medicationList(page) {
        await page.goto(root + '/medications/');
        const form = page.locator('form[role="search"]');
        await form.locator('[name="q"]').fill('запас');
        await form.locator('[name="sort"]').selectOption('name_desc');
        await Promise.all([page.waitForEvent('load'), form.locator('[type="submit"]').click()]);
        assert.equal(await page.locator('.medication-card').count(), 20);
        assert.equal(await page.locator('.medication-card h4').first().innerText(), 'Запас 24');
        assert.equal(new URL(page.url()).searchParams.get('q'), 'запас');
        await Promise.all([page.waitForEvent('load'), page.locator('a[rel="next"]').click()]);
        assert.equal(await page.locator('.medication-card').count(), 5);
        const params = new URL(page.url()).searchParams;
        assert.equal(params.get('page'), '2');
        assert.equal(params.get('q'), 'запас');
        assert.equal(params.get('sort'), 'name_desc');
        await Promise.all([
            page.waitForEvent('load'),
            page.locator('.medication-sections [value="occasional"]').click(),
        ]);
        assert.equal(new URL(page.url()).searchParams.get('section'), 'occasional');
        assert.equal(new URL(page.url()).searchParams.has('page'), false);
        assert.equal(await page.locator('.medication-card').count(), 20);
        await form.locator('[name="status"]').selectOption('active');
        await Promise.all([page.waitForEvent('load'), form.locator('[type="submit"]').click()]);
        assert.equal(await page.locator('.medication-card').count(), 0);
        assert.match(await page.locator('.list-empty').innerText(), /По заданным условиям/);
        await Promise.all([page.waitForEvent('load'), form.getByText('Сбросить', {exact: true}).click()]);
        assert.equal(await form.locator('[name="q"]').inputValue(), '');
        assert.equal(await page.locator('.medication-card').count(), 20);
        assert.equal(await page.locator('.list-result-count').innerText(), 'Найдено: 26 из 26');
    },

    async diaryList(page) {
        await page.goto(root + '/diary/');
        const form = page.locator('form[role="search"]');
        await form.locator('[name="q"]').fill('ГОЛОВНАЯ');
        await form.locator('[name="sort"]').selectOption('date_asc');
        await Promise.all([page.waitForEvent('load'), form.locator('[type="submit"]').click()]);
        await Promise.all([page.waitForEvent('load'), page.locator('a[rel="next"]').click()]);
        assert.equal(new URL(page.url()).searchParams.get('q'), 'ГОЛОВНАЯ');
        assert.equal(await page.locator('tbody tr').count(), 5);
        await form.locator('[name="date_from"]').fill(config.MEDIARY_TEST_DATE_FROM);
        await form.locator('[name="date_to"]').fill(config.MEDIARY_TEST_DATE_TO);
        await form.locator('[name="condition"]').selectOption('Нормальное');
        await form.locator('[name="mood"]').selectOption('Хорошее');
        await form.locator('[name="pain_min"]').fill('3');
        await form.locator('[name="pain_max"]').fill('7');
        await form.locator('[name="sort"]').selectOption('pain_desc');
        await Promise.all([page.waitForEvent('load'), form.locator('[type="submit"]').click()]);
        assert.equal(new URL(page.url()).searchParams.has('page'), false);
        assert.equal(await page.locator('tbody tr').count(), 11);
        assert.match(await page.locator('tbody tr').first().innerText(), /7 \/ 10/);
        assert.equal(await form.locator('[name="pain_min"]').inputValue(), '3');
        await form.locator('[name="pain_min"]').fill('8');
        await form.locator('[name="pain_max"]').fill('3');
        await Promise.all([page.waitForEvent('load'), form.locator('[type="submit"]').click()]);
        assert.equal(await page.locator('[role="alert"]').count(), 1);
        assert.match(await form.locator('.errorlist').innerText(), /Верхняя граница/);
        await Promise.all([page.waitForEvent('load'), form.getByText('Сбросить', {exact: true}).click()]);
        assert.equal(await form.locator('[name="q"]').inputValue(), '');
        assert.equal(await form.locator('[name="sort"]').inputValue(), 'date_desc');
        assert.equal(await page.locator('tbody tr').count(), 20);
        assert.equal(await page.locator('.list-result-count').innerText(), 'Найдено: 26 из 26');
    },
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
        // Необязательные снимки содержат только данные временной тестовой базы.
        if (config.MEDIARY_TEST_SCREENSHOTS) {
            fs.mkdirSync(config.MEDIARY_TEST_SCREENSHOTS, {recursive: true});
            await page.screenshot({
                path: path.join(config.MEDIARY_TEST_SCREENSHOTS, `${scenario}-${config.MEDIARY_TEST_WIDTH}.png`),
                fullPage: true,
            });
        }
        await context.close();
    } finally {
        await browser.close();
    }
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
