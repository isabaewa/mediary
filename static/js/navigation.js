/** На каждой странице измеряем ссылки заново, включая мобильную раскладку. */
(() => {
    const nav = document.querySelector('.navbar-nav');
    const active = nav?.querySelector('[aria-current="page"]');
    if (!active) return;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const indicator = document.createElement('span');
    indicator.className = 'nav-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    nav.append(indicator);
    nav.classList.add('has-indicator');

    function position(link) {
        const container = nav.getBoundingClientRect();
        const bounds = link.getBoundingClientRect();
        return {
            left: bounds.left - container.left + 12,
            top: bounds.bottom - container.top - 3,
            width: Math.max(0, bounds.width - 24),
        };
    }
    function place() {
        const target = position(active);
        Object.assign(indicator.style, {
            left: target.left + 'px',
            top: target.top + 'px',
            width: target.width + 'px',
        });
    }
    place();

    // Сохраняем адрес исходной вкладки, чтобы продолжить движение после загрузки.
    let previous;
    try {
        previous = JSON.parse(sessionStorage.getItem('mediary-nav-transition'));
        sessionStorage.removeItem('mediary-nav-transition');
    } catch {
        previous = null;
    }
    const source = previous && Array.from(nav.querySelectorAll('a')).find(
        link => link.pathname === previous.from
    );
    if (source && source !== active && previous.to === active.pathname && !reducedMotion.matches) {
        const from = position(source);
        const to = position(active);
        indicator.animate([
            {transform: `translate(${from.left - to.left}px, ${from.top - to.top}px)`, width: from.width + 'px'},
            {transform: 'translate(0, 0)', width: to.width + 'px'},
        ], {duration: 400, easing: 'ease-in-out'});
    }
    nav.addEventListener('click', event => {
        const link = event.target.closest('a');
        if (!link || event.button !== 0 || event.ctrlKey || event.metaKey ||
            event.shiftKey || event.altKey || link.target || link === active) return;
        try {
            sessionStorage.setItem('mediary-nav-transition', JSON.stringify({
                from: active.pathname, to: link.pathname,
            }));
        } catch {
            // Статическая активная полоска работает и без хранилища.
        }
    });
    new ResizeObserver(place).observe(nav);
    document.fonts.ready.then(place);
})();
