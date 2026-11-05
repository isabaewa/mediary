/** Общее поведение шапки. Подключается один раз через базовый шаблон. */
(() => {
    const brandLink = document.querySelector('.brand-wrapper');
    if (!brandLink) return;
    // Приветствие запускается при загрузке главной страницы.
    if (brandLink.hasAttribute('data-animate-brand') &&
        !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        brandLink.classList.add('is-introducing');
        const wave = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        wave.classList.add('brand-intro-wave');
        wave.setAttribute('viewBox', '0 0 140 24');
        wave.setAttribute('aria-hidden', 'true');
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', 'M2 12h35l7-4 7 8 8-13 8 19 8-14 7 4h56');
        wave.append(path);
        brandLink.append(wave);
        wave.addEventListener('animationend', () => {
            wave.remove();
            brandLink.classList.remove('is-introducing');
        }, {once: true});
    }

    const accountMenu = document.querySelector('.account-menu');
    if (!accountMenu) return;
    const trigger = accountMenu.querySelector('summary');

    // Escape возвращает фокус к кнопке, а клик вне меню сохраняет естественный фокус.
    accountMenu.addEventListener('keydown', event => {
        if (event.key !== 'Escape' || !accountMenu.open) return;
        accountMenu.open = false;
        trigger.focus();
    });
    document.addEventListener('click', event => {
        if (!accountMenu.contains(event.target)) accountMenu.open = false;
    });
})();
