/** Дневник: кнопки выбора отражают значения обычных полей Django. */
(() => {
    const form = document.getElementById('mainForm');
    if (!form?.querySelector('[name="mood"]')) return;

    /** Единый источник значения — поле формы, включая aria-pressed и внешние изменения. */
    function bindChoices(input, buttons, eventName) {
        function updateSelection() {
            buttons.forEach(button => {
                const selected = button.dataset.val === input.value;
                button.classList.toggle('active', selected);
                button.setAttribute('aria-pressed', String(selected));
            });
        }
        input.addEventListener(eventName, updateSelection);
        buttons.forEach(button => button.addEventListener('click', () => {
            input.value = button.dataset.val;
            input.dispatchEvent(new Event(eventName, {bubbles: true}));
        }));
        updateSelection();
    }

    const mood = form.querySelector('[name="mood"]');
    const condition = form.querySelector('[name="condition"]');
    const pain = form.querySelector('[name="pain_intensity"]');
    const painButtons = form.querySelectorAll('.pain-block');
    bindChoices(mood, form.querySelectorAll('.mood-btn'), 'change');
    bindChoices(condition, form.querySelectorAll('.cond-btn'), 'change');
    bindChoices(pain, painButtons, 'input');

    // Подсказка зависит от значения поля, а не от способа его изменения.
    const support = form.querySelector('#condition-support');
    const supportTexts = {
        'Плохое': 'Сегодня непростой день. Будьте к себе бережнее — не обязательно успевать всё.',
        'Нормальное': 'Спасибо, что нашли время прислушаться к себе.',
        'Отличное': 'Приятно, что сегодня вы чувствуете себя хорошо. Пусть в дне найдётся место тому, что вас радует.',
    };
    function updateSupport() {
        support.textContent = supportTexts[condition.value] || '';
        support.hidden = !support.textContent;
    }
    condition.addEventListener('change', updateSupport);
    updateSupport();

    const painDetails = form.querySelector('#pain-details');
    const painNumber = form.querySelector('#pain_num');
    pain.addEventListener('input', () => { painNumber.textContent = pain.value; });
    painButtons.forEach(button => {
        button.setAttribute('aria-label', `Боль ${button.dataset.val} из 10`);
    });

    function updatePainVisibility() {
        const hasPain = form.querySelector('[name="has_pain"]:checked')?.value === 'yes';
        painDetails.hidden = !hasPain;
        pain.disabled = !hasPain;
        if (!hasPain) pain.value = '0';
        else if (Number(pain.value) < 1) pain.value = '1';
        // Все подписчики получают нормализованное значение, в том числе при загрузке.
        pain.dispatchEvent(new Event('input', {bubbles: true}));
    }
    form.querySelectorAll('[name="has_pain"]').forEach(input => {
        input.addEventListener('change', updatePainVisibility);
    });
    updatePainVisibility();

    // Без JavaScript исходные select и числовое поле остаются доступными.
    form.querySelectorAll('.native-choice').forEach(wrapper => { wrapper.hidden = true; });
    form.querySelectorAll('.choice-buttons').forEach(group => { group.hidden = false; });
    form.querySelector('#pain-native').hidden = true;
    form.querySelector('.pain-options').hidden = false;
})();
