"""Пользовательские сценарии с настоящими POST, CSRF и тестовой базой Django."""

from diary.models import MedicationIntake

from .base import BrowserCase


class ComponentTests(BrowserCase):
    def test_medication_mode_count_and_save(self):
        self.run_browser('medication')
        self.medication.refresh_from_db()
        self.assertTrue(self.medication.as_needed)
        self.assertEqual(self.medication.intakes.filter(taken=True).count(), 1)
        self.assertEqual(self.medication.intakes.filter(taken=False).count(), 0)

    def test_health_choices_initial_value_and_save(self):
        self.run_browser('health')
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.mood, 'Отличное')
        self.assertEqual(self.entry.condition, 'Отличное')
        self.assertEqual(self.entry.pain_intensity, 0)

    def test_pill_toggle_updates_database_and_progress_without_navigation(self):
        self.run_browser('toggle')
        self.assertEqual(self.medication.intakes.filter(taken=True).count(), 1)
        last = self.medication.intakes.get(slot=2)
        self.assertFalse(last.taken)
        self.assertIsNone(last.taken_at)

    def test_failed_request_does_not_change_status_and_can_be_retried(self):
        self.run_browser('retry')
        self.assertEqual(self.medication.intakes.filter(taken=True).count(), 2)

    def test_quick_intake_uses_app_timezone_and_preserves_daily_goal(self):
        self.run_browser('quick')
        extra = MedicationIntake.objects.select_related('medication').get(is_extra=True)
        self.assertEqual(extra.reason, 'Synthetic reason')
        self.assertEqual(extra.medication.owner_id, self.user.pk)
        self.assertTrue(extra.medication.as_needed)
        self.assertEqual(self.medication.intakes.filter(is_extra=False).count(), 2)

    def test_native_diary_form_works_without_javascript(self):
        self.run_browser('native')
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.mood, 'Плохое')
        self.assertEqual(self.entry.pain_intensity, 6)


class MobileComponentTests(ComponentTests):
    """Те же сценарии выполняются на узком экране без копирования тестов."""

    viewport = (390, 844)
