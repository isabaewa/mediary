/** Плановые приёмы: POST → подтверждение сервера → статус кнопки и прогресс. */
(() => {
    const intakeForms = [...document.querySelectorAll('.intake-toggle')];
    if (!intakeForms.length || !window.fetch) return;

    const STATUS_REFRESH_MS = 15000;
    const REQUEST_TIMEOUT_MS = 12000;

    /** Просрочка меняется с течением времени даже без действий пользователя. */
    function updatePendingState(button, state) {
        const overdue = Boolean(button.dataset.scheduledAt) && Date.parse(button.dataset.scheduledAt) < Date.now();
        state.classList.toggle('intake-missed', overdue);
        state.textContent = overdue ? 'Пропущено' : 'Ожидает отметки';
    }
    // Таймер обновляет только ожидающие записи; ошибки и активные запросы не затираются.
    setInterval(() => document.querySelectorAll('.intake-toggle .pill-button').forEach(button => {
        const state = button.closest('.list-group-item').querySelector('.intake-state');
        if (button.getAttribute('aria-pressed') !== 'true'
            && !button.disabled && !state.classList.contains('intake-error')) {
            updatePendingState(button, state);
        }
    }), STATUS_REFRESH_MS);

    /** Прогресс учитывает только плановые приёмы, дополнительные записи в него не входят. */
    function updateDayProgress() {
        const buttons = [...document.querySelectorAll('.intake-toggle .pill-button')];
        const bar = document.getElementById('day-progress-bar');
        if (!bar) return;
        const done = buttons.filter(button => button.getAttribute('aria-pressed') === 'true').length;
        const complete = buttons.length > 0 && done === buttons.length;
        bar.closest('.day-progress').classList.toggle('is-complete', complete);
        document.getElementById('day-complete').classList.toggle('is-hidden', !complete);
        bar.max = buttons.length || 1;
        bar.value = done;
        bar.textContent = `${buttons.length ? Math.round(done / buttons.length * 100) : 0}%`;
        document.getElementById('day-progress-text').textContent = `Принято ${done} из ${buttons.length}`;
    }
    // Без JavaScript остаётся обычная форма с POST и CSRF-защитой.
    intakeForms.forEach(form => {
        let submitting = false;
        const button = form.querySelector('button');
        const state = form.closest('.list-group-item').querySelector('.intake-state');
        const displayLabel = taken => `${taken ? 'Снять отметку' : 'Отметить приём'} ${button.dataset.name}, приём ${button.dataset.slot}`;
        form.addEventListener('submit', async event => {
            event.preventDefault();
            if (submitting) return;
            submitting = true;
            button.disabled = true;
            const animationStarted = performance.now();
            const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            button.classList.add('is-busy');
            button.setAttribute('aria-busy', 'true');
            const data = new FormData(form);
            // Явный желаемый статус делает повтор запроса безопасным при потере ответа.
            data.set('taken', String(button.getAttribute('aria-pressed') !== 'true'));
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
            try {
                // FormData содержит CSRF-токен; Accept выбирает JSON-ответ вместо redirect.
                const response = await fetch(form.action, {method: 'POST', body: data,
                    headers: {'Accept': 'application/json'}, signal: controller.signal});
                if (!response.ok) throw new Error('Save failed');
                const result = await response.json();
                if (typeof result.taken !== 'boolean') throw new Error('Invalid response');
                if (!reducedMotion) await new Promise(resolve => setTimeout(resolve, Math.max(0, 600 - (performance.now() - animationStarted))));
                button.classList.remove('is-busy');
                // Состояние интерфейса меняем только после подтверждения сохранения сервером.
                button.classList.toggle('taken', result.taken);
                button.setAttribute('aria-pressed', String(result.taken));
                updateDayProgress();
                button.setAttribute('aria-label', displayLabel(result.taken));
                button.classList.add('is-changing');
                setTimeout(() => button.classList.remove('is-changing'), 520);
                state.classList.remove('intake-error');
                state.classList.toggle('intake-done', result.taken);
                state.classList.remove('intake-missed');
                if (result.taken) state.textContent = result.taken_at ? `✓ Принято в ${result.taken_at}` : '✓ Принято · время не записано';
                else updatePendingState(button, state);
                if (!reducedMotion) await new Promise(resolve => setTimeout(resolve, 500));
            } catch (error) {
                state.classList.add('intake-error');
                state.textContent = 'Не удалось сохранить. Повторите.';
            } finally {
                // При сетевой ошибке снова разрешаем пользователю отправить ту же отметку.
                clearTimeout(timeout);
                button.disabled = false;
                button.classList.remove('is-busy');
                button.removeAttribute('aria-busy');
                submitting = false;
            }
        });
    });
})();
