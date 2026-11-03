"""Проверки history."""

from datetime import date, time

from django.urls import reverse
from django.utils import timezone

from diary.models import Medication, MedicationIntake

from .base import FormDataTestCase, OwnedTestCase


class DashboardHistoryTests(FormDataTestCase):
    def test_dashboard_history(self):
        self.entry()
        MedicationIntake.objects.create(
            medication=self.med(), date=date.today(), scheduled_time=time(9)
        )
        for route in ['dashboard', 'history']:
            self.assertContains(self.client.get(reverse(route)), 'Тестовый препарат')


class HistoryDateTests(OwnedTestCase):
    def test_archive_includes_past_and_today_but_not_future(self):
        from datetime import timedelta

        today = timezone.localdate()
        med = Medication.objects.create(
            owner=self.user,
            name='Архив',
            dosage='1',
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=1),
        )
        rows = [
            MedicationIntake.objects.create(medication=med, date=today + timedelta(days=offset))
            for offset in [-1, 0, 1]
        ]
        response = self.client.get(reverse('history'))
        self.assertEqual(
            set(response.context['all_intakes'].values_list('pk', flat=True)),
            {rows[0].pk, rows[1].pk},
        )
        self.assertTrue(MedicationIntake.objects.filter(pk=rows[2].pk).exists())


class IntakePaginationTests(OwnedTestCase):
    def test_history_pages_are_limited_and_recent_before_future(self):
        from datetime import timedelta

        today = timezone.localdate()
        med = Medication.objects.create(
            owner=self.user,
            name='Длинный курс',
            dosage='1',
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=2),
        )
        for offset in range(-25, 3):
            MedicationIntake.objects.create(medication=med, date=today + timedelta(days=offset))
        url = reverse('medication_detail', args=[med.pk])
        first = self.client.get(url)
        second = self.client.get(url, {'page': 2})
        self.assertEqual(len(first.context['intakes']), 20)
        self.assertEqual(first.context['intakes'][0].date, today)
        self.assertEqual(len(second.context['intakes']), 8)
        self.assertFalse(
            set(i.pk for i in first.context['intakes'])
            & set(i.pk for i in second.context['intakes'])
        )
        self.assertEqual(MedicationIntake.objects.count(), 28)
        self.assertEqual(self.client.get(url, {'page': 'invalid'}).status_code, 200)
