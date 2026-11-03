/** Форма препарата: режим курса, количество приёмов и необязательное время. */
(() => {
    const form = document.getElementById('mainForm');
    const countInput = form?.querySelector('[name="daily_doses"]');
    if (!countInput) return;

    const modeInputs = form.querySelectorAll('[name="intake_mode"]');
    const rows = [...form.querySelectorAll('.dose-slot')];
    const steps = [...form.querySelectorAll('.dose-step')];
    const schedule = form.querySelector('#schedule-details');
    const regularFields = [
        ...form.querySelectorAll('.regular-only'),
        form.querySelector('#daily-count-field'),
        schedule,
    ];
    const isOccasional = () => form.querySelector('[name="intake_mode"]:checked')?.value === 'occasional';

    /** Скрытые слоты не отправляются; введённое время сохраняется при переключении режима. */
    function updateCount() {
        const count = Number(countInput.value);
        steps.forEach(button => {
            button.disabled = Number(button.dataset.step) < 0 ? count <= 1 : count >= 12;
        });
        rows.forEach(row => {
            const active = Number(row.dataset.slot) <= count;
            row.hidden = !active;
            row.querySelector('input').disabled = !active || isOccasional();
        });
    }

    function updateMode() {
        const occasional = isOccasional();
        regularFields.forEach(container => {
            container.hidden = occasional;
            container.querySelectorAll('input, select, textarea').forEach(input => {
                input.disabled = occasional;
            });
        });
        updateCount();
    }

    // И кнопки, и ручной ввод используют один обработчик пересчёта слотов.
    steps.forEach(button => {
        button.hidden = false;
        button.addEventListener('click', () => {
            const current = Number(countInput.value) || 1;
            countInput.value = Math.max(1, Math.min(12, Math.trunc(current) + Number(button.dataset.step)));
            countInput.dispatchEvent(new Event('input', {bubbles: true}));
        });
    });
    countInput.addEventListener('input', updateCount);
    countInput.addEventListener('change', updateCount);
    modeInputs.forEach(input => input.addEventListener('change', updateMode));

    rows.forEach(row => {
        const input = row.querySelector('input');
        const clearButton = row.querySelector('.time-remove');
        const updateClear = () => { clearButton.hidden = !input.value; };
        input.addEventListener('input', updateClear);
        clearButton.addEventListener('click', () => {
            input.value = '';
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.focus();
        });
        updateClear();
    });

    // Время предлагается только для нового курса и никогда не заменяет введённое.
    if (schedule.dataset.new === 'true') {
        schedule.addEventListener('toggle', () => {
            if (!schedule.open || schedule.dataset.suggested || isOccasional()) return;
            const firstTime = form.querySelector('#id_dose_time_1');
            if (!firstTime.value) {
                firstTime.value = '07:00';
                firstTime.dispatchEvent(new Event('input', {bubbles: true}));
            }
            schedule.dataset.suggested = 'true';
        });
    }

    // При ошибке серверной проверки восстанавливаем состояние из полей Django.
    updateMode();
})();
