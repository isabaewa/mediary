"""Проверки auth."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from diary.models import HealthEntry, Medication, MedicationIntake


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AuthenticationTests(TestCase):
    def setUp(self):
        self.password = 'Strong-Lab-Password-823!'
        self.owner = get_user_model().objects.create_user(username='owner', password=self.password)
        self.other = get_user_model().objects.create_user(username='other', password=self.password)
        self.today = timezone.localdate()
        self.med = Medication.objects.create(
            owner=self.owner,
            name='Чужой препарат',
            dosage='1',
            start_date=self.today,
            end_date=self.today,
        )
        self.intake = MedicationIntake.objects.create(medication=self.med, date=self.today)
        self.entry = HealthEntry.objects.create(
            owner=self.owner,
            date=self.today,
            mood='Хорошее',
            condition='Нормальное',
            symptoms='Личная запись',
            pain_intensity=0,
        )

    def test_registration_hashes_password_and_creates_empty_account(self):
        response = self.client.post(
            reverse('signup'),
            {'username': 'newuser', 'password1': self.password, 'password2': self.password},
        )
        self.assertRedirects(response, reverse('login'))
        user = get_user_model().objects.get(username='newuser')
        self.assertNotEqual(user.password, self.password)
        self.assertTrue(user.check_password(self.password))
        self.assertFalse(user.medications.exists())
        self.assertFalse(user.health_entries.exists())

    def test_duplicate_username_weak_and_mismatched_passwords_rejected(self):
        for data in [
            {'username': 'owner', 'password1': self.password, 'password2': self.password},
            {'username': 'weak', 'password1': '123', 'password2': '123'},
            {'username': 'mismatch', 'password1': self.password, 'password2': 'different'},
        ]:
            response = self.client.post(reverse('signup'), data)
            self.assertTrue(response.context['form'].errors)
        self.assertEqual(get_user_model().objects.count(), 2)

    def test_anonymous_cannot_access_private_pages_or_post(self):
        for route, args in [
            ('dashboard', []),
            ('medication_list', []),
            ('medication_detail', [self.med.pk]),
            ('medication_update', [self.med.pk]),
            ('medication_delete', [self.med.pk]),
            ('diary_list', []),
            ('diary_detail', [self.entry.pk]),
            ('history', []),
            ('quick_intake', []),
        ]:
            response = self.client.get(reverse(route, args=args))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse('login')))
        response = self.client.post(reverse('toggle_intake', args=[self.intake.pk]))
        self.assertEqual(response.status_code, 302)
        self.intake.refresh_from_db()
        self.assertFalse(self.intake.taken)

    def test_other_user_cannot_read_update_delete_or_toggle(self):
        self.client.force_login(self.other)
        for method in ['get', 'post']:
            for route, args in [
                ('medication_detail', [self.med.pk]),
                ('medication_update', [self.med.pk]),
                ('medication_delete', [self.med.pk]),
                ('diary_detail', [self.entry.pk]),
                ('diary_update', [self.entry.pk]),
                ('diary_delete', [self.entry.pk]),
            ]:
                self.assertEqual(
                    getattr(self.client, method)(reverse(route, args=args)).status_code, 404
                )
        self.assertEqual(
            self.client.post(reverse('toggle_intake', args=[self.intake.pk])).status_code, 404
        )
        self.assertEqual(
            self.client.post(reverse('record_as_needed', args=[self.med.pk])).status_code, 404
        )
        self.assertTrue(Medication.objects.filter(pk=self.med.pk).exists())
        self.intake.refresh_from_db()
        self.assertFalse(self.intake.taken)

    def test_other_data_absent_from_lists_json_and_quick_choices(self):
        self.client.force_login(self.other)
        for route in ['dashboard', 'medication_list', 'diary_list', 'history', 'quick_intake']:
            response = self.client.get(reverse(route))
            self.assertNotContains(response, 'Чужой препарат')
            self.assertNotContains(response, 'Личная запись')
        response = self.client.post(
            reverse('quick_intake'), {'mode': 'existing', 'medication': self.med.pk}
        )
        self.assertTrue(response.context['quick_form'].errors)
        self.assertEqual(self.med.intakes.count(), 1)

    def test_each_user_can_have_entry_for_same_date_and_owner_cannot_be_forged(self):
        self.client.force_login(self.other)
        data = {
            'date': self.today,
            'mood': 'Хорошее',
            'condition': 'Нормальное',
            'symptoms': 'Моя запись',
            'has_pain': 'no',
            'owner': self.owner.pk,
        }
        self.client.post(reverse('diary_create'), data)
        self.assertEqual(HealthEntry.objects.filter(date=self.today).count(), 2)
        self.assertEqual(HealthEntry.objects.get(symptoms='Моя запись').owner, self.other)
        response = self.client.post(reverse('diary_create'), data)
        self.assertTrue(response.context['form'].errors)

    def test_login_logout_remember_me_session_and_preference_cookie(self):
        response = self.client.post(
            reverse('login'), {'username': 'owner', 'password': self.password, 'remember_me': 'on'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session['_auth_user_id'], str(self.owner.pk))
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), 14 * 24 * 60 * 60)
        self.assertEqual(response.cookies['mediary_remember'].value, '1')
        self.assertTrue(response.cookies['mediary_remember']['httponly'])
        self.assertEqual(response.cookies['mediary_remember']['samesite'], 'Lax')
        self.client.post(reverse('medication_section'), {'section': 'occasional'})
        self.assertEqual(self.client.session.get_expiry_age(), 14 * 24 * 60 * 60)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.client.post(reverse('logout'))
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)
        # Preference survives logout; authentication does not.
        self.assertTrue(self.client.get(reverse('login')).context['form']['remember_me'].value())

    def test_unchecked_remember_me_expires_with_browser_session(self):
        response = self.client.post(
            reverse('login'), {'username': 'owner', 'password': self.password}
        )
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.assertEqual(response.cookies['sessionid']['max-age'], '')
        self.assertEqual(response.cookies['mediary_remember'].value, '0')

    def test_wrong_password_and_external_next(self):
        response = self.client.post(reverse('login'), {'username': 'owner', 'password': 'wrong'})
        self.assertTrue(response.context['form'].errors)
        self.assertNotIn('_auth_user_id', self.client.session)
        response = self.client.post(
            reverse('login'),
            {'username': 'owner', 'password': self.password, 'next': 'https://example.org/'},
        )
        self.assertEqual(response.url, reverse('dashboard'))

    def test_csrf_required_for_authentication_actions(self):
        client = Client(enforce_csrf_checks=True)
        for route in ['login', 'signup', 'logout']:
            self.assertEqual(client.post(reverse(route), {}).status_code, 403)

    def test_login_rotates_session_and_logout_clears_state(self):
        session = self.client.session
        session['medication_section'] = 'courses'
        session.save()
        before = session.session_key
        self.client.post(reverse('login'), {'username': 'owner', 'password': self.password})
        self.assertNotEqual(self.client.session.session_key, before)
        self.client.post(reverse('logout'))
        self.assertNotIn('medication_section', self.client.session)

    def test_password_change_keeps_current_session(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('password_change'),
            {
                'old_password': self.password,
                'new_password1': 'Another-Lab-Password-941!',
                'new_password2': 'Another-Lab-Password-941!',
            },
        )
        self.assertRedirects(response, reverse('profile'))
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password('Another-Lab-Password-941!'))
