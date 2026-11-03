"""Проверки health."""

from django.urls import reverse
from django.utils import timezone

from diary.models import HealthEntry

from .base import FormDataTestCase, OwnedTestCase


class HealthCRUDTests(FormDataTestCase):
    def test_diary_full_crud(self):
        self.assertRedirects(
            self.client.post(reverse('diary_create'), self.entry_data), reverse('dashboard')
        )
        entry = HealthEntry.objects.get()
        for route in ['diary_list', 'diary_detail', 'diary_update', 'diary_delete']:
            args = [] if route.endswith('list') else [entry.pk]
            self.assertEqual(self.client.get(reverse(route, args=args)).status_code, 200)
        self.assertTrue(HealthEntry.objects.filter(pk=entry.pk).exists())
        self.client.post(
            reverse('diary_update', args=[entry.pk]),
            {**self.entry_data, 'pain_intensity': 10, 'has_pain': 'yes', 'note': 'Изменено'},
        )
        entry.refresh_from_db()
        self.assertEqual(entry.pain_intensity, 10)
        self.assertEqual(entry.note, 'Изменено')
        self.client.post(reverse('diary_delete', args=[entry.pk]))
        self.assertFalse(HealthEntry.objects.exists())

    def test_diary_invalid_values_and_duplicate(self):
        for field, value in [
            ('pain_intensity', -1),
            ('pain_intensity', 11),
            ('mood', 'invalid'),
            ('condition', 'invalid'),
            ('date', ''),
        ]:
            response = self.client.post(reverse('diary_create'), {**self.entry_data, field: value})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
            self.assertContains(response, 'role="alert"')
            self.assertFalse(HealthEntry.objects.exists())
        self.entry()
        response = self.client.post(reverse('diary_create'), self.entry_data)
        self.assertIn('date', response.context['form'].errors)
        self.assertEqual(HealthEntry.objects.count(), 1)

    def test_no_pain_can_omit_scale_and_clears_old_value(self):
        data = {**self.entry_data}
        data.pop('pain_intensity')
        self.assertEqual(self.client.post(reverse('diary_create'), data).status_code, 302)
        entry = HealthEntry.objects.get()
        self.assertEqual(entry.pain_intensity, 0)
        entry.pain_intensity = 7
        entry.save()
        self.client.post(reverse('diary_update', args=[entry.pk]), {**data, 'pain_intensity': 7})
        entry.refresh_from_db()
        self.assertEqual(entry.pain_intensity, 0)

    def test_yes_pain_requires_valid_positive_score(self):
        for value in ['', 0, -1, 11]:
            response = self.client.post(
                reverse('diary_create'),
                {**self.entry_data, 'has_pain': 'yes', 'pain_intensity': value},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn('pain_intensity', response.context['form'].errors)
        response = self.client.post(
            reverse('diary_create'), {**self.entry_data, 'has_pain': 'yes', 'pain_intensity': 4}
        )
        self.assertEqual(response.status_code, 302)
        entry = HealthEntry.objects.get()
        self.assertEqual(entry.pain_intensity, 4)
        response = self.client.get(reverse('diary_update', args=[entry.pk]))
        self.assertEqual(response.context['form']['has_pain'].value(), 'yes')


class HealthDateTests(OwnedTestCase):
    def test_future_diary_entry_is_rejected(self):
        from datetime import timedelta

        response = self.client.post(
            reverse('diary_create'),
            dict(
                date=timezone.localdate() + timedelta(days=1),
                mood='Хорошее',
                condition='Нормальное',
                symptoms='Нет',
                has_pain='no',
            ),
        )
        self.assertTrue(response.context['form'].errors)
        self.assertFalse(HealthEntry.objects.exists())
