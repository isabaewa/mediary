"""Профиль меняет только текущий аккаунт и не раскрывает чужие записи."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from diary.models import HealthEntry, Medication, MedicationIntake

from .base import OwnedTestCase


class ProfileTests(OwnedTestCase):
    def data(self, **changes):
        return {
            'username': self.user.username,
            'first_name': '',
            'last_name': '',
            'email': '',
            **changes,
        }

    def test_anonymous_cannot_read_or_edit_profile(self):
        self.client.logout()
        for method in ['get', 'post']:
            response = getattr(self.client, method)(reverse('profile'), self.data())
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse('login')))

    def test_empty_profile_and_account_link(self):
        response = self.client.get(reverse('profile'))
        self.assertContains(response, 'Личный кабинет')
        self.assertContains(response, self.user.username)
        self.assertContains(response, reverse('password_change'))
        self.assertEqual(
            response.context['summary'],
            {
                'medication_count': 0,
                'active_course_count': 0,
                'entry_count': 0,
                'last_entry_date': None,
                'taken_count': 0,
            },
        )

    def test_profile_update_keeps_login_and_password(self):
        password_hash = self.user.password
        response = self.client.post(
            reverse('profile'),
            self.data(
                username='updated_test_user',
                first_name='Анна',
                last_name='Тестовая',
                email='profile@example.test',
            ),
        )
        self.assertRedirects(response, reverse('profile'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'updated_test_user')
        self.assertEqual(self.user.first_name, 'Анна')
        self.assertEqual(self.user.email, 'profile@example.test')
        self.assertEqual(self.user.password, password_hash)
        self.assertEqual(self.client.session['_auth_user_id'], str(self.user.pk))

    def test_email_and_names_are_optional(self):
        self.assertRedirects(self.client.post(reverse('profile'), self.data()), reverse('profile'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, '')

    def test_duplicate_login_and_invalid_email_do_not_save_partial_changes(self):
        get_user_model().objects.create_user(username='occupied_test_user')
        original = self.user.username
        for changes, field in [
            ({'username': 'occupied_test_user'}, 'username'),
            ({'username': 'invalid space'}, 'username'),
            ({'email': 'invalid'}, 'email'),
            ({'first_name': 'x' * 151}, 'first_name'),
        ]:
            with self.subTest(field=field):
                response = self.client.post(
                    reverse('profile'),
                    self.data(
                        **{'last_name': 'Несохранённая', **changes},
                    ),
                )
                self.assertIn(field, response.context['form'].errors)
                self.user.refresh_from_db()
                self.assertEqual(self.user.username, original)
                self.assertEqual(self.user.last_name, '')
                self.assertEqual(response.context['user'].last_name, '')

    def test_extra_post_fields_cannot_modify_permissions_or_another_user(self):
        other = get_user_model().objects.create_user(username='other_profile_test_user')
        response = self.client.post(
            reverse('profile'),
            self.data(
                first_name='Моё имя',
                id=other.pk,
                pk=other.pk,
                owner=other.pk,
                is_staff='on',
                is_superuser='on',
                is_active='',
                password='tampered',
            ),
        )
        self.assertRedirects(response, reverse('profile'))
        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.check_password('Own-Test-Pass-839!'))
        self.assertEqual(self.user.first_name, 'Моё имя')
        self.assertEqual(other.first_name, '')

    def test_profile_post_requires_csrf_and_rejects_put(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('profile'), self.data()).status_code, 403)
        self.assertEqual(self.client.put(reverse('profile')).status_code, 405)

    def test_profile_escapes_names_as_text(self):
        response = self.client.post(
            reverse('profile'), self.data(first_name='<script>alert(1)</script>'), follow=True
        )
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;')

    def test_summary_counts_only_own_records_and_inclusive_active_courses(self):
        today = timezone.localdate()
        for user in [
            self.user,
            get_user_model().objects.create_user(username='other_summary_user'),
        ]:
            active = Medication.objects.create(
                owner=user, name='Активный', dosage='1', start_date=today, end_date=today
            )
            Medication.objects.create(
                owner=user,
                name='Будущий',
                dosage='1',
                start_date=today + timedelta(days=1),
                end_date=today + timedelta(days=2),
            )
            Medication.objects.create(
                owner=user,
                name='Прошлый',
                dosage='1',
                start_date=today - timedelta(days=2),
                end_date=today - timedelta(days=1),
            )
            Medication.objects.create(owner=user, name='Иногда', dosage='1', as_needed=True)
            MedicationIntake.objects.create(medication=active, date=today, slot=1, taken=True)
            MedicationIntake.objects.create(medication=active, date=today, slot=2, taken=False)
            HealthEntry.objects.create(
                owner=user, date=today, mood='Хорошее', condition='Нормальное', pain_intensity=0
            )
        response = self.client.get(reverse('profile'))
        self.assertEqual(
            response.context['summary'],
            {
                'medication_count': 4,
                'active_course_count': 1,
                'entry_count': 1,
                'last_entry_date': today,
                'taken_count': 1,
            },
        )
