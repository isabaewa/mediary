from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils.html import escape

from diary.models import HealthEntry

from .base import FormDataTestCase


class DiarySecurityTests(FormDataTestCase):
    def test_xss_is_escaped_in_detail_and_fetch_search(self):
        payload = '<img src=x onerror=alert(1)>'
        response = self.client.post(reverse('diary_create'), {**self.entry_data, 'note': payload})
        self.assertEqual(response.status_code, 302)
        entry = HealthEntry.objects.get(owner=self.user)

        detail = self.client.get(reverse('diary_detail', args=[entry.pk]))
        self.assertContains(detail, escape(payload))
        self.assertNotContains(detail, payload)

        fragment = self.client.get(
            reverse('diary_list'), {'q': payload}, headers={'X-Diary-Fragment': '1'}
        )
        self.assertContains(fragment, f'<mark>{escape(payload)}</mark>', html=True)
        self.assertNotContains(fragment, payload)

    def test_sql_like_search_is_literal(self):
        self.entry()
        payload = "' OR 1=1 --"
        fragment = self.client.get(
            reverse('diary_list'), {'q': payload}, headers={'X-Diary-Fragment': '1'}
        )
        self.assertEqual(fragment.status_code, 200)
        self.assertEqual(list(fragment.context['entries']), [])

    def test_diary_responses_with_entries_cannot_be_cached(self):
        entry = self.entry()
        for route, args, headers in [
            ('diary_list', [], {}),
            ('diary_list', [], {'X-Diary-Fragment': '1'}),
            ('diary_detail', [entry.pk], {}),
        ]:
            with self.subTest(route=route, headers=headers):
                response = self.client.get(reverse(route, args=args), headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertIn('private', response.headers['Cache-Control'])
                self.assertIn('no-store', response.headers['Cache-Control'])

    def test_delete_requires_post_and_csrf(self):
        entry = self.entry()
        url = reverse('diary_delete', args=[entry.pk])
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        confirmation = client.get(url)
        self.assertContains(confirmation, 'csrfmiddlewaretoken')
        token = client.cookies['csrftoken'].value
        headers = {'X-CSRFToken': token}
        self.assertEqual(client.delete(url, headers=headers).status_code, 405)
        self.assertEqual(client.post(url).status_code, 403)
        self.assertTrue(HealthEntry.objects.filter(pk=entry.pk).exists())

        self.assertEqual(client.post(url, headers=headers).status_code, 302)
        self.assertFalse(HealthEntry.objects.filter(pk=entry.pk).exists())

    def test_other_user_cannot_delete_entry_by_id(self):
        entry = self.entry()
        other = get_user_model().objects.create_user(username='other_diary_user')
        self.client.force_login(other)

        url = reverse('diary_delete', args=[entry.pk])
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(HealthEntry.objects.filter(pk=entry.pk).exists())
