"""Проверки intakes."""

from datetime import date, time
from unittest.mock import patch

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from diary.models import Medication, MedicationIntake

from .base import FormDataTestCase, OwnedTestCase


class PlannedIntakeTests(FormDataTestCase):
    def test_toggle_post_and_csrf(self):
        intake = MedicationIntake.objects.create(
            medication=self.med(), date=date.today(), scheduled_time=time(9)
        )
        url = reverse('toggle_intake', args=[intake.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        intake.refresh_from_db()
        self.assertFalse(intake.taken)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(url).status_code, 403)
        response = csrf_client.get(reverse('dashboard'))
        self.assertContains(response, 'csrfmiddlewaretoken')
        token = csrf_client.cookies['csrftoken'].value
        self.assertEqual(csrf_client.post(url, HTTP_X_CSRFTOKEN=token).status_code, 302)
        intake.refresh_from_db()
        self.assertTrue(intake.taken)
        self.client.post(url)
        intake.refresh_from_db()
        self.assertFalse(intake.taken)

    def test_actual_time_records_and_clears(self):
        from django.utils import timezone

        intake = MedicationIntake.objects.create(medication=self.med(), date=timezone.localdate())
        now = timezone.now()
        with patch('diary.views.timezone.now', return_value=now):
            self.client.post(reverse('toggle_intake', args=[intake.pk]))
        intake.refresh_from_db()
        self.assertEqual(intake.taken_at, now)
        self.assertContains(self.client.get(reverse('history')), 'Принято:')
        self.client.post(reverse('toggle_intake', args=[intake.pk]))
        intake.refresh_from_db()
        self.assertIsNone(intake.taken_at)
        self.assertFalse(intake.taken)

    def test_json_intake_update_is_idempotent(self):
        from django.utils import timezone

        intake = MedicationIntake.objects.create(medication=self.med(), date=timezone.localdate())
        url = reverse('toggle_intake', args=[intake.pk])
        response = self.client.post(url, {'taken': 'true'}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['taken'])
        intake.refresh_from_db()
        original_time = intake.taken_at
        self.client.post(url, {'taken': 'true'}, HTTP_ACCEPT='application/json')
        intake.refresh_from_db()
        self.assertEqual(intake.taken_at, original_time)
        response = self.client.post(url, {'taken': 'false'}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.json(), {'taken': False, 'taken_at': None})
        intake.refresh_from_db()
        self.assertFalse(intake.taken)
        self.assertIsNone(intake.taken_at)

    def test_json_rejects_invalid_state_without_change(self):
        from django.utils import timezone

        intake = MedicationIntake.objects.create(medication=self.med(), date=timezone.localdate())
        response = self.client.post(
            reverse('toggle_intake', args=[intake.pk]),
            {'taken': 'bad'},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 400)
        intake.refresh_from_db()
        self.assertFalse(intake.taken)


class OptionalIntakeTests(OwnedTestCase):
    def test_as_needed_creates_only_actual_intakes(self):
        today = timezone.localdate()
        data = dict(
            name='По необходимости',
            dosage='1 таблетка',
            start_date=today,
            end_date=today,
            daily_doses=1,
            as_needed='on',
        )
        self.client.post(reverse('medication_create'), data)
        medication = Medication.objects.get()
        self.assertTrue(medication.as_needed)
        self.assertEqual(medication.scheduled_times, [])
        self.assertFalse(medication.intakes.exists())
        url = reverse('record_as_needed', args=[medication.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(medication.intakes.count(), 2)
        for intake in medication.intakes.all():
            self.assertTrue(intake.taken)
            self.assertIsNotNone(intake.taken_at)
            self.assertIsNone(intake.scheduled_time)
            self.assertFalse(intake.is_overdue)
        self.assertContains(self.client.get(reverse('dashboard')), 'По необходимости')

    def test_overdue_status_in_history_and_detail(self):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        medication = Medication.objects.create(
            owner=self.user,
            name='Курс',
            dosage='1',
            start_date=today - timedelta(days=1),
            end_date=today,
        )
        intake = MedicationIntake.objects.create(
            medication=medication, date=today - timedelta(days=1)
        )
        self.assertTrue(intake.is_overdue)
        self.assertContains(self.client.get(reverse('history')), 'Пропущено')
        self.assertContains(
            self.client.get(reverse('medication_detail', args=[medication.pk])), 'Пропущено'
        )
        intake.taken = True
        intake.save()
        self.assertFalse(intake.is_overdue)


class ClearedTimeTests(OwnedTestCase):
    def test_undo_uses_current_schedule_instead_of_historical_time(self):
        from django.utils import timezone

        today = timezone.localdate()
        med = Medication.objects.create(
            owner=self.user,
            name='Без времени',
            dosage='1',
            start_date=today,
            end_date=today,
            scheduled_times=[None],
        )
        intake = MedicationIntake.objects.create(
            medication=med, date=today, taken=True, taken_at=timezone.now(), scheduled_time=time(9)
        )
        self.client.post(reverse('toggle_intake', args=[intake.pk]), {'taken': 'false'})
        intake.refresh_from_db()
        self.assertIsNone(intake.scheduled_time)
        self.assertIsNone(intake.taken_at)
        self.assertFalse(intake.is_overdue)


class QuickIntakeTests(OwnedTestCase):
    def test_existing_medication_extra_dose_does_not_change_goal(self):
        from django.utils import timezone

        today = timezone.localdate()
        med = Medication.objects.create(
            owner=self.user,
            name='Курс',
            dosage='1 таблетка',
            start_date=today,
            end_date=today,
            scheduled_times=['07:00'],
        )
        planned = MedicationIntake.objects.create(
            medication=med, date=today, scheduled_time=time(7)
        )
        response = self.client.post(
            reverse('quick_intake'), {'mode': 'existing', 'medication': med.pk}
        )
        self.assertRedirects(response, reverse('dashboard'))
        extra = med.intakes.get(is_extra=True)
        self.assertTrue(extra.taken)
        self.assertIsNotNone(extra.taken_at)
        self.assertIsNone(extra.scheduled_time)
        self.assertFalse(extra.is_overdue)
        planned.refresh_from_db()
        self.assertFalse(planned.taken)
        self.assertEqual(self.client.get(reverse('dashboard')).context['total_intakes'], 1)
        med.refresh_from_db()
        self.assertFalse(med.as_needed)
        self.assertEqual(med.scheduled_times, ['07:00'])

    def test_new_medication_records_once_without_schedule(self):
        self.client.post(
            reverse('quick_intake'), {'mode': 'new', 'name': 'Разовый', 'dosage': '1 пакетик'}
        )
        med = Medication.objects.get()
        self.assertTrue(med.as_needed)
        self.assertEqual(med.intakes.count(), 1)
        self.assertTrue(med.intakes.get().is_extra)
        self.assertEqual(self.client.get(reverse('dashboard')).context['total_intakes'], 0)
        self.assertContains(self.client.get(reverse('history')), 'Разовый')

    def test_invalid_quick_intake_creates_nothing(self):
        for data in [
            {'mode': 'new', 'name': 'Нет дозировки'},
            {'mode': 'existing'},
            {'mode': 'existing', 'medication': '999999'},
        ]:
            response = self.client.post(reverse('quick_intake'), data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['quick_form'].errors)
        self.assertFalse(Medication.objects.exists())
        self.assertFalse(MedicationIntake.objects.exists())


class PastIntakeTests(OwnedTestCase):
    def make_med(self, today):
        return Medication.objects.create(
            owner=self.user, name='Лекарство', dosage='1', start_date=today, end_date=today
        )

    def test_past_intake_uses_selected_day_and_local_time(self):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        value = yesterday.strftime('%Y-%m-%d') + 'T21:30'
        response = self.client.post(
            reverse('quick_intake'),
            {'mode': 'new', 'name': 'Вчерашний', 'dosage': '1', 'taken_at': value},
        )
        self.assertRedirects(response, reverse('dashboard'))
        intake = MedicationIntake.objects.get()
        self.assertEqual(intake.date, yesterday)
        self.assertEqual(timezone.localtime(intake.taken_at).strftime('%Y-%m-%dT%H:%M'), value)
        self.assertIsNone(intake.medication.start_date)
        self.assertNotContains(self.client.get(reverse('dashboard')), '<strong>Вчерашний</strong>')
        self.assertContains(self.client.get(reverse('history')), 'Вчерашний')

    def test_future_time_and_invalid_timestamp_save_nothing(self):
        from datetime import timedelta

        from django.utils import timezone

        for value in [
            (timezone.localtime() + timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M'),
            (timezone.localtime() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
            'не дата',
        ]:
            response = self.client.post(
                reverse('quick_intake'),
                {'mode': 'new', 'name': 'Будущий', 'dosage': '1', 'taken_at': value},
            )
            self.assertTrue(response.context['quick_form'].errors)
        self.assertFalse(Medication.objects.exists())
        self.assertFalse(MedicationIntake.objects.exists())

    def test_past_extra_dose_does_not_change_current_plan(self):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        med = self.make_med(today)
        MedicationIntake.objects.create(medication=med, date=today)
        self.client.post(
            reverse('quick_intake'),
            {
                'mode': 'existing',
                'medication': med.pk,
                'taken_at': (today - timedelta(days=1)).strftime('%Y-%m-%d') + 'T23:59',
            },
        )
        dashboard = self.client.get(reverse('dashboard'))
        self.assertEqual(dashboard.context['total_intakes'], 1)
        self.assertEqual(dashboard.context['taken_intakes'], 0)
        self.assertFalse(dashboard.context['as_needed_intakes'].exists())

    def test_dated_statuses_with_and_without_clock(self):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        med = self.make_med(today)
        intake = MedicationIntake(medication=med, date=today, scheduled_time=None)
        self.assertFalse(intake.is_overdue)
        intake.date = today - timedelta(days=1)
        self.assertTrue(intake.is_overdue)
        intake.is_extra = True
        self.assertFalse(intake.is_overdue)
        intake.is_extra = False
        intake.date = today + timedelta(days=1)
        self.assertFalse(intake.is_overdue)


class IntakeReasonTests(OwnedTestCase):
    def test_reason_is_optional_and_belongs_to_single_intake(self):
        self.client.post(
            reverse('quick_intake'),
            {'mode': 'new', 'name': 'Лекарство', 'dosage': '1', 'reason': 'Поднялась температура'},
        )
        med = Medication.objects.get()
        self.client.post(reverse('quick_intake'), {'mode': 'existing', 'medication': med.pk})
        self.assertEqual(
            list(med.intakes.order_by('id').values_list('reason', flat=True)),
            ['Поднялась температура', ''],
        )
        self.assertContains(self.client.get(reverse('history')), 'Поднялась температура')
        self.assertContains(
            self.client.get(reverse('medication_detail', args=[med.pk])), 'Поднялась температура'
        )
        self.assertIsNone(med.start_date)
        self.assertIsNone(med.end_date)

    def test_reason_length_rejected_without_records(self):
        response = self.client.post(
            reverse('quick_intake'),
            {'mode': 'new', 'name': 'Лекарство', 'dosage': '1', 'reason': 'a' * 301},
        )
        self.assertIn('reason', response.context['quick_form'].errors)
        self.assertFalse(MedicationIntake.objects.exists())
