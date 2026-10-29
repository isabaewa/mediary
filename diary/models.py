from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import time, datetime

class Medication(models.Model):
    """Модель лекарственного препарата/курса"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='medications', verbose_name='Владелец')
    name = models.CharField(max_length=100, verbose_name="Название препарата")
    purpose = models.CharField(max_length=200, blank=True, verbose_name="Назначение")
    as_needed = models.BooleanField(default=False, verbose_name="Иногда")
    daily_doses = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(12)], verbose_name="Приёмов в день")
    scheduled_times = models.JSONField(default=list, blank=True, verbose_name="Необязательное время приёмов")
    dosage = models.CharField(max_length=100, verbose_name="Дозировка / Форма приёма")
    frequency = models.CharField(max_length=100, blank=True, verbose_name="Примечание к приёму")
    start_date = models.DateField(null=True, blank=True, verbose_name="Дата начала курса")
    end_date = models.DateField(null=True, blank=True, verbose_name="Дата окончания курса")

    class Meta:
        verbose_name = "Препарат"
        verbose_name_plural = "Препараты"
        constraints = [models.CheckConstraint(condition=models.Q(as_needed=True) | (models.Q(start_date__isnull=False, end_date__isnull=False) & models.Q(end_date__gte=models.F('start_date'))), name='medication_valid_dates'), models.CheckConstraint(condition=models.Q(daily_doses__gte=1, daily_doses__lte=12), name='medication_doses_range')]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'Дата окончания курса не может быть раньше даты начала!'})

        values = self.scheduled_times
        if not isinstance(values, list) or len(values) > (self.daily_doses or 0):
            raise ValidationError({'scheduled_times': 'Количество времён не должно превышать количество приёмов.'})
        nonempty = []
        for value in values:
            if value is not None:
                try:
                    parsed = time.fromisoformat(value)
                except (ValueError, TypeError):
                    raise ValidationError({'scheduled_times': 'Укажите корректное время.'})
                if parsed.second or parsed.microsecond or parsed.tzinfo:
                    raise ValidationError({'scheduled_times': 'Время указывается в часах и минутах.'})
                nonempty.append(parsed)
        if len(nonempty) != len(set(nonempty)):
            raise ValidationError({'scheduled_times': 'Время приёмов не должно повторяться.'})

    @property
    def course_status(self):
        if self.as_needed:
            return 'Иногда'
        today = timezone.localdate()
        if today < self.start_date:
            return 'Курс ещё не начался'
        if today > self.end_date:
            return 'Курс завершён'
        return 'Активный курс' 

    def __str__(self):
        return self.name


class MedicationIntake(models.Model):
    """Модель конкретного запланированного приёма лекарства"""
    medication = models.ForeignKey(
        Medication, 
        on_delete=models.CASCADE, 
        related_name='intakes',
        verbose_name="Препарат"
    )
    date = models.DateField(verbose_name="Дата приёма")
    slot = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)], verbose_name="Номер приёма")
    reason = models.CharField(max_length=300, blank=True, verbose_name="Причина приёма")
    is_extra = models.BooleanField(default=False, verbose_name="Дополнительный приём")
    taken_at = models.DateTimeField(null=True, blank=True, verbose_name="Фактическое время приёма")
    scheduled_time = models.TimeField(null=True, blank=True, verbose_name="Запланированное время приёма")
    taken = models.BooleanField(default=False, verbose_name="Статус приёма (Выполнен)")

    class Meta:
        verbose_name = "Запланированный приём"
        verbose_name_plural = "Запланированные приёмы"
        ordering = ['date', 'slot']
        constraints = [models.UniqueConstraint(fields=['medication', 'date', 'scheduled_time'], name='unique_medication_intake'), models.UniqueConstraint(fields=['medication', 'date', 'slot'], name='unique_daily_intake_slot'), models.CheckConstraint(condition=models.Q(slot__gte=1), name='intake_positive_slot'), models.CheckConstraint(condition=models.Q(taken=True) | models.Q(taken_at__isnull=True), name='intake_time_requires_taken')]

    @property
    def is_overdue(self):
        if self.taken or self.medication.as_needed or self.is_extra:
            return False
        now = timezone.localtime()
        if self.date < now.date():
            return True
        if self.scheduled_time:
            scheduled = timezone.make_aware(datetime.combine(self.date, self.scheduled_time))
            return scheduled < now
        return False

    def __str__(self):
        status = "Принято" if self.taken else "Ожидает"
        return f"{self.medication.name} — {self.date}, приём {self.slot} ({status})"


class HealthEntry(models.Model):
    """Модель записи в дневнике самочувствия"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='health_entries', verbose_name='Владелец')
    date = models.DateField(verbose_name="Дата записи")
    mood = models.CharField(choices=[(v, v) for v in ["Отличное", "Хорошее", "Нормальное", "Плохое", "Очень плохое"]], max_length=20, verbose_name="Настроение")
    condition = models.CharField(choices=[(v, v) for v in ["Отличное", "Нормальное", "Плохое"]], max_length=20, verbose_name="Общее состояние")
    symptoms = models.TextField(default="Нет симптомов", verbose_name="Симптомы")
    pain_intensity = models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(10)], verbose_name="Интенсивность боли (0-10)")
    note = models.TextField(blank=True, null=True, verbose_name="Заметка")

    class Meta:
        verbose_name = "Запись самочувствия"
        verbose_name_plural = "Записи самочувствия"
        ordering = ['-date']
        constraints = [models.UniqueConstraint(fields=['owner', 'date'], name='unique_owner_health_date'), models.CheckConstraint(condition=models.Q(pain_intensity__gte=0, pain_intensity__lte=10), name='health_pain_range')]

    def __str__(self):
        return f"Состояние за {self.date} ({self.condition})"
