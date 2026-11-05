"""Серверная валидация ввода; проверки обязательны независимо от JavaScript."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils import timezone

from .models import HealthEntry, Medication
from .validators import DIARY_MIN_DATE, validate_diary_date


class MedicationForm(forms.ModelForm):
    """Количество приёмов обязательно, конкретное время — по желанию."""

    intake_mode = forms.ChoiceField(
        label='Как принимаете?',
        choices=[('regular', 'Регулярно'), ('occasional', 'Иногда')],
        initial='regular',
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Medication
        fields = [
            'name',
            'purpose',
            'dosage',
            'frequency',
            'as_needed',
            'daily_doses',
            'start_date',
            'end_date',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'purpose': forms.TextInput(attrs={'class': 'form-control'}),
            'dosage': forms.TextInput(attrs={'class': 'form-control'}),
            'frequency': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'daily_doses': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': 1,
                    'max': 12,
                    'step': 1,
                    'inputmode': 'numeric',
                }
            ),
            'start_date': forms.DateInput(
                format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}
            ),
            'end_date': forms.DateInput(
                format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}
            ),
        }

    def __init__(self, *args, **kwargs):
        # Совместимость с прежними POST, где режим задавался только as_needed.
        if args and args[0] is not None and 'intake_mode' not in args[0]:
            data = args[0].copy()
            data['intake_mode'] = 'occasional' if data.get('as_needed') else 'regular'
            args = (data, *args[1:])
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['intake_mode'].initial = (
                'occasional' if self.instance.as_needed else 'regular'
            )
        self.fields['daily_doses'].required = False
        self.fields['daily_doses'].min_value = 1
        self.fields['daily_doses'].max_value = 12
        self.fields['daily_doses'].widget.attrs.update({'min': 1, 'max': 12})
        times = self.instance.scheduled_times or []
        # Все 12 полей существуют и без JS; клиент лишь управляет видимостью слотов.
        for n in range(1, 13):
            self.fields[f'dose_time_{n}'] = forms.TimeField(
                required=False,
                label=f'Приём {n}',
                initial=times[n - 1] if len(times) >= n else None,
                input_formats=['%H:%M'],
                widget=forms.TimeInput(
                    format='%H:%M', attrs={'type': 'time', 'class': 'form-control'}
                ),
            )

    @property
    def time_fields(self):
        return [self[f'dose_time_{n}'] for n in range(1, 13)]

    @property
    def has_scheduled_times(self):
        return any(
            self[f'dose_time_{n}'].value() or self[f'dose_time_{n}'].errors for n in range(1, 13)
        )

    def clean(self):
        data = super().clean()
        # Сервер повторно определяет режим: скрытым и отключённым полям доверять нельзя.
        data['as_needed'] = data.get('intake_mode') == 'occasional'
        if data['as_needed']:
            data['start_date'] = None
            data['end_date'] = None
            data['frequency'] = ''
            data['daily_doses'] = 1
            self.instance.scheduled_times = []
            return data
        for field in ['start_date', 'end_date', 'daily_doses']:
            if not data.get(field) and field not in self.errors:
                self.add_error(field, 'Заполните это поле для регулярного приёма.')
        count = data.get('daily_doses')
        if count and 1 <= count <= 12:
            times = [data.get(f'dose_time_{n}') for n in range(1, count + 1)]
            selected = [t for t in times if t is not None]
            if len(selected) != len(set(selected)):
                raise forms.ValidationError('Время приёмов не должно повторяться.')
            self.instance.scheduled_times = [t.strftime('%H:%M') if t else None for t in times]
        return data


class HealthEntryForm(forms.ModelForm):
    """Форма для дневника самочувствия с валидацией оценки боли"""

    mood = forms.ChoiceField(
        label='Настроение',
        choices=[('', 'Выберите настроение')]
        + [(v, v) for v in ['Очень плохое', 'Плохое', 'Нормальное', 'Хорошее', 'Отличное']],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    condition = forms.ChoiceField(
        label='Общее состояние',
        choices=[('', 'Выберите состояние')]
        + [(v, v) for v in ['Плохое', 'Нормальное', 'Отличное']],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    has_pain = forms.ChoiceField(
        label='Есть ли боль?',
        choices=[('no', 'Нет'), ('yes', 'Да')],
        initial='no',
        widget=forms.RadioSelect,
    )
    pain_intensity = forms.IntegerField(
        label='Интенсивность боли',
        required=False,
        min_value=0,
        max_value=10,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 10}),
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        pain = self.instance.pain_intensity or 0
        self.initial.setdefault('has_pain', 'yes' if pain > 0 else 'no')
        self.initial.setdefault('pain_intensity', pain)
        self.fields['date'].validators.append(validate_diary_date)
        self.fields['date'].widget.attrs.update(
            min=DIARY_MIN_DATE.isoformat(), max=timezone.localdate().isoformat()
        )

    class Meta:
        model = HealthEntry
        fields = ['date', 'mood', 'condition', 'symptoms', 'pain_intensity', 'note']
        widgets = {
            'date': forms.DateInput(
                format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}
            ),
            'mood': forms.Select(attrs={'class': 'form-select'}),
            'condition': forms.Select(attrs={'class': 'form-select'}),
            'symptoms': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 2,
                    'placeholder': 'Например: головная боль, насморк',
                }
            ),
            'pain_intensity': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0, 'max': 10, 'placeholder': 'От 0 до 10'}
            ),
            'note': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Дополнительные заметки...',
                }
            ),
        }

    def clean_date(self):
        value = self.cleaned_data['date']
        if (
            self.user
            and HealthEntry.objects.filter(owner=self.user, date=value)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError('Запись за эту дату уже существует.')
        if value > timezone.localdate():
            raise forms.ValidationError('Самочувствие нельзя записать за будущий день.')
        return value

    def clean(self):
        data = super().clean()
        if data.get('has_pain') == 'no':
            data['pain_intensity'] = 0
        elif data.get('has_pain') == 'yes':
            pain = data.get('pain_intensity')
            if pain is None or pain < 1:
                self.add_error(
                    'pain_intensity', 'При наличии боли выберите интенсивность от 1 до 10.'
                )
        return data


class QuickIntakeForm(forms.Form):
    """Дополнительный приём: только свой препарат, новое название или прошедшее время."""

    reason = forms.CharField(
        max_length=300,
        required=False,
        label='Причина приёма',
        widget=forms.TextInput(
            attrs={'class': 'form-control', 'placeholder': 'Например: поднялась температура'}
        ),
    )
    taken_at = forms.DateTimeField(
        required=False,
        label='Когда приняли?',
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': 'form-control'}
        ),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # ModelChoiceField отклоняет чужой id, даже если его подставили вручную в POST.
        self.fields['medication'].queryset = (
            Medication.objects.filter(owner=user).order_by('name')
            if user and user.is_authenticated
            else Medication.objects.none()
        )
        now = timezone.localtime().replace(second=0, microsecond=0)
        self.fields['taken_at'].initial = now
        self.fields['taken_at'].widget.attrs['max'] = now.strftime('%Y-%m-%dT%H:%M')

    def clean_taken_at(self):
        value = self.cleaned_data.get('taken_at') or timezone.now()
        if value > timezone.now():
            raise forms.ValidationError('Приём нельзя записать на будущее.')
        return value

    mode = forms.ChoiceField(
        choices=[('existing', 'Сохранённое'), ('new', 'Новое')],
        initial='existing',
        widget=forms.HiddenInput,
    )
    medication = forms.ModelChoiceField(
        queryset=Medication.objects.none(),
        required=False,
        label='Какое лекарство?',
        empty_label='Выберите лекарство',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    name = forms.CharField(
        max_length=100,
        required=False,
        label='Название',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    dosage = forms.CharField(
        max_length=100,
        required=False,
        label='Дозировка',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    def clean(self):
        data = super().clean()
        if data.get('mode') == 'new':
            for field in ['name', 'dosage']:
                if not data.get(field):
                    self.add_error(field, 'Заполните это поле.')
        elif not data.get('medication'):
            self.add_error('medication', 'Выберите лекарство.')
        return data


class SignUpForm(UserCreationForm):
    """Стандартные проверки логина и двух паролей Django."""


class SignInForm(AuthenticationForm):
    """Стандартная аутентификация с дополнительным выбором срока сессии."""

    remember_me = forms.BooleanField(required=False, label='Запомнить меня на 14 дней')


class ProfileForm(forms.ModelForm):
    """Редактируем только разрешённые поля текущего аккаунта, без прав и пароля."""

    class Meta:
        model = get_user_model()
        fields = ['first_name', 'last_name', 'username', 'email']
        labels = {
            'username': 'Логин',
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'email': 'Электронная почта',
        }
        help_texts = {
            'username': 'Используется для входа в аккаунт.',
            'first_name': '',
            'last_name': '',
            'email': 'Восстановление пароля по почте пока недоступно.',
        }
        widgets = {
            'username': forms.TextInput(
                attrs={'class': 'form-control', 'autocomplete': 'username'}
            ),
            'first_name': forms.TextInput(
                attrs={'class': 'form-control', 'autocomplete': 'given-name'}
            ),
            'last_name': forms.TextInput(
                attrs={'class': 'form-control', 'autocomplete': 'family-name'}
            ),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}),
        }
