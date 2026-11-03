"""Проверки integrity."""

from datetime import date, time

from django.urls import reverse

from diary.models import MedicationIntake

from .base import FormDataTestCase


class IntegrityTests(FormDataTestCase):
    def test_form_controls_and_date(self):
        response = self.client.get(reverse('diary_create'))
        self.assertContains(response, 'value="Хорошее"')
        self.assertContains(response, 'value="Нормальное"')
        self.assertContains(response, 'name="date"', count=1)
        entry = self.entry()
        response = self.client.get(reverse('diary_update', args=[entry.pk]))
        self.assertContains(response, 'value="2026-10-01"')
        med = self.med()
        response = self.client.get(reverse('medication_update', args=[med.pk]))
        self.assertContains(response, 'value="2026-10-01"')

    def test_missing_objects(self):
        for route in [
            'medication_detail',
            'medication_update',
            'medication_delete',
            'diary_detail',
            'diary_update',
            'diary_delete',
        ]:
            self.assertEqual(self.client.get(reverse(route, args=[999])).status_code, 404)
        self.assertEqual(self.client.post(reverse('toggle_intake', args=[999])).status_code, 404)

    def test_model_validation_and_database_constraints(self):
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError, transaction

        med = self.med()
        med.end_date = date(2026, 9, 1)
        with self.assertRaises(ValidationError):
            med.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            med.save()
        entry = self.entry()
        entry.pain_intensity = 11
        with self.assertRaises(ValidationError):
            entry.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            entry.save()
        data = dict(medication=med, date=date(2026, 10, 1), scheduled_time=time(9))
        MedicationIntake.objects.create(**data)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MedicationIntake.objects.create(**data)
