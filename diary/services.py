"""Операции с приёмами: запись дополнительного приёма и согласование расписания."""

from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import Medication, MedicationIntake


@transaction.atomic
def record_extra_intake(
    *,
    owner,
    medication_id=None,
    new_medication=None,
    taken_at=None,
    reason='',
    as_needed_only=False,
):
    """Записать дополнительный приём своего препарата в одной транзакции.

    Источник ровно один: medication_id либо new_medication с name и dosage.
    Проверки формы остаются на HTTP-границе; владение, время и целостность
    проверяются здесь повторно, чтобы сервис можно было вызывать вне views.
    При недоступном препарате поднимается Medication.DoesNotExist; HTTP-ответ
    выбирает представление. Создание нового препарата откатывается при сбое записи.
    """
    if (medication_id is None) == (new_medication is None):
        raise ValueError('Укажите существующий препарат либо данные нового.')

    taken_at = taken_at if taken_at is not None else timezone.now()
    if timezone.is_naive(taken_at):
        raise ValueError('Время приёма должно содержать часовой пояс.')
    if taken_at > timezone.now():
        raise ValidationError('Приём нельзя записать на будущее.')
    taken_at = timezone.localtime(taken_at)

    if medication_id is not None:
        available = Medication.objects.select_for_update().filter(owner=owner)
        if as_needed_only:
            available = available.filter(as_needed=True)
        medication = available.get(pk=medication_id)
    else:
        # Не передаём словарь целиком: владелец и режим не берутся из входных данных.
        medication = Medication(
            owner=owner,
            name=new_medication['name'],
            dosage=new_medication['dosage'],
            as_needed=True,
        )
        medication.full_clean()
        medication.save()

    day = taken_at.date()
    last_slot = medication.intakes.filter(date=day).aggregate(last=Max('slot'))['last'] or 0
    # Даже при ещё не построенном расписании дополнительная запись не занимает план.
    planned_slots = 0 if medication.as_needed else medication.daily_doses
    intake = MedicationIntake(
        medication=medication,
        date=day,
        slot=max(last_slot, planned_slots) + 1,
        is_extra=True,
        taken=True,
        taken_at=taken_at,
        reason=reason,
    )
    intake.full_clean()
    intake.save()
    return intake


def sync_intakes(medication):
    """Согласовать невыполненные приёмы с курсом, сохранить выполненную историю.

    Вызывать внутри transaction.atomic() вместе с сохранением препарата.
    Повторный вызов не создаёт дубликаты; дополнительные приёмы не входят в план.
    """
    intakes = medication.intakes
    if medication.as_needed:
        intakes.filter(taken=False, is_extra=False).delete()
        return
    intakes.filter(taken=False, is_extra=False).exclude(
        date__range=(medication.start_date, medication.end_date)
    ).delete()
    intakes.filter(taken=False, is_extra=False, slot__gt=medication.daily_doses).delete()
    day = medication.start_date
    while day <= medication.end_date:
        # Дополнительные записи не должны занимать слоты ежедневного плана.
        last_slot = max(
            medication.daily_doses, *(intakes.filter(date=day).values_list('slot', flat=True)), 0
        )
        for extra in intakes.filter(
            date=day, is_extra=True, slot__lte=medication.daily_doses
        ).order_by('slot'):
            last_slot += 1
            extra.slot = last_slot
            extra.save(update_fields=['slot'])
        rows = {i.slot: i for i in intakes.filter(date=day, is_extra=False)}
        # Сначала освобождаем время невыполненных слотов для перестановки времён.
        intakes.filter(date=day, taken=False, is_extra=False).update(scheduled_time=None)
        for slot in range(1, medication.daily_doses + 1):
            existing = rows.get(slot)
            if existing and existing.taken:
                continue
            value = (
                medication.scheduled_times[slot - 1]
                if len(medication.scheduled_times) >= slot
                else None
            )
            scheduled = time.fromisoformat(value) if value else None
            # Выполненная историческая запись может занимать это время.
            if (
                scheduled
                and intakes.filter(date=day, scheduled_time=scheduled, taken=True).exists()
            ):
                scheduled = None
            if existing:
                existing.scheduled_time = scheduled
                existing.save(update_fields=['scheduled_time'])
            else:
                MedicationIntake.objects.create(
                    medication=medication, date=day, slot=slot, scheduled_time=scheduled
                )
        if day == medication.end_date:
            break
        day += timedelta(days=1)
