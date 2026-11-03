/** Общая форма дополнительного приёма: отдельная страница и диалог главной. */
(() => {
    const form = document.getElementById('quick-form');
    if (!form) return;

    const mode = form.querySelector('[name="mode"]');
    const medication = form.querySelector('[name="medication"]');
    const toggleButton = form.querySelector('#quick-new');
    const takenAt = form.querySelector('[name="taken_at"]');
    const submitButton = form.querySelector('[type="submit"]');
    const medications = JSON.parse(document.getElementById('quick-medication-data').textContent);

    function updateMode() {
        const isNew = mode.value === 'new';
        form.querySelector('#quick-existing').hidden = isNew;
        form.querySelector('#quick-new-fields').hidden = !isNew;
        toggleButton.textContent = isNew ? 'Выбрать из моих лекарств' : '＋ Новое лекарство';
        medication.disabled = isNew;
        form.querySelectorAll('[name="name"], [name="dosage"]').forEach(input => {
            input.disabled = !isNew;
            input.required = isNew;
        });
    }

    function updateDosage() {
        form.querySelector('#quick-dose').textContent = medications.find(
            item => String(item.id) === medication.value,
        )?.dosage || '';
    }

    toggleButton.addEventListener('click', () => {
        mode.value = mode.value === 'new' ? 'existing' : 'new';
        updateMode();
        (mode.value === 'new' ? form.querySelector('[name="name"]') : medication).focus();
    });
    medication.addEventListener('change', updateDosage);
    updateMode();
    updateDosage();

    const dialog = document.getElementById('quick-dialog');
    const opener = document.querySelector('.quick-open');
    if (dialog?.showModal && opener) {
        // datetime-local не содержит часовой пояс: используем тот же пояс, что и Django.
        const formatter = new Intl.DateTimeFormat('sv-SE', {
            timeZone: form.dataset.timeZone,
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
        });
        opener.addEventListener('click', event => {
            event.preventDefault();
            const parts = Object.fromEntries(formatter.formatToParts(new Date()).map(part => [part.type, part.value]));
            const now = `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
            takenAt.max = now;
            if (!takenAt.dataset.edited) takenAt.value = now;
            dialog.showModal();
        });
        takenAt.addEventListener('input', () => { takenAt.dataset.edited = 'true'; });
        dialog.querySelector('.quick-close').addEventListener('click', () => dialog.close());
    }

    // Нативная валидация проходит до submit; после неё блокируем повторную отправку.
    form.addEventListener('submit', () => { submitButton.disabled = true; });
    window.addEventListener('pageshow', () => { submitButton.disabled = false; });
})();
