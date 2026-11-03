"""Проверки medications."""

from datetime import date, time
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

from diary.models import Medication, MedicationIntake

from .base import FormDataTestCase, OwnedTestCase


class MedicationCRUDTests(FormDataTestCase):
    def test_medication_full_crud(self):
        self.assertRedirects(
            self.client.post(reverse('medication_create'), self.med_data),
            reverse('medication_list'),
        )
        med = Medication.objects.get()
        self.assertEqual(med.intakes.count(), 3)
        self.assertEqual(med.intakes.first().scheduled_time, time(9))
        for route in [
            'medication_list',
            'medication_detail',
            'medication_update',
            'medication_delete',
        ]:
            args = [] if route.endswith('list') else [med.pk]
            self.assertContains(self.client.get(reverse(route, args=args)), med.name)
        self.assertTrue(Medication.objects.filter(pk=med.pk).exists())
        self.client.post(
            reverse('medication_update', args=[med.pk]), {**self.med_data, 'name': 'Новое имя'}
        )
        med.refresh_from_db()
        self.assertEqual(med.name, 'Новое имя')
        self.assertEqual(med.intakes.count(), 3)
        self.client.post(reverse('medication_delete', args=[med.pk]))
        self.assertFalse(Medication.objects.exists())
        self.assertFalse(MedicationIntake.objects.exists())

    def test_invalid_course_not_saved(self):
        response = self.client.post(
            reverse('medication_create'), {**self.med_data, 'end_date': '2026-09-01'}
        )
        self.assertContains(response, 'Дата окончания курса не может быть раньше')
        self.assertFalse(Medication.objects.exists())

    def test_course_and_schedule_atomic(self):
        with patch('diary.views.sync_intakes', side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('medication_create'), self.med_data)
        self.assertFalse(Medication.objects.exists())

    def test_purpose_and_selected_time(self):
        self.client.post(reverse('medication_create'), {**self.med_data, 'dose_time_1': '18:30'})
        med = Medication.objects.get()
        self.assertEqual(med.purpose, 'Головная боль')
        self.assertTrue(all(i.scheduled_time == time(18, 30) for i in med.intakes.all()))
        for route in ['medication_list', 'medication_detail', 'medication_update']:
            args = [] if route.endswith('list') else [med.pk]
            self.assertContains(self.client.get(reverse(route, args=args)), 'Головная боль')

    def test_course_status_uses_dates(self):
        med = self.med()
        med.start_date, med.end_date = date(2026, 10, 1), date(2026, 10, 3)
        for today, status in [
            (date(2026, 9, 30), 'Курс ещё не начался'),
            (date(2026, 10, 2), 'Активный курс'),
            (date(2026, 10, 4), 'Курс завершён'),
        ]:
            with patch('diary.models.timezone.localdate', return_value=today):
                self.assertEqual(med.course_status, status)

    def test_count_and_time_validation(self):
        for changes in [{'daily_doses': 0}, {'daily_doses': 13}, {'dose_time_1': '25:00'}]:
            response = self.client.post(reverse('medication_create'), {**self.med_data, **changes})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
        self.assertFalse(Medication.objects.exists())


class MedicationModeTests(OwnedTestCase):
    def test_occasional_medication_needs_no_dates_or_daily_count(self):
        response = self.client.post(
            reverse('medication_create'),
            {
                'intake_mode': 'occasional',
                'name': 'Иногда',
                'dosage': '1',
                'purpose': 'При симптомах',
            },
        )
        self.assertRedirects(response, reverse('medication_list'))
        med = Medication.objects.get()
        self.assertTrue(med.as_needed)
        self.assertIsNone(med.start_date)
        self.assertIsNone(med.end_date)
        self.assertEqual(med.scheduled_times, [])
        self.assertFalse(med.intakes.exists())
        self.assertEqual(med.course_status, 'Иногда')
        detail = self.client.get(reverse('medication_detail', args=[med.pk]))
        self.assertNotContains(detail, 'Сроки курса лечения')

    def test_regular_mode_requires_course_and_count(self):
        response = self.client.post(
            reverse('medication_create'), {'intake_mode': 'regular', 'name': 'Курс', 'dosage': '1'}
        )
        self.assertTrue(response.context['form'].errors)
        self.assertFalse(Medication.objects.exists())

    def test_switching_to_occasional_preserves_completed_history(self):
        from diary.services import sync_intakes

        today = timezone.localdate()
        med = Medication.objects.create(
            owner=self.user, name='Курс', dosage='1', start_date=today, end_date=today
        )
        sync_intakes(med)
        intake = med.intakes.get()
        intake.taken = True
        intake.taken_at = timezone.now()
        intake.save()
        self.client.post(
            reverse('medication_update', args=[med.pk]),
            {'intake_mode': 'occasional', 'name': 'Курс', 'dosage': '1'},
        )
        med.refresh_from_db()
        self.assertTrue(med.as_needed)
        self.assertIsNone(med.start_date)
        intake.refresh_from_db()
        self.assertTrue(intake.taken)
        self.assertEqual(self.client.get(reverse('dashboard')).context['total_intakes'], 0)
