/** Применяем тему до отрисовки страницы, чтобы избежать светлой вспышки. */
(() => {
    const preference = window.matchMedia('(prefers-color-scheme: dark)');
    let saved;
    try {
        saved = localStorage.getItem('mediary-theme');
    } catch {
        // При запрете хранилища переключатель действует до закрытия страницы.
    }
    function apply(theme) {
        document.documentElement.dataset.theme = theme;
        const button = document.querySelector('.theme-toggle');
        if (!button) return;
        const dark = theme === 'dark';
        button.setAttribute('aria-pressed', String(dark));
        const label = dark ? 'Включить светлую тему' : 'Включить тёмную тему';
        button.setAttribute('aria-label', label);
        button.title = label;
    }
    if (saved !== 'light' && saved !== 'dark') saved = null;
    apply(saved || (preference.matches ? 'dark' : 'light'));
    document.addEventListener('DOMContentLoaded', () => {
        apply(document.documentElement.dataset.theme);
        document.querySelector('.theme-toggle').addEventListener('click', () => {
            saved = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
            apply(saved);
            try {
                localStorage.setItem('mediary-theme', saved);
            } catch {
                // Тема остаётся доступной и без localStorage.
            }
        });
    });
    preference.addEventListener('change', event => {
        if (!saved) apply(event.matches ? 'dark' : 'light');
    });
    window.addEventListener('storage', event => {
        if (event.key !== 'mediary-theme') return;
        saved = ['light', 'dark'].includes(event.newValue) ? event.newValue : null;
        apply(saved || (preference.matches ? 'dark' : 'light'));
    });
})();
