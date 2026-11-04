/** Общее поведение шапки. Подключается один раз через базовый шаблон. */
(() => {
    const brandLink = document.querySelector('.brand-wrapper');
    if (!brandLink) return;
    brandLink.addEventListener('click', event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
        // На главной повторяем пульс без ненужной перезагрузки.
        if (brandLink.href === window.location.href) {
            event.preventDefault();
            const heart = brandLink.querySelector('.brand-logo');
            heart.classList.add('is-restarting');
            // Чтение геометрии фиксирует сброс перед повторным запуском анимации.
            void heart.offsetWidth;
            heart.classList.remove('is-restarting');
        }
    });

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
