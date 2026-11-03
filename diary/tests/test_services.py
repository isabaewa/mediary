"""Проверки инвариантов сервиса без HTTP и клиентской валидации."""

from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from diary.models import Medication, MedicationIntake
from diary.services import record_extra_intake, sync_intakes

from .base import OwnedTestCase


class ExtraIntakeServiceTests(OwnedTestCase):
    def setUp(self):
        super().setUp()
        self.medication = Medication.objects.create(
            owner=self.user,
            name='Тестовый препарат',
            dosage='1',
            as_needed=True,
        )

    def test_foreign_medication_is_not_available_to_service(self):
        other = get_user_model().objects.create_user(username='other_test_owner')
        with self.assertRaises(Medication.DoesNotExist):
            record_extra_intake(owner=other, medication_id=self.medication.pk)
        self.assertFalse(MedicationIntake.objects.exists())

    def test_missing_and_ambiguous_source_are_rejected(self):
        with self.assertRaises(ValueError):
            record_extra_intake(owner=self.user)
        with self.assertRaises(ValueError):
            record_extra_intake(
                owner=self.user,
                medication_id=self.medication.pk,
                new_medication={'name': 'Новый', 'dosage': '1'},
            )
        self.assertFalse(MedicationIntake.objects.exists())

    def test_future_and_naive_timestamps_create_nothing(self):
        for taken_at, error in [
            (timezone.now() + timedelta(days=1), ValidationError),
            (datetime(2026, 10, 1, 9), ValueError),
        ]:
            with self.subTest(taken_at=taken_at), self.assertRaises(error):
                record_extra_intake(
                    owner=self.user,
                    new_medication={'name': 'Новый', 'dosage': '1'},
                    taken_at=taken_at,
                )
        self.assertEqual(Medication.objects.count(), 1)
        self.assertFalse(MedicationIntake.objects.exists())

    def test_new_medication_is_rolled_back_when_intake_cannot_be_saved(self):
        with patch.object(MedicationIntake, 'save', side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):
                record_extra_intake(
                    owner=self.user,
                    new_medication={'name': 'Новый', 'dosage': '1'},
                )
        self.assertEqual(Medication.objects.count(), 1)
        self.assertFalse(MedicationIntake.objects.exists())

    def test_day_is_calculated_in_application_timezone(self):
        # В UTC ещё предыдущий день, но в UTC+5 уже 1 октября.
        taken_at = datetime(2026, 9, 30, 22, 30, tzinfo=datetime_timezone.utc)
        with timezone.override('Asia/Yekaterinburg'):
            intake = record_extra_intake(
                owner=self.user,
                medication_id=self.medication.pk,
                taken_at=taken_at,
                reason='Тестовая причина',
            )
        self.assertEqual(intake.date.isoformat(), '2026-10-01')
        self.assertEqual(intake.reason, 'Тестовая причина')
        self.assertEqual(intake.taken_at, taken_at)

    def test_extra_dose_does_not_occupy_slots_of_an_unbuilt_plan(self):
        today = timezone.localdate()
        self.medication.as_needed = False
        self.medication.start_date = self.medication.end_date = today
        self.medication.daily_doses = 3
        self.medication.save()
        extra = record_extra_intake(owner=self.user, medication_id=self.medication.pk)
        self.assertEqual(extra.slot, 4)
        sync_intakes(self.medication)
        self.assertEqual(
            set(self.medication.intakes.filter(is_extra=False).values_list('slot', flat=True)),
            {1, 2, 3},
        )
        extra.refresh_from_db()
        self.assertTrue(extra.taken)
        self.assertEqual(extra.slot, 4)

    def test_occasional_only_operation_rejects_a_regular_course(self):
        self.medication.as_needed = False
        self.medication.start_date = self.medication.end_date = timezone.localdate()
        self.medication.save()
        with self.assertRaises(Medication.DoesNotExist):
            record_extra_intake(
                owner=self.user,
                medication_id=self.medication.pk,
                as_needed_only=True,
            )
        self.assertFalse(MedicationIntake.objects.exists())

    def test_invalid_reason_rolls_back_new_medication(self):
        with self.assertRaises(ValidationError):
            record_extra_intake(
                owner=self.user,
                new_medication={'name': 'Новый', 'dosage': '1'},
                reason='x' * 301,
            )
        self.assertEqual(Medication.objects.count(), 1)
        self.assertFalse(MedicationIntake.objects.exists())
