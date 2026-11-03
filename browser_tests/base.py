"""Тестовый сервер и Node-процесс работают только с искусственными записями."""

import os
import shutil
import subprocess
from datetime import time, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings, tag
from django.utils import timezone

from diary.models import HealthEntry, Medication, MedicationIntake

ROOT = Path(__file__).resolve().parent.parent


@tag('browser')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class BrowserCase(StaticLiveServerTestCase):
    """Каждый сценарий получает чистую БД, сессию и процесс браузера."""

    viewport = (1280, 900)

    @classmethod
    def setUpClass(cls):
        cls.node = os.environ.get('MEDIARY_NODE') or shutil.which('node')
        if not cls.node:
            raise RuntimeError('Для браузерных тестов установите Node.js и выполните npm ci.')
        probe = subprocess.run(
            [cls.node, '-e', "require.resolve('playwright')"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if probe.returncode:
            raise RuntimeError('Playwright не установлен. Выполните npm ci в папке проекта.')
        super().setUpClass()

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='browser_test_user')
        self.client.force_login(self.user)
        self.session_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        today = timezone.localdate()
        self.medication = Medication.objects.create(
            owner=self.user,
            name='Browser test medication',
            dosage='Test dosage',
            daily_doses=2,
            start_date=today,
            end_date=today,
            scheduled_times=['08:00', '20:00'],
        )
        for slot in (1, 2):
            MedicationIntake.objects.create(
                medication=self.medication,
                date=today,
                slot=slot,
                scheduled_time=time(8 if slot == 1 else 20),
                taken=slot == 1,
                taken_at=timezone.now() if slot == 1 else None,
            )
        self.entry = HealthEntry.objects.create(
            owner=self.user,
            date=today,
            mood='Хорошее',
            condition='Нормальное',
            pain_intensity=3,
        )

    def run_browser(self, scenario):
        """Передать тестовую сессию процессу, не сохраняя cookie в файлы или логи."""
        env = os.environ.copy()
        now = timezone.localtime()
        env.update(
            {
                'MEDIARY_TEST_URL': self.live_server_url,
                'MEDIARY_TEST_SESSION': self.session_cookie,
                'MEDIARY_TEST_COOKIE_NAME': settings.SESSION_COOKIE_NAME,
                'MEDIARY_TEST_MEDICATION': str(self.medication.pk),
                'MEDIARY_TEST_ENTRY': str(self.entry.pk),
                'MEDIARY_TEST_WIDTH': str(self.viewport[0]),
                'MEDIARY_TEST_HEIGHT': str(self.viewport[1]),
                'MEDIARY_TEST_DATE_FROM': (now.date() - timedelta(days=25)).isoformat(),
                'MEDIARY_TEST_DATE_TO': (now.date() - timedelta(days=1)).isoformat(),
                'MEDIARY_TEST_TIME_MIN': (now - timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M'),
                'MEDIARY_TEST_TIME_MAX': (now + timedelta(minutes=2)).strftime('%Y-%m-%dT%H:%M'),
            }
        )
        result = subprocess.run(
            [self.node, str(ROOT / 'browser_tests' / 'components.cjs'), scenario],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
