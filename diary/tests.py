from datetime import date, time
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import Medication, MedicationIntake, HealthEntry


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class OwnedTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='test_owner',password='Own-Test-Pass-839!')
        self.client.force_login(self.user)


class CRUDTests(OwnedTestCase):
    def setUp(self):
        super().setUp()
        self.med_data = dict(name='Тестовый препарат', dosage='1 таблетка', frequency='Раз в день',
                             start_date='2026-10-01', end_date='2026-10-03', daily_doses=1, purpose='Головная боль')
        self.med_data['dose_time_1'] = '09:00'
        self.entry_data = dict(date='2026-10-01', mood='Хорошее', condition='Нормальное',
                               symptoms='Нет симптомов', pain_intensity=0, note='Заметка', has_pain='no')

    def med(self):
        return Medication.objects.create(owner=self.user, **{k: v for k, v in self.med_data.items() if k != 'dose_time_1'}, scheduled_times=['09:00'])

    def entry(self):
        return HealthEntry.objects.create(owner=self.user, **{k: v for k, v in self.entry_data.items() if k != 'has_pain'})

    def test_medication_full_crud(self):
        self.assertRedirects(self.client.post(reverse('medication_create'), self.med_data), reverse('medication_list'))
        med = Medication.objects.get()
        self.assertEqual(med.intakes.count(), 3)
        self.assertEqual(med.intakes.first().scheduled_time, time(9))
        for route in ['medication_list', 'medication_detail', 'medication_update', 'medication_delete']:
            args = [] if route.endswith('list') else [med.pk]
            self.assertContains(self.client.get(reverse(route, args=args)), med.name)
        self.assertTrue(Medication.objects.filter(pk=med.pk).exists())
        self.client.post(reverse('medication_update', args=[med.pk]), {**self.med_data, 'name': 'Новое имя'})
        med.refresh_from_db()
        self.assertEqual(med.name, 'Новое имя')
        self.assertEqual(med.intakes.count(), 3)
        self.client.post(reverse('medication_delete', args=[med.pk]))
        self.assertFalse(Medication.objects.exists())
        self.assertFalse(MedicationIntake.objects.exists())

    def test_schedule_update_preserves_taken(self):
        self.client.post(reverse('medication_create'), self.med_data)
        med = Medication.objects.get()
        taken = med.intakes.get(date='2026-10-01')
        taken.taken = True
        taken.save()
        kept = med.intakes.get(date='2026-10-02')
        data = {**self.med_data, 'start_date': '2026-10-02', 'end_date': '2026-10-04'}
        self.client.post(reverse('medication_update', args=[med.pk]), data)
        taken.refresh_from_db()
        self.assertTrue(taken.taken)
        self.assertTrue(med.intakes.filter(pk=kept.pk).exists())
        self.assertEqual(med.intakes.count(), 4)
        self.client.post(reverse('medication_update', args=[med.pk]), {**data, 'end_date': '2026-10-02'})
        self.assertEqual(med.intakes.count(), 2)

    def test_invalid_course_not_saved(self):
        response = self.client.post(reverse('medication_create'), {**self.med_data, 'end_date': '2026-09-01'})
        self.assertContains(response, 'Дата окончания курса не может быть раньше')
        self.assertFalse(Medication.objects.exists())

    def test_course_and_schedule_atomic(self):
        with patch('diary.views.sync_intakes', side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('medication_create'), self.med_data)
        self.assertFalse(Medication.objects.exists())

    def test_diary_full_crud(self):
        self.assertRedirects(self.client.post(reverse('diary_create'), self.entry_data), reverse('dashboard'))
        entry = HealthEntry.objects.get()
        for route in ['diary_list', 'diary_detail', 'diary_update', 'diary_delete']:
            args = [] if route.endswith('list') else [entry.pk]
            self.assertEqual(self.client.get(reverse(route, args=args)).status_code, 200)
        self.assertTrue(HealthEntry.objects.filter(pk=entry.pk).exists())
        self.client.post(reverse('diary_update', args=[entry.pk]), {**self.entry_data, 'pain_intensity': 10, 'has_pain': 'yes', 'note': 'Изменено'})
        entry.refresh_from_db()
        self.assertEqual(entry.pain_intensity, 10)
        self.assertEqual(entry.note, 'Изменено')
        self.client.post(reverse('diary_delete', args=[entry.pk]))
        self.assertFalse(HealthEntry.objects.exists())

    def test_diary_invalid_values_and_duplicate(self):
        for field, value in [('pain_intensity', -1), ('pain_intensity', 11), ('mood', 'invalid'), ('condition', 'invalid'), ('date', '')]:
            response = self.client.post(reverse('diary_create'), {**self.entry_data, field: value})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
            self.assertContains(response, 'role="alert"')
            self.assertFalse(HealthEntry.objects.exists())
        self.entry()
        response = self.client.post(reverse('diary_create'), self.entry_data)
        self.assertIn('date', response.context['form'].errors)
        self.assertEqual(HealthEntry.objects.count(), 1)

    def test_form_controls_and_date(self):
        response = self.client.get(reverse('diary_create'))
        self.assertContains(response, 'value="Хорошее"')
        self.assertContains(response, 'value="Нормальное"')
        self.assertContains(response, 'name="date"', count=1)
        entry = self.entry()
        response = self.client.get(reverse('diary_update', args=[entry.pk]))
        self.assertContains(response, 'value="2026-10-01"')
        med = self.med()
        response = self.client.get(reverse('medication_update', args=[med.pk]))
        self.assertContains(response, 'value="2026-10-01"')

    def test_toggle_post_and_csrf(self):
        intake = MedicationIntake.objects.create(medication=self.med(), date=date.today(), scheduled_time=time(9))
        url = reverse('toggle_intake', args=[intake.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        intake.refresh_from_db()
        self.assertFalse(intake.taken)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(url).status_code, 403)
        response = csrf_client.get(reverse('dashboard'))
        self.assertContains(response, 'csrfmiddlewaretoken')
        token = csrf_client.cookies['csrftoken'].value
        self.assertEqual(csrf_client.post(url, HTTP_X_CSRFTOKEN=token).status_code, 302)
        intake.refresh_from_db()
        self.assertTrue(intake.taken)
        self.client.post(url)
        intake.refresh_from_db()
        self.assertFalse(intake.taken)

    def test_missing_objects(self):
        for route in ['medication_detail', 'medication_update', 'medication_delete', 'diary_detail', 'diary_update', 'diary_delete']:
            self.assertEqual(self.client.get(reverse(route, args=[999])).status_code, 404)
        self.assertEqual(self.client.post(reverse('toggle_intake', args=[999])).status_code, 404)

    def test_dashboard_history(self):
        self.entry()
        MedicationIntake.objects.create(medication=self.med(), date=date.today(), scheduled_time=time(9))
        for route in ['dashboard', 'history']:
            self.assertContains(self.client.get(reverse(route)), 'Тестовый препарат')


    def test_purpose_and_selected_time(self):
        self.client.post(reverse('medication_create'), {**self.med_data, 'dose_time_1': '18:30'})
        med = Medication.objects.get()
        self.assertEqual(med.purpose, 'Головная боль')
        self.assertTrue(all(i.scheduled_time == time(18, 30) for i in med.intakes.all()))
        for route in ['medication_list', 'medication_detail', 'medication_update']:
            args = [] if route.endswith('list') else [med.pk]
            self.assertContains(self.client.get(reverse(route, args=args)), 'Головная боль')

    def test_change_time_keeps_completed_intake(self):
        self.client.post(reverse('medication_create'), self.med_data)
        med = Medication.objects.get()
        taken = med.intakes.first()
        taken.taken = True
        taken.save()
        self.client.post(reverse('medication_update', args=[med.pk]), {**self.med_data, 'dose_time_1': '18:30'})
        taken.refresh_from_db()
        self.assertTrue(taken.taken)
        self.assertEqual(taken.scheduled_time, time(9))
        self.assertEqual(med.intakes.count(), 3)
        self.assertTrue(all(i.scheduled_time == time(18, 30) for i in med.intakes.filter(taken=False)))

    def test_model_validation_and_database_constraints(self):
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError, transaction
        med = self.med()
        med.end_date = date(2026, 9, 1)
        with self.assertRaises(ValidationError):
            med.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            med.save()
        entry = self.entry()
        entry.pain_intensity = 11
        with self.assertRaises(ValidationError):
            entry.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            entry.save()
        data = dict(medication=med, date=date(2026, 10, 1), scheduled_time=time(9))
        MedicationIntake.objects.create(**data)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MedicationIntake.objects.create(**data)

    def test_course_status_uses_dates(self):
        med = self.med()
        med.start_date, med.end_date = date(2026, 10, 1), date(2026, 10, 3)
        for today, status in [(date(2026, 9, 30), 'Курс ещё не начался'),
                              (date(2026, 10, 2), 'Активный курс'),
                              (date(2026, 10, 4), 'Курс завершён')]:
            with patch('diary.models.timezone.localdate', return_value=today):
                self.assertEqual(med.course_status, status)


    def test_restore_missing_slots_is_idempotent(self):
        from .services import sync_intakes
        med = self.med()
        taken = MedicationIntake.objects.create(medication=med, date=date(2026, 10, 1), scheduled_time=time(8), taken=True)
        med.refresh_from_db()
        sync_intakes(med)
        sync_intakes(med)
        taken.refresh_from_db()
        self.assertTrue(taken.taken)
        self.assertEqual(taken.scheduled_time, time(8))
        self.assertEqual(med.intakes.count(), 3)

    def test_three_doses_without_time(self):
        data = {**self.med_data, 'daily_doses': 3, 'dose_time_1': ''}
        self.assertEqual(self.client.post(reverse('medication_create'), data).status_code, 302)
        med = Medication.objects.get()
        self.assertEqual(med.intakes.count(), 9)
        self.assertFalse(med.intakes.filter(scheduled_time__isnull=False).exists())
        self.assertEqual(list(med.intakes.filter(date='2026-10-01').values_list('slot', flat=True)), [1, 2, 3])

    def test_optional_times_and_duplicate_validation(self):
        data = {**self.med_data, 'daily_doses': 3, 'dose_time_1': '', 'dose_time_2': '14:00', 'dose_time_3': ''}
        self.client.post(reverse('medication_create'), data)
        med = Medication.objects.get()
        self.assertEqual(med.scheduled_times, [None, '14:00', None])
        response = self.client.post(reverse('medication_update', args=[med.pk]), {**data, 'dose_time_3': '14:00'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        med.refresh_from_db()
        self.assertEqual(med.scheduled_times, [None, '14:00', None])

    def test_change_count_keeps_completed_extra_slot(self):
        self.client.post(reverse('medication_create'), {**self.med_data, 'daily_doses': 3})
        med = Medication.objects.get()
        done = med.intakes.get(date='2026-10-01', slot=3)
        done.taken = True
        done.save()
        self.client.post(reverse('medication_update', args=[med.pk]), self.med_data)
        self.assertEqual(med.intakes.count(), 4)
        done.refresh_from_db()
        self.assertTrue(done.taken)

    def test_actual_time_records_and_clears(self):
        from django.utils import timezone
        intake = MedicationIntake.objects.create(medication=self.med(), date=timezone.localdate())
        now = timezone.now()
        with patch('diary.views.timezone.now', return_value=now):
            self.client.post(reverse('toggle_intake', args=[intake.pk]))
        intake.refresh_from_db()
        self.assertEqual(intake.taken_at, now)
        self.assertContains(self.client.get(reverse('history')), 'Принято:')
        self.client.post(reverse('toggle_intake', args=[intake.pk]))
        intake.refresh_from_db()
        self.assertIsNone(intake.taken_at)
        self.assertFalse(intake.taken)

    def test_count_and_time_validation(self):
        for changes in [{'daily_doses': 0}, {'daily_doses': 13}, {'dose_time_1': '25:00'}]:
            response = self.client.post(reverse('medication_create'), {**self.med_data, **changes})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
        self.assertFalse(Medication.objects.exists())


    def test_json_intake_update_is_idempotent(self):
        from django.utils import timezone
        intake = MedicationIntake.objects.create(medication=self.med(), date=timezone.localdate())
        url = reverse('toggle_intake', args=[intake.pk])
        response = self.client.post(url, {'taken': 'true'}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['taken'])
        intake.refresh_from_db()
        original_time = intake.taken_at
        self.client.post(url, {'taken': 'true'}, HTTP_ACCEPT='application/json')
        intake.refresh_from_db()
        self.assertEqual(intake.taken_at, original_time)
        response = self.client.post(url, {'taken': 'false'}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.json(), {'taken': False, 'taken_at': None})
        intake.refresh_from_db()
        self.assertFalse(intake.taken)
        self.assertIsNone(intake.taken_at)

    def test_json_rejects_invalid_state_without_change(self):
        from django.utils import timezone
        intake = MedicationIntake.objects.create(medication=self.med(), date=timezone.localdate())
        response = self.client.post(reverse('toggle_intake', args=[intake.pk]), {'taken': 'bad'}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 400)
        intake.refresh_from_db()
        self.assertFalse(intake.taken)


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
            response = self.client.post(reverse('diary_create'), {**self.entry_data, 'has_pain': 'yes', 'pain_intensity': value})
            self.assertEqual(response.status_code, 200)
            self.assertIn('pain_intensity', response.context['form'].errors)
        response = self.client.post(reverse('diary_create'), {**self.entry_data, 'has_pain': 'yes', 'pain_intensity': 4})
        self.assertEqual(response.status_code, 302)
        entry = HealthEntry.objects.get()
        self.assertEqual(entry.pain_intensity, 4)
        response = self.client.get(reverse('diary_update', args=[entry.pk]))
        self.assertEqual(response.context['form']['has_pain'].value(), 'yes')


class OptionalIntakeTests(OwnedTestCase):
    def test_as_needed_creates_only_actual_intakes(self):
        today = __import__('django.utils.timezone', fromlist=['localdate']).localdate()
        data = dict(name='По необходимости', dosage='1 таблетка', start_date=today, end_date=today, daily_doses=1, as_needed='on')
        self.client.post(reverse('medication_create'), data)
        medication = Medication.objects.get()
        self.assertTrue(medication.as_needed)
        self.assertEqual(medication.scheduled_times, [])
        self.assertFalse(medication.intakes.exists())
        url = reverse('record_as_needed', args=[medication.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(medication.intakes.count(), 2)
        for intake in medication.intakes.all():
            self.assertTrue(intake.taken)
            self.assertIsNotNone(intake.taken_at)
            self.assertIsNone(intake.scheduled_time)
            self.assertFalse(intake.is_overdue)
        self.assertContains(self.client.get(reverse('dashboard')), 'По необходимости')

    def test_overdue_status_in_history_and_detail(self):
        from django.utils import timezone
        from datetime import timedelta
        today = timezone.localdate()
        medication = Medication.objects.create(owner=self.user, name='Курс', dosage='1', start_date=today-timedelta(days=1), end_date=today)
        intake = MedicationIntake.objects.create(medication=medication, date=today-timedelta(days=1))
        self.assertTrue(intake.is_overdue)
        self.assertContains(self.client.get(reverse('history')), 'Пропущено')
        self.assertContains(self.client.get(reverse('medication_detail', args=[medication.pk])), 'Пропущено')
        intake.taken = True
        intake.save()
        self.assertFalse(intake.is_overdue)


class HistoryDateTests(OwnedTestCase):
    def test_archive_includes_past_and_today_but_not_future(self):
        from django.utils import timezone
        from datetime import timedelta
        today = timezone.localdate()
        med = Medication.objects.create(owner=self.user, name='Архив', dosage='1', start_date=today-timedelta(days=1), end_date=today+timedelta(days=1))
        rows = [MedicationIntake.objects.create(medication=med, date=today+timedelta(days=offset)) for offset in [-1, 0, 1]]
        response = self.client.get(reverse('history'))
        self.assertEqual(set(response.context['all_intakes'].values_list('pk', flat=True)), {rows[0].pk, rows[1].pk})
        self.assertTrue(MedicationIntake.objects.filter(pk=rows[2].pk).exists())


class ClearedTimeTests(OwnedTestCase):
    def test_undo_uses_current_schedule_instead_of_historical_time(self):
        from django.utils import timezone
        today = timezone.localdate()
        med = Medication.objects.create(owner=self.user, name='Без времени', dosage='1', start_date=today, end_date=today, scheduled_times=[None])
        intake = MedicationIntake.objects.create(medication=med, date=today, taken=True, taken_at=timezone.now(), scheduled_time=time(9))
        self.client.post(reverse('toggle_intake', args=[intake.pk]), {'taken': 'false'})
        intake.refresh_from_db()
        self.assertIsNone(intake.scheduled_time)
        self.assertIsNone(intake.taken_at)
        self.assertFalse(intake.is_overdue)


class QuickIntakeTests(OwnedTestCase):
    def test_existing_medication_extra_dose_does_not_change_goal(self):
        from django.utils import timezone
        today = timezone.localdate()
        med = Medication.objects.create(owner=self.user, name='Курс', dosage='1 таблетка', start_date=today, end_date=today, scheduled_times=['07:00'])
        planned = MedicationIntake.objects.create(medication=med, date=today, scheduled_time=time(7))
        response = self.client.post(reverse('quick_intake'), {'mode': 'existing', 'medication': med.pk})
        self.assertRedirects(response, reverse('dashboard'))
        extra = med.intakes.get(is_extra=True)
        self.assertTrue(extra.taken)
        self.assertIsNotNone(extra.taken_at)
        self.assertIsNone(extra.scheduled_time)
        self.assertFalse(extra.is_overdue)
        planned.refresh_from_db()
        self.assertFalse(planned.taken)
        self.assertEqual(self.client.get(reverse('dashboard')).context['total_intakes'], 1)
        med.refresh_from_db()
        self.assertFalse(med.as_needed)
        self.assertEqual(med.scheduled_times, ['07:00'])

    def test_new_medication_records_once_without_schedule(self):
        self.client.post(reverse('quick_intake'), {'mode': 'new', 'name': 'Разовый', 'dosage': '1 пакетик'})
        med = Medication.objects.get()
        self.assertTrue(med.as_needed)
        self.assertEqual(med.intakes.count(), 1)
        self.assertTrue(med.intakes.get().is_extra)
        self.assertEqual(self.client.get(reverse('dashboard')).context['total_intakes'], 0)
        self.assertContains(self.client.get(reverse('history')), 'Разовый')

    def test_invalid_quick_intake_creates_nothing(self):
        for data in [{'mode': 'new', 'name': 'Нет дозировки'}, {'mode': 'existing'}, {'mode': 'existing', 'medication': '999999'}]:
            response = self.client.post(reverse('quick_intake'), data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['quick_form'].errors)
        self.assertFalse(Medication.objects.exists())
        self.assertFalse(MedicationIntake.objects.exists())


class BusinessLogicTests(OwnedTestCase):
    def make_med(self, today):
        return Medication.objects.create(owner=self.user, name='Лекарство', dosage='1', start_date=today, end_date=today)

    def test_past_intake_uses_selected_day_and_local_time(self):
        from django.utils import timezone
        from datetime import timedelta
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        value = yesterday.strftime('%Y-%m-%d') + 'T21:30'
        response = self.client.post(reverse('quick_intake'), {'mode': 'new', 'name': 'Вчерашний', 'dosage': '1', 'taken_at': value})
        self.assertRedirects(response, reverse('dashboard'))
        intake = MedicationIntake.objects.get()
        self.assertEqual(intake.date, yesterday)
        self.assertEqual(timezone.localtime(intake.taken_at).strftime('%Y-%m-%dT%H:%M'), value)
        self.assertIsNone(intake.medication.start_date)
        self.assertNotContains(self.client.get(reverse('dashboard')), '<strong>Вчерашний</strong>')
        self.assertContains(self.client.get(reverse('history')), 'Вчерашний')

    def test_future_time_and_invalid_timestamp_save_nothing(self):
        from django.utils import timezone
        from datetime import timedelta
        for value in [(timezone.localtime()+timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M'), (timezone.localtime()+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'), 'не дата']:
            response = self.client.post(reverse('quick_intake'), {'mode':'new', 'name':'Будущий', 'dosage':'1', 'taken_at':value})
            self.assertTrue(response.context['quick_form'].errors)
        self.assertFalse(Medication.objects.exists())
        self.assertFalse(MedicationIntake.objects.exists())

    def test_past_extra_dose_does_not_change_current_plan(self):
        from django.utils import timezone
        from datetime import timedelta
        today = timezone.localdate()
        med = self.make_med(today)
        MedicationIntake.objects.create(medication=med, date=today)
        self.client.post(reverse('quick_intake'), {'mode':'existing', 'medication':med.pk, 'taken_at':(today-timedelta(days=1)).strftime('%Y-%m-%d')+'T23:59'})
        dashboard = self.client.get(reverse('dashboard'))
        self.assertEqual(dashboard.context['total_intakes'], 1)
        self.assertEqual(dashboard.context['taken_intakes'], 0)
        self.assertFalse(dashboard.context['as_needed_intakes'].exists())

    def test_expanding_daily_plan_preserves_extra_and_creates_all_slots(self):
        from django.utils import timezone
        from diary.services import sync_intakes
        today = timezone.localdate()
        med = self.make_med(today)
        sync_intakes(med)
        extra = MedicationIntake.objects.create(medication=med, date=today, slot=2, is_extra=True, taken=True, taken_at=timezone.now())
        timestamp = extra.taken_at
        med.daily_doses=3;med.scheduled_times=[None,None,None];med.save()
        sync_intakes(med);sync_intakes(med)
        self.assertEqual(set(med.intakes.filter(is_extra=False).values_list('slot',flat=True)), {1,2,3})
        extra.refresh_from_db()
        self.assertEqual(extra.taken_at,timestamp)
        self.assertTrue(extra.is_extra)
        self.assertGreater(extra.slot,3)
        self.assertEqual(self.client.get(reverse('dashboard')).context['total_intakes'],3)

    def test_converting_as_needed_to_daily_preserves_recorded_dose(self):
        from django.utils import timezone
        from diary.services import sync_intakes
        today=timezone.localdate();med=self.make_med(today)
        med.as_needed=True;med.save()
        extra=MedicationIntake.objects.create(medication=med,date=today,is_extra=True,taken=True,taken_at=timezone.now())
        med.as_needed=False;med.save();sync_intakes(med)
        self.assertEqual(med.intakes.filter(is_extra=False).count(),1)
        extra.refresh_from_db();self.assertTrue(extra.taken)

    def test_future_diary_entry_is_rejected(self):
        from django.utils import timezone
        from datetime import timedelta
        response=self.client.post(reverse('diary_create'), dict(date=timezone.localdate()+timedelta(days=1),mood='Хорошее',condition='Нормальное',symptoms='Нет',has_pain='no'))
        self.assertTrue(response.context['form'].errors)
        self.assertFalse(HealthEntry.objects.exists())

    def test_dated_statuses_with_and_without_clock(self):
        from django.utils import timezone
        from datetime import timedelta
        today=timezone.localdate();med=self.make_med(today)
        intake=MedicationIntake(medication=med,date=today,scheduled_time=None)
        self.assertFalse(intake.is_overdue)
        intake.date=today-timedelta(days=1);self.assertTrue(intake.is_overdue)
        intake.is_extra=True;self.assertFalse(intake.is_overdue)
        intake.is_extra=False;intake.date=today+timedelta(days=1);self.assertFalse(intake.is_overdue)


class FinishedCourseTests(OwnedTestCase):
    def test_completed_course_disappears_from_goal_without_losing_history(self):
        from django.utils import timezone
        from datetime import timedelta
        today=timezone.localdate()
        med=Medication.objects.create(owner=self.user, name='Завершённый',dosage='1',start_date=today-timedelta(days=2),end_date=today-timedelta(days=1))
        intake=MedicationIntake.objects.create(medication=med,date=today,taken=True,taken_at=timezone.now())
        response=self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['total_intakes'],0)
        self.assertFalse(response.context['today_intakes'])
        self.assertContains(self.client.get(reverse('history')),'Завершённый')
        self.assertTrue(MedicationIntake.objects.filter(pk=intake.pk).exists())

    def test_future_course_not_in_today_goal(self):
        from django.utils import timezone
        from datetime import timedelta
        today=timezone.localdate()
        med=Medication.objects.create(owner=self.user, name='Будущий курс',dosage='1',start_date=today+timedelta(days=1),end_date=today+timedelta(days=2))
        MedicationIntake.objects.create(medication=med,date=today)
        self.assertEqual(self.client.get(reverse('dashboard')).context['total_intakes'],0)


class IntakeModeAndReasonTests(OwnedTestCase):
    def test_occasional_medication_needs_no_dates_or_daily_count(self):
        response=self.client.post(reverse('medication_create'), {'intake_mode':'occasional','name':'Иногда','dosage':'1','purpose':'При симптомах'})
        self.assertRedirects(response,reverse('medication_list'))
        med=Medication.objects.get()
        self.assertTrue(med.as_needed)
        self.assertIsNone(med.start_date);self.assertIsNone(med.end_date)
        self.assertEqual(med.scheduled_times,[]);self.assertFalse(med.intakes.exists())
        self.assertEqual(med.course_status,'Иногда')
        detail=self.client.get(reverse('medication_detail',args=[med.pk]))
        self.assertNotContains(detail,'Сроки курса лечения')

    def test_regular_mode_requires_course_and_count(self):
        response=self.client.post(reverse('medication_create'), {'intake_mode':'regular','name':'Курс','dosage':'1'})
        self.assertTrue(response.context['form'].errors)
        self.assertFalse(Medication.objects.exists())

    def test_reason_is_optional_and_belongs_to_single_intake(self):
        self.client.post(reverse('quick_intake'), {'mode':'new','name':'Лекарство','dosage':'1','reason':'Поднялась температура'})
        med=Medication.objects.get()
        self.client.post(reverse('quick_intake'), {'mode':'existing','medication':med.pk})
        self.assertEqual(list(med.intakes.order_by('id').values_list('reason',flat=True)), ['Поднялась температура',''])
        self.assertContains(self.client.get(reverse('history')), 'Поднялась температура')
        self.assertContains(self.client.get(reverse('medication_detail',args=[med.pk])), 'Поднялась температура')
        self.assertIsNone(med.start_date);self.assertIsNone(med.end_date)

    def test_reason_length_rejected_without_records(self):
        response=self.client.post(reverse('quick_intake'), {'mode':'new','name':'Лекарство','dosage':'1','reason':'a'*301})
        self.assertIn('reason',response.context['quick_form'].errors)
        self.assertFalse(MedicationIntake.objects.exists())

    def test_switching_to_occasional_preserves_completed_history(self):
        from django.utils import timezone
        from diary.services import sync_intakes
        today=timezone.localdate()
        med=Medication.objects.create(owner=self.user, name='Курс',dosage='1',start_date=today,end_date=today)
        sync_intakes(med)
        intake=med.intakes.get();intake.taken=True;intake.taken_at=timezone.now();intake.save()
        self.client.post(reverse('medication_update',args=[med.pk]),{'intake_mode':'occasional','name':'Курс','dosage':'1'})
        med.refresh_from_db();self.assertTrue(med.as_needed);self.assertIsNone(med.start_date)
        intake.refresh_from_db();self.assertTrue(intake.taken)
        self.assertEqual(self.client.get(reverse('dashboard')).context['total_intakes'],0)


class IntakePaginationTests(OwnedTestCase):
    def test_history_pages_are_limited_and_recent_before_future(self):
        from django.utils import timezone
        from datetime import timedelta
        today=timezone.localdate()
        med=Medication.objects.create(owner=self.user, name='Длинный курс',dosage='1',start_date=today-timedelta(days=30),end_date=today+timedelta(days=2))
        for offset in range(-25,3):
            MedicationIntake.objects.create(medication=med,date=today+timedelta(days=offset))
        url=reverse('medication_detail',args=[med.pk])
        first=self.client.get(url);second=self.client.get(url,{'page':2})
        self.assertEqual(len(first.context['intakes']),20)
        self.assertEqual(first.context['intakes'][0].date,today)
        self.assertEqual(len(second.context['intakes']),8)
        self.assertFalse(set(i.pk for i in first.context['intakes']) & set(i.pk for i in second.context['intakes']))
        self.assertEqual(MedicationIntake.objects.count(),28)
        self.assertEqual(self.client.get(url,{'page':'invalid'}).status_code,200)



@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AuthenticationTests(TestCase):
    def setUp(self):
        self.password='Strong-Lab-Password-823!'
        self.owner=get_user_model().objects.create_user(username='owner',password=self.password)
        self.other=get_user_model().objects.create_user(username='other',password=self.password)
        from django.utils import timezone
        self.today=timezone.localdate()
        self.med=Medication.objects.create(owner=self.owner,name='Чужой препарат',dosage='1',start_date=self.today,end_date=self.today)
        self.intake=MedicationIntake.objects.create(medication=self.med,date=self.today)
        self.entry=HealthEntry.objects.create(owner=self.owner,date=self.today,mood='Хорошее',condition='Нормальное',symptoms='Личная запись',pain_intensity=0)

    def test_registration_hashes_password_and_creates_empty_account(self):
        response=self.client.post(reverse('signup'),{'username':'newuser','password1':self.password,'password2':self.password})
        self.assertRedirects(response,reverse('login'))
        user=get_user_model().objects.get(username='newuser')
        self.assertNotEqual(user.password,self.password);self.assertTrue(user.check_password(self.password))
        self.assertFalse(user.medications.exists());self.assertFalse(user.health_entries.exists())

    def test_duplicate_username_weak_and_mismatched_passwords_rejected(self):
        for data in [{'username':'owner','password1':self.password,'password2':self.password},{'username':'weak','password1':'123','password2':'123'},{'username':'mismatch','password1':self.password,'password2':'different'}]:
            response=self.client.post(reverse('signup'),data)
            self.assertTrue(response.context['form'].errors)
        self.assertEqual(get_user_model().objects.count(),2)

    def test_anonymous_cannot_access_private_pages_or_post(self):
        for route,args in [('dashboard',[]),('medication_list',[]),('medication_detail',[self.med.pk]),('medication_update',[self.med.pk]),('medication_delete',[self.med.pk]),('diary_list',[]),('diary_detail',[self.entry.pk]),('history',[]),('quick_intake',[])]:
            response=self.client.get(reverse(route,args=args))
            self.assertEqual(response.status_code,302)
            self.assertTrue(response.url.startswith(reverse('login')))
        response=self.client.post(reverse('toggle_intake',args=[self.intake.pk]))
        self.assertEqual(response.status_code,302)
        self.intake.refresh_from_db();self.assertFalse(self.intake.taken)

    def test_other_user_cannot_read_update_delete_or_toggle(self):
        self.client.force_login(self.other)
        for method in ['get','post']:
            for route,args in [('medication_detail',[self.med.pk]),('medication_update',[self.med.pk]),('medication_delete',[self.med.pk]),('diary_detail',[self.entry.pk]),('diary_update',[self.entry.pk]),('diary_delete',[self.entry.pk])]:
                self.assertEqual(getattr(self.client,method)(reverse(route,args=args)).status_code,404)
        self.assertEqual(self.client.post(reverse('toggle_intake',args=[self.intake.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('record_as_needed',args=[self.med.pk])).status_code,404)
        self.assertTrue(Medication.objects.filter(pk=self.med.pk).exists())
        self.intake.refresh_from_db();self.assertFalse(self.intake.taken)

    def test_other_data_absent_from_lists_json_and_quick_choices(self):
        self.client.force_login(self.other)
        for route in ['dashboard','medication_list','diary_list','history','quick_intake']:
            response=self.client.get(reverse(route))
            self.assertNotContains(response,'Чужой препарат');self.assertNotContains(response,'Личная запись')
        response=self.client.post(reverse('quick_intake'),{'mode':'existing','medication':self.med.pk})
        self.assertTrue(response.context['quick_form'].errors)
        self.assertEqual(self.med.intakes.count(),1)

    def test_each_user_can_have_entry_for_same_date_and_owner_cannot_be_forged(self):
        self.client.force_login(self.other)
        data={'date':self.today,'mood':'Хорошее','condition':'Нормальное','symptoms':'Моя запись','has_pain':'no','owner':self.owner.pk}
        self.client.post(reverse('diary_create'),data)
        self.assertEqual(HealthEntry.objects.filter(date=self.today).count(),2)
        self.assertEqual(HealthEntry.objects.get(symptoms='Моя запись').owner,self.other)
        response=self.client.post(reverse('diary_create'),data)
        self.assertTrue(response.context['form'].errors)

    def test_login_logout_remember_me_session_and_preference_cookie(self):
        response=self.client.post(reverse('login'),{'username':'owner','password':self.password,'remember_me':'on'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.session['_auth_user_id'],str(self.owner.pk))
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(),14*24*60*60)
        self.assertEqual(response.cookies['mediary_remember'].value,'1')
        self.assertTrue(response.cookies['mediary_remember']['httponly'])
        self.assertEqual(response.cookies['mediary_remember']['samesite'],'Lax')
        self.client.post(reverse('medication_section'),{'section':'occasional'})
        self.assertEqual(self.client.session.get_expiry_age(),14*24*60*60)
        self.assertEqual(self.client.get(reverse('logout')).status_code,405)
        self.client.post(reverse('logout'))
        self.assertNotIn('_auth_user_id',self.client.session)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code,302)
        # Preference survives logout; authentication does not.
        self.assertTrue(self.client.get(reverse('login')).context['form']['remember_me'].value())

    def test_unchecked_remember_me_expires_with_browser_session(self):
        response=self.client.post(reverse('login'),{'username':'owner','password':self.password})
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.assertEqual(response.cookies['sessionid']['max-age'],'')
        self.assertEqual(response.cookies['mediary_remember'].value,'0')

    def test_wrong_password_and_external_next(self):
        response=self.client.post(reverse('login'),{'username':'owner','password':'wrong'})
        self.assertTrue(response.context['form'].errors)
        self.assertNotIn('_auth_user_id',self.client.session)
        response=self.client.post(reverse('login'),{'username':'owner','password':self.password,'next':'https://example.org/'})
        self.assertEqual(response.url,reverse('dashboard'))

    def test_csrf_required_for_authentication_actions(self):
        client=Client(enforce_csrf_checks=True)
        for route in ['login','signup','logout']:
            self.assertEqual(client.post(reverse(route),{}).status_code,403)

    def test_login_rotates_session_and_logout_clears_state(self):
        session=self.client.session;session['medication_section']='courses';session.save();before=session.session_key
        self.client.post(reverse('login'),{'username':'owner','password':self.password})
        self.assertNotEqual(self.client.session.session_key,before)
        self.client.post(reverse('logout'))
        self.assertNotIn('medication_section',self.client.session)

    def test_password_change_keeps_current_session(self):
        self.client.force_login(self.owner)
        response=self.client.post(reverse('password_change'),{'old_password':self.password,'new_password1':'Another-Lab-Password-941!','new_password2':'Another-Lab-Password-941!'})
        self.assertRedirects(response,reverse('dashboard'))
        self.owner.refresh_from_db();self.assertTrue(self.owner.check_password('Another-Lab-Password-941!'))
