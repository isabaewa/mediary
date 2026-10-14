from datetime import timedelta, time
from .models import MedicationIntake


def sync_intakes(medication):
    """Согласовать невыполненные приёмы с курсом, сохранить выполненную историю."""
    intakes = medication.intakes
    if medication.as_needed:
        intakes.filter(taken=False, is_extra=False).delete()
        return
    intakes.filter(taken=False, is_extra=False).exclude(date__range=(medication.start_date, medication.end_date)).delete()
    intakes.filter(taken=False, is_extra=False, slot__gt=medication.daily_doses).delete()
    day = medication.start_date
    while day <= medication.end_date:
        # Дополнительные записи не должны занимать слоты ежедневного плана.
        last_slot = max(medication.daily_doses, *(intakes.filter(date=day).values_list('slot', flat=True)), 0)
        for extra in intakes.filter(date=day, is_extra=True, slot__lte=medication.daily_doses).order_by('slot'):
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
            value = medication.scheduled_times[slot-1] if len(medication.scheduled_times) >= slot else None
            scheduled = time.fromisoformat(value) if value else None
            # Выполненная историческая запись может занимать это время.
            if scheduled and intakes.filter(date=day, scheduled_time=scheduled, taken=True).exists():
                scheduled = None
            if existing:
                existing.scheduled_time = scheduled
                existing.save(update_fields=['scheduled_time'])
            else:
                MedicationIntake.objects.create(medication=medication, date=day, slot=slot, scheduled_time=scheduled)
        if day == medication.end_date:
            break
        day += timedelta(days=1)
