"""Валидация GET-параметров списков; произвольные имена полей в сортировку не попадают."""

from django import forms

from .models import HealthEntry

MEDICATION_SECTIONS = [('all', 'Все'), ('courses', 'Курсы'), ('occasional', 'Без курса')]
MEDICATION_SORTS = [
    ('name_asc', 'Название: А–Я'),
    ('name_desc', 'Название: Я–А'),
    ('start_desc', 'Начало курса: сначала новые'),
    ('start_asc', 'Начало курса: сначала старые'),
    ('end_asc', 'Окончание курса: ближайшие'),
]
HEALTH_SORTS = [
    ('date_desc', 'Дата: сначала новые'),
    ('date_asc', 'Дата: сначала старые'),
    ('pain_desc', 'Боль: сначала сильнее'),
    ('pain_asc', 'Боль: сначала слабее'),
]


class ListFilterForm(forms.Form):
    q = forms.CharField(
        label='Поиск',
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={'type': 'search', 'placeholder': 'Введите текст'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = (
                'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            )


class MedicationFilterForm(ListFilterForm):
    section = forms.ChoiceField(choices=MEDICATION_SECTIONS, widget=forms.HiddenInput)
    status = forms.ChoiceField(
        label='Статус курса',
        required=False,
        choices=[
            ('', 'Любой статус'),
            ('active', 'Активный'),
            ('upcoming', 'Ещё не начался'),
            ('finished', 'Завершён'),
        ],
        help_text='Статус относится к препаратам с регулярным курсом.',
    )
    sort = forms.ChoiceField(label='Сортировка', choices=MEDICATION_SORTS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['q'].widget.attrs['placeholder'] = 'Название, дозировка, назначение'


class HealthEntryFilterForm(ListFilterForm):
    date_from = forms.DateField(
        label='С даты',
        required=False,
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
    )
    date_to = forms.DateField(
        label='По дату',
        required=False,
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
    )
    condition = forms.ChoiceField(
        label='Самочувствие',
        required=False,
        choices=[('', 'Любое')] + list(HealthEntry._meta.get_field('condition').choices),
    )
    mood = forms.ChoiceField(
        label='Настроение',
        required=False,
        choices=[('', 'Любое')] + list(HealthEntry._meta.get_field('mood').choices),
    )
    pain_min = forms.IntegerField(label='Боль от', required=False, min_value=0, max_value=10)
    pain_max = forms.IntegerField(label='Боль до', required=False, min_value=0, max_value=10)
    sort = forms.ChoiceField(label='Сортировка', choices=HEALTH_SORTS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['q'].widget.attrs['placeholder'] = 'Симптомы или заметка'

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            self.add_error('date_to', 'Конец периода не может быть раньше начала.')
        low, high = data.get('pain_min'), data.get('pain_max')
        if low is not None and high is not None and low > high:
            self.add_error('pain_max', 'Верхняя граница боли не может быть меньше нижней.')
        return data
