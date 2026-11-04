"""Чтение списков: сначала ограничение владельцем, затем поиск и фильтры."""

from django.db.models import Count, F, Max, Q
from django.utils import timezone

from .db_functions import UnicodeLower
from .models import HealthEntry, Medication, MedicationIntake


def account_summary_for(user):
    """Сводка кабинета: только свои записи, без загрузки истории целиком."""
    today = timezone.localdate()
    medications = Medication.objects.filter(owner=user).aggregate(
        medication_count=Count('pk'),
        active_course_count=Count(
            'pk',
            filter=Q(
                as_needed=False,
                start_date__lte=today,
                end_date__gte=today,
            ),
        ),
    )
    entries = HealthEntry.objects.filter(owner=user).aggregate(
        entry_count=Count('pk'),
        last_entry_date=Max('date'),
    )
    taken_count = MedicationIntake.objects.filter(medication__owner=user, taken=True).count()
    return {**medications, **entries, 'taken_count': taken_count}


MEDICATION_ORDERING = {
    'name_asc': ('_name_lower', 'pk'),
    'name_desc': ('-_name_lower', '-pk'),
    'start_desc': (F('start_date').desc(nulls_last=True), '_name_lower', 'pk'),
    'start_asc': (F('start_date').asc(nulls_last=True), '_name_lower', 'pk'),
    'end_asc': (F('end_date').asc(nulls_last=True), '_name_lower', 'pk'),
}
HEALTH_ORDERING = {
    'date_desc': ('-date', '-pk'),
    'date_asc': ('date', 'pk'),
    'pain_desc': ('-pain_intensity', '-date', '-pk'),
    'pain_asc': ('pain_intensity', '-date', '-pk'),
}


def search_text(queryset, text, fields):
    """Буквальный поиск подстроки; ORM экранирует %, _ и параметры SQL."""
    if not text:
        return queryset
    condition = Q()
    aliases = {}
    for index, field in enumerate(fields):
        alias = f'_search_{index}'
        aliases[alias] = UnicodeLower(field)
        condition |= Q(**{f'{alias}__contains': text.lower()})
    return queryset.alias(**aliases).filter(condition)


def medications_for(user, filters):
    """filters — только cleaned_data успешно проверенной MedicationFilterForm."""
    records = Medication.objects.filter(owner=user).alias(_name_lower=UnicodeLower('name'))
    records = search_text(records, filters['q'], ['name', 'dosage', 'purpose', 'frequency'])
    section = filters['section']
    if section != 'all':
        records = records.filter(as_needed=section == 'occasional')
    today = timezone.localdate()
    status = filters['status']
    if status:
        records = records.filter(as_needed=False)
        if status == 'active':
            records = records.filter(start_date__lte=today, end_date__gte=today)
        elif status == 'upcoming':
            records = records.filter(start_date__gt=today)
        elif status == 'finished':
            records = records.filter(end_date__lt=today)
    # Набор SQL-полей задан в коде; строка из URL никогда не передаётся в order_by.
    return records.order_by(*MEDICATION_ORDERING[filters['sort']])


def health_entries_for(user, filters):
    """filters — cleaned_data HealthEntryFilterForm; границы диапазонов включительны."""
    records = HealthEntry.objects.filter(owner=user)
    records = search_text(records, filters['q'], ['symptoms', 'note'])
    lookups = {
        'date_from': 'date__gte',
        'date_to': 'date__lte',
        'condition': 'condition',
        'mood': 'mood',
        'pain_min': 'pain_intensity__gte',
        'pain_max': 'pain_intensity__lte',
    }
    for key, lookup in lookups.items():
        value = filters.get(key)
        # Ноль — допустимая оценка боли, его нельзя проверять через if value.
        if value is not None and value != '':
            records = records.filter(**{lookup: value})
    return records.order_by(*HEALTH_ORDERING[filters['sort']])
