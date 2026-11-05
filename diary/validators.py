"""Общие ограничения для полей дневника."""

from datetime import date

from django.core.validators import MinValueValidator

DIARY_MIN_DATE = date(2025, 1, 1)
validate_diary_date = MinValueValidator(
    DIARY_MIN_DATE, message='Выберите дату не раньше 01.01.2025.'
)
