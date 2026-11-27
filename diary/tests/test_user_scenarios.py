"""ЛЗ 13: модульные проверки и основные пользовательские сценарии."""

from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import Client, SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from diary.models import HealthEntry, Medication
from diary.validators import DIARY_MIN_DATE, validate_diary_date
from diary.views import diary_search_excerpt

from .base import FormDataTestCase


class DiaryUnitTests(SimpleTestCase):
    """Отдельные функции проверяются без запросов к базе и HTTP."""

    def test_excerpt_finds_text_ignoring_case(self):
        entry = SimpleNamespace(symptoms='Сильная головная боль', note=None)
        result = diary_search_excerpt(entry, 'ГОЛОВНАЯ')
        self.assertEqual(result['label'], 'Симптомы')
        self.assertEqual(result['before'], 'Сильная ')
        self.assertEqual(result['match'], 'головная')
        self.assertEqual(result['after'], ' боль')

    def test_excerpt_handles_missing_text(self):
        entry = SimpleNamespace(symptoms='', note=None)
        self.assertIsNone(diary_search_excerpt(entry, 'боль'))

    def test_date_validator_accepts_boundary_and_rejects_earlier_date(self):
        from datetime import timedelta

        validate_diary_date(DIARY_MIN_DATE)
        with self.assertRaises(ValidationError):
            validate_diary_date(DIARY_MIN_DATE - timedelta(days=1))


class UserScenarioTests(FormDataTestCase):
    """HTTP, формы, сессия, шаблоны и база проверяются совместно."""

    def setUp(self):
        super().setUp()
        self.client = Client(enforce_csrf_checks=True)

    def post_form(self, url, data=None, *, headers=None):
        # Получаем форму и действующий CSRF-токен перед отправкой.
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        token = self.client.cookies['csrftoken'].value
        return self.client.post(url, data or {}, headers={'X-CSRFToken': token, **(headers or {})})

    def sign_in(self):
        response = self.post_form(
            reverse('login'),
            {'username': self.user.username, 'password': 'Own-Test-Pass-839!'},
        )
        self.assertRedirects(response, reverse('dashboard'))

    def test_login_wrong_password_and_logout(self):
        # Закрытая страница направляет гостя на вход.
        response = self.client.get(reverse('diary_list'))
        self.assertRedirects(response, reverse('login') + '?next=' + reverse('diary_list'))
        response = self.post_form(
            reverse('login'), {'username': self.user.username, 'password': 'wrong'}
        )
        self.assertTrue(response.context['form'].errors)
        self.assertNotIn('_auth_user_id', self.client.session)

        self.sign_in()
        self.assertContains(self.client.get(reverse('diary_list')), 'Дневник самочувствия')
        token = self.client.cookies['csrftoken'].value
        response = self.client.post(reverse('logout'), headers={'X-CSRFToken': token})
        self.assertRedirects(response, reverse('login'))
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.get(reverse('diary_list')).status_code, 302)

    def test_diary_invalid_input_then_create_search_edit_delete(self):
        self.sign_in()
        data = {**self.entry_data, 'date': timezone.localdate().isoformat(), 'has_pain': 'yes'}

        # Ошибка ввода не создаёт запись. Затем пользователь исправляет данные.
        response = self.post_form(reverse('diary_create'), {**data, 'pain_intensity': 11})
        self.assertIn('pain_intensity', response.context['form'].errors)
        self.assertFalse(HealthEntry.objects.filter(owner=self.user).exists())

        data.update(pain_intensity=4, note='Тестовая заметка ЛЗ 13')
        self.assertRedirects(self.post_form(reverse('diary_create'), data), reverse('dashboard'))
        entry = HealthEntry.objects.get(owner=self.user)
        response = self.client.get(
            reverse('diary_list'),
            {'q': 'заметка ЛЗ 13'},
            headers={'X-Diary-Fragment': '1'},
        )
        self.assertTemplateUsed(response, 'diary/list_fragment.html')
        self.assertEqual([item.pk for item in response.context['entries']], [entry.pk])

        response = self.post_form(
            reverse('diary_update', args=[entry.pk]), {**data, 'note': 'Исправленная заметка'}
        )
        self.assertRedirects(response, reverse('dashboard'))
        entry.refresh_from_db()
        self.assertEqual(entry.note, 'Исправленная заметка')
        self.assertContains(
            self.client.get(reverse('diary_detail', args=[entry.pk])), 'Исправленная заметка'
        )
        self.assertRedirects(
            self.post_form(reverse('diary_delete', args=[entry.pk])), reverse('dashboard')
        )
        self.assertFalse(HealthEntry.objects.filter(pk=entry.pk).exists())
        self.assertEqual(self.client.get(reverse('diary_detail', args=[entry.pk])).status_code, 404)

    def test_medication_schedule_mark_retry_unmark_delete(self):
        self.sign_in()
        today = timezone.localdate().isoformat()
        data = {**self.med_data, 'start_date': today, 'end_date': today, 'intake_mode': 'regular'}
        self.assertRedirects(
            self.post_form(reverse('medication_create'), data), reverse('medication_list')
        )
        medication = Medication.objects.get(owner=self.user)
        intake = medication.intakes.get()
        self.assertEqual(intake.slot, 1)
        self.assertFalse(intake.taken)
        self.assertContains(self.client.get(reverse('dashboard')), medication.name)

        token = self.client.cookies['csrftoken'].value
        headers = {'X-CSRFToken': token, 'Accept': 'application/json'}
        url = reverse('toggle_intake', args=[intake.pk])
        response = self.client.post(url, {'taken': 'true'}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['taken'])
        intake.refresh_from_db()
        marked_at = intake.taken_at
        self.assertIsNotNone(marked_at)

        # Повтор запроса после потери ответа сохраняет ту же отметку и время.
        response = self.client.post(url, {'taken': 'true'}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['taken'])
        intake.refresh_from_db()
        self.assertEqual(intake.taken_at, marked_at)
        response = self.client.post(url, {'taken': 'false'}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['taken'])
        intake.refresh_from_db()
        self.assertFalse(intake.taken)
        self.assertIsNone(intake.taken_at)

        self.assertRedirects(
            self.post_form(reverse('medication_delete', args=[medication.pk])),
            reverse('medication_list'),
        )
        self.assertFalse(Medication.objects.filter(pk=medication.pk).exists())
        self.assertFalse(medication.intakes.exists())
