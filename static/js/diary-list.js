(() => {
    const list = document.getElementById('diary-list');
    if (!list || !window.fetch || !window.AbortController) return;

    const status = document.getElementById('diary-list-status');
    const listPath = location.pathname;
    let pendingRequest;

    async function loadList(url, {fromHistory = false, focusSearch = false} = {}) {
        pendingRequest?.abort();
        const controller = new AbortController();
        pendingRequest = controller;
        const timeout = setTimeout(() => controller.abort(), 12000);
        status.hidden = false;
        status.textContent = 'Загрузка записей…';
        list.setAttribute('aria-busy', 'true');

        try {
            const response = await fetch(url, {
                headers: {'X-Diary-Fragment': '1'},
                signal: controller.signal,
            });
            if (!response.ok) throw new Error('List request failed');

            const responseUrl = new URL(response.url);
            if (response.redirected && responseUrl.pathname !== listPath) {
                if (pendingRequest === controller) location.assign(responseUrl);
                return;
            }

            const html = await response.text();
            if (pendingRequest !== controller) return;
            const focusWasInList = list.contains(document.activeElement);
            // Django отрисовывает и экранирует фрагмент тем же шаблоном, что и при обычном GET.
            list.innerHTML = html;
            if (!fromHistory && responseUrl.href !== location.href) {
                history.pushState(null, '', responseUrl);
            }
            if (focusWasInList) {
                const target = focusSearch ? list.querySelector('[name="q"]') : list;
                target.focus({preventScroll: true});
            }
            status.hidden = true;
        } catch {
            if (pendingRequest !== controller) return;
            if (fromHistory) {
                location.reload();
                return;
            }
            status.textContent = 'Не удалось загрузить записи. Повторите действие.';
        } finally {
            clearTimeout(timeout);
            if (pendingRequest === controller) {
                list.removeAttribute('aria-busy');
                pendingRequest = null;
            }
        }
    }

    list.addEventListener('submit', event => {
        const form = event.target.closest('.list-filters');
        if (!form) return;

        event.preventDefault();
        const params = new URLSearchParams(new FormData(form));
        const submitter = event.submitter;
        if (submitter?.name) params.set(submitter.name, submitter.value);

        const url = new URL(form.action);
        url.search = params.toString();
        loadList(url, {focusSearch: Boolean(submitter?.closest('.list-search-control'))});
    });

    list.addEventListener('click', event => {
        const link = event.target.closest('.list-pagination a, .filter-actions a');
        if (!link || event.button !== 0 || event.ctrlKey || event.metaKey
            || event.shiftKey || event.altKey) return;

        event.preventDefault();
        loadList(link.href);
    });

    window.addEventListener('popstate', () => loadList(location.href, {fromHistory: true}));
})();
