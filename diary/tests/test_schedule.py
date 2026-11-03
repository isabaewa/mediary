"""Проверки schedule."""

from datetime import date, time

from django.urls import reverse
from django.utils import timezone

from diary.models import Medication, MedicationIntake

from .base import FormDataTestCase, OwnedTestCase


class ScheduleTests(FormDataTestCase):
    def test_schedule_update_preserves_taken(self):
        self.client.post(reverse('medication_create'), self.med_data)
        med = Medication.objects.get()
        taken = med.intakes.get(date='2026-10-01')
        taken.taken = True
        taken.save()
        kept = med.intakes.get(date='2026-10-02')
        data = {**self.med_data, 'start_date': '2026-10-02', 'end_date': '2026-10-04'}
        self.client.post(reverse('medication_update', args=[med.pk]), data)
        taken.refresh_from_db()
        self.assertTrue(taken.taken)
        self.assertTrue(med.intakes.filter(pk=kept.pk).exists())
        self.assertEqual(med.intakes.count(), 4)
        self.client.post(
            reverse('medication_update', args=[med.pk]), {**data, 'end_date': '2026-10-02'}
        )
        self.assertEqual(med.intakes.count(), 2)

    def test_change_time_keeps_completed_intake(self):
        self.client.post(reverse('medication_create'), self.med_data)
        med = Medication.objects.get()
        taken = med.intakes.first()
        taken.taken = True
        taken.save()
        self.client.post(
            reverse('medication_update', args=[med.pk]), {**self.med_data, 'dose_time_1': '18:30'}
        )
        taken.refresh_from_db()
        self.assertTrue(taken.taken)
        self.assertEqual(taken.scheduled_time, time(9))
        self.assertEqual(med.intakes.count(), 3)
        self.assertTrue(
            all(i.scheduled_time == time(18, 30) for i in med.intakes.filter(taken=False))
        )

    def test_restore_missing_slots_is_idempotent(self):
        from diary.services import sync_intakes

        med = self.med()
        taken = MedicationIntake.objects.create(
            medication=med, date=date(2026, 10, 1), scheduled_time=time(8), taken=True
        )
        med.refresh_from_db()
        sync_intakes(med)
        sync_intakes(med)
        taken.refresh_from_db()
        self.assertTrue(taken.taken)
        self.assertEqual(taken.scheduled_time, time(8))
        self.assertEqual(med.intakes.count(), 3)

    def test_three_doses_without_time(self):
        data = {**self.med_data, 'daily_doses': 3, 'dose_time_1': ''}
        self.assertEqual(self.client.post(reverse('medication_create'), data).status_code, 302)
        med = Medication.objects.get()
        self.assertEqual(med.intakes.count(), 9)
        self.assertFalse(med.intakes.filter(scheduled_time__isnull=False).exists())
        self.assertEqual(
            list(med.intakes.filter(date='2026-10-01').values_list('slot', flat=True)), [1, 2, 3]
        )

    def test_optional_times_and_duplicate_validation(self):
        data = {
            **self.med_data,
            'daily_doses': 3,
            'dose_time_1': '',
            'dose_time_2': '14:00',
            'dose_time_3': '',
        }
        self.client.post(reverse('medication_create'), data)
        med = Medication.objects.get()
        self.assertEqual(med.scheduled_times, [None, '14:00', None])
        response = self.client.post(
            reverse('medication_update', args=[med.pk]), {**data, 'dose_time_3': '14:00'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        med.refresh_from_db()
        self.assertEqual(med.scheduled_times, [None, '14:00', None])

    def test_change_count_keeps_completed_extra_slot(self):
        self.client.post(reverse('medication_create'), {**self.med_data, 'daily_doses': 3})
        med = Medication.objects.get()
        done = med.intakes.get(date='2026-10-01', slot=3)
        done.taken = True
        done.save()
        self.client.post(reverse('medication_update', args=[med.pk]), self.med_data)
        self.assertEqual(med.intakes.count(), 4)
        done.refresh_from_db()
        self.assertTrue(done.taken)


class FinishedCourseTests(OwnedTestCase):
    def test_completed_course_disappears_from_goal_without_losing_history(self):
        from datetime import timedelta

        today = timezone.localdate()
        med = Medication.objects.create(
            owner=self.user,
            name='Завершённый',
            dosage='1',
            start_date=today - timedelta(days=2),
            end_date=today - timedelta(days=1),
        )
        intake = MedicationIntake.objects.create(
            medication=med, date=today, taken=True, taken_at=timezone.now()
        )
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['total_intakes'], 0)
        self.assertFalse(response.context['today_intakes'])
        self.assertContains(self.client.get(reverse('history')), 'Завершённый')
        self.assertTrue(MedicationIntake.objects.filter(pk=intake.pk).exists())

    def test_future_course_not_in_today_goal(self):
        from datetime import timedelta

        today = timezone.localdate()
        med = Medication.objects.create(
            owner=self.user,
            name='Будущий курс',
            dosage='1',
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=2),
        )
        MedicationIntake.objects.create(medication=med, date=today)
        self.assertEqual(self.client.get(reverse('dashboard')).context['total_intakes'], 0)


class ScheduleEvolutionTests(OwnedTestCase):
    def make_med(self, today):
        return Medication.objects.create(
            owner=self.user, name='Лекарство', dosage='1', start_date=today, end_date=today
        )

    def test_expanding_daily_plan_preserves_extra_and_creates_all_slots(self):
        from diary.services import sync_intakes

        today = timezone.localdate()
        med = self.make_med(today)
        sync_intakes(med)
        extra = MedicationIntake.objects.create(
            medication=med, date=today, slot=2, is_extra=True, taken=True, taken_at=timezone.now()
        )
        timestamp = extra.taken_at
        med.daily_doses = 3
        med.scheduled_times = [None, None, None]
        med.save()
        sync_intakes(med)
        sync_intakes(med)
        self.assertEqual(
            set(med.intakes.filter(is_extra=False).values_list('slot', flat=True)), {1, 2, 3}
        )
        extra.refresh_from_db()
        self.assertEqual(extra.taken_at, timestamp)
        self.assertTrue(extra.is_extra)
        self.assertGreater(extra.slot, 3)
        self.assertEqual(self.client.get(reverse('dashboard')).context['total_intakes'], 3)

    def test_converting_as_needed_to_daily_preserves_recorded_dose(self):
        from diary.services import sync_intakes

        today = timezone.localdate()
        med = self.make_med(today)
        med.as_needed = True
        med.save()
        extra = MedicationIntake.objects.create(
            medication=med, date=today, is_extra=True, taken=True, taken_at=timezone.now()
        )
        med.as_needed = False
        med.save()
        sync_intakes(med)
        self.assertEqual(med.intakes.filter(is_extra=False).count(), 1)
        extra.refresh_from_db()
        self.assertTrue(extra.taken)
