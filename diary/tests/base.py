"""Общие фикстуры; классы здесь не содержат тестов и не дублируют проверки."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from diary.models import HealthEntry, Medication


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class OwnedTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='test_owner', password='Own-Test-Pass-839!'
        )
        self.client.force_login(self.user)


class FormDataTestCase(OwnedTestCase):
    """Данные форм и фабрики записей для интеграционных проверок."""

    def setUp(self):
        super().setUp()
        self.med_data = dict(
            name='Тестовый препарат',
            dosage='1 таблетка',
            frequency='Раз в день',
            start_date='2026-10-01',
            end_date='2026-10-03',
            daily_doses=1,
            purpose='Головная боль',
        )
        self.med_data['dose_time_1'] = '09:00'
        self.entry_data = dict(
            date='2026-10-01',
            mood='Хорошее',
            condition='Нормальное',
            symptoms='Нет симптомов',
            pain_intensity=0,
            note='Заметка',
            has_pain='no',
        )

    def med(self):
        return Medication.objects.create(
            owner=self.user,
            **{k: v for k, v in self.med_data.items() if k != 'dose_time_1'},
            scheduled_times=['09:00'],
        )

    def entry(self):
        return HealthEntry.objects.create(
            owner=self.user, **{k: v for k, v in self.entry_data.items() if k != 'has_pain'}
        )
