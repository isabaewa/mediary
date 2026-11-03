"""Поиск, сочетание фильтров, порядок, страницы и изоляция владельцев."""

from datetime import timedelta
from html import unescape
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from diary.models import HealthEntry, Medication

from .base import OwnedTestCase


class MedicationListFilterTests(OwnedTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.active = self.make_med('Ёлка', start=0, end=0, purpose='ГОЛОВНАЯ боль')
        self.finished = self.make_med('Бета', start=-3, end=-1, dosage='Тестовая дозировка')
        self.upcoming = self.make_med('Альфа', start=1, end=2)
        self.occasional = Medication.objects.create(
            owner=self.user,
            name='Аспирин',
            dosage='1',
            as_needed=True,
        )

    def make_med(self, name, *, start, end, **kwargs):
        return Medication.objects.create(
            owner=self.user,
            name=name,
            dosage=kwargs.pop('dosage', '1'),
            start_date=self.today + timedelta(days=start),
            end_date=self.today + timedelta(days=end),
            **kwargs,
        )

    def get(self, **params):
        return self.client.get(reverse('medication_list'), params)

    def ids(self, response):
        return [record.pk for record in response.context['medications']]

    def test_cyrillic_search_ignores_case_in_name_and_other_text(self):
        for query, expected in [
            ('ёлКА', self.active),
            ('головная', self.active),
            ('дозировка', self.finished),
        ]:
            with self.subTest(query=query):
                self.assertEqual(self.ids(self.get(q=query)), [expected.pk])

    def test_status_boundaries_are_inclusive_and_do_not_include_occasional(self):
        for status, expected in [
            ('active', self.active),
            ('finished', self.finished),
            ('upcoming', self.upcoming),
        ]:
            with self.subTest(status=status):
                self.assertEqual(self.ids(self.get(status=status)), [expected.pk])

    def test_section_status_and_search_are_combined(self):
        self.assertEqual(
            self.ids(self.get(section='courses', status='active', q='ЁЛКА')), [self.active.pk]
        )
        self.assertEqual(self.ids(self.get(section='occasional')), [self.occasional.pk])
        self.assertEqual(self.ids(self.get(section='occasional', status='active')), [])

    def test_name_sort_is_global_not_separate_for_course_groups(self):
        expected = [self.upcoming.pk, self.occasional.pk, self.finished.pk, self.active.pk]
        self.assertEqual(self.ids(self.get(sort='name_asc')), expected)
        self.assertEqual(self.ids(self.get(sort='name_desc')), expected[::-1])

    def test_date_sorts_place_missing_course_dates_last(self):
        self.assertEqual(
            self.ids(self.get(sort='start_desc')),
            [self.upcoming.pk, self.active.pk, self.finished.pk, self.occasional.pk],
        )
        self.assertEqual(
            self.ids(self.get(sort='end_asc')),
            [self.finished.pk, self.active.pk, self.upcoming.pk, self.occasional.pk],
        )

    def test_query_is_literal_and_does_not_become_sql_or_html(self):
        literal = Medication.objects.create(
            owner=self.user, name='Тест %_ запись', dosage='1', as_needed=True
        )
        self.assertEqual(self.ids(self.get(q='%_')), [literal.pk])
        response = self.get(q='<script>alert(1)</script>')
        self.assertEqual(self.ids(response), [])
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertEqual(self.ids(self.get(q="' OR 1=1 --")), [])

    def test_invalid_parameters_show_errors_without_expanding_results(self):
        for params in [
            {'sort': 'owner__password'},
            {'status': 'wrong'},
            {'section': 'wrong'},
            {'q': 'x' * 201},
        ]:
            with self.subTest(params=params):
                response = self.get(**params)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['filter_form'].errors)
                self.assertEqual(self.ids(response), [])

    def test_foreign_records_are_not_counted_or_found(self):
        other = get_user_model().objects.create_user(username='other_filter_owner')
        Medication.objects.create(owner=other, name='Скрытый', dosage='1', as_needed=True)
        response = self.get(q='скрытый')
        self.assertEqual(self.ids(response), [])
        self.assertEqual(response.context['total_records'], 4)

    def test_empty_state_distinguishes_no_matches_from_no_data(self):
        self.assertContains(
            self.get(q='несуществующий'), 'По заданным условиям препараты не найдены'
        )
        Medication.objects.filter(owner=self.user).delete()
        self.assertContains(self.get(), 'Препаратов пока нет')

    def test_pagination_is_stable_and_keeps_the_query(self):
        for index in range(25):
            Medication.objects.create(
                owner=self.user, name=f'Запас {index:02}', dosage='1', as_needed=True
            )
        params = {'q': 'запас', 'section': 'occasional', 'sort': 'name_desc'}
        first = self.get(**params)
        second = self.get(**params, page=2)
        self.assertEqual(len(self.ids(first)), 20)
        self.assertEqual(len(self.ids(second)), 5)
        self.assertFalse(set(self.ids(first)) & set(self.ids(second)))
        self.assertEqual(first.context['medications'][0].name, 'Запас 24')
        from re import search

        link = search(r'href="([^"]+)" rel="next"', first.content.decode())[1]
        query = parse_qs(urlsplit(unescape(link)).query)
        self.assertEqual(query, {**{key: [value] for key, value in params.items()}, 'page': ['2']})
        for page in ['invalid', '999', '0']:
            self.assertEqual(self.get(**params, page=page).status_code, 200)

    def test_session_section_still_works_and_tabs_keep_search(self):
        self.client.post(reverse('medication_section'), {'section': 'occasional'})
        self.assertEqual(self.ids(self.get()), [self.occasional.pk])
        self.assertEqual(len(self.ids(self.get(section='all'))), 4)
        response = self.client.post(
            reverse('medication_section'),
            {
                'section': 'courses',
                'q': 'ёлка',
                'sort': 'name_desc',
                'page': '2',
            },
        )
        params = parse_qs(urlsplit(response.url).query)
        self.assertEqual(params, {'section': ['courses'], 'q': ['ёлка'], 'sort': ['name_desc']})
        self.assertEqual(self.client.session['medication_section'], 'courses')


class HealthListFilterTests(OwnedTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.entries = [
            HealthEntry.objects.create(
                owner=self.user,
                date=self.today - timedelta(days=index),
                mood='Хорошее' if index != 1 else 'Плохое',
                condition='Нормальное' if index != 1 else 'Плохое',
                pain_intensity=pain,
                symptoms='ГОЛОВНАЯ боль' if index else 'Нет симптомов',
                note='СОН' if index == 0 else None,
            )
            for index, pain in enumerate([0, 7, 3])
        ]

    def get(self, **params):
        return self.client.get(reverse('diary_list'), params)

    def ids(self, response):
        return [entry.pk for entry in response.context['entries']]

    def test_search_in_symptoms_and_nullable_notes_ignores_case(self):
        self.assertEqual(self.ids(self.get(q='головная')), [self.entries[1].pk, self.entries[2].pk])
        self.assertEqual(self.ids(self.get(q='сон')), [self.entries[0].pk])

    def test_date_bounds_include_both_ends(self):
        self.assertEqual(
            self.ids(
                self.get(
                    date_from=self.entries[2].date.isoformat(),
                    date_to=self.entries[1].date.isoformat(),
                )
            ),
            [self.entries[1].pk, self.entries[2].pk],
        )

    def test_condition_mood_pain_and_query_combine(self):
        self.assertEqual(
            self.ids(
                self.get(
                    q='головная',
                    condition='Нормальное',
                    mood='Хорошее',
                    pain_min=2,
                    pain_max=4,
                )
            ),
            [self.entries[2].pk],
        )

    def test_zero_is_a_real_pain_bound(self):
        self.assertEqual(self.ids(self.get(pain_min=0, pain_max=0)), [self.entries[0].pk])

    def test_date_and_pain_sorting(self):
        self.assertEqual(self.ids(self.get(sort='date_asc')), [e.pk for e in self.entries[::-1]])
        self.assertEqual(
            self.ids(self.get(sort='pain_desc')), [self.entries[i].pk for i in [1, 2, 0]]
        )
        self.assertEqual(
            self.ids(self.get(sort='pain_asc')), [self.entries[i].pk for i in [0, 2, 1]]
        )

    def test_bad_ranges_and_unknown_values_do_not_silently_drop_filters(self):
        cases = [
            {'date_from': 'not-a-date'},
            {'date_from': self.today.isoformat(), 'date_to': self.entries[2].date.isoformat()},
            {'pain_min': 8, 'pain_max': 2},
            {'pain_min': -1},
            {'pain_max': 11},
            {'pain_min': 'x'},
            {'condition': 'unknown'},
            {'mood': 'unknown'},
            {'sort': '-owner'},
        ]
        for params in cases:
            with self.subTest(params=params):
                response = self.get(**params)
                self.assertTrue(response.context['filter_form'].errors)
                self.assertEqual(self.ids(response), [])
                self.assertContains(response, 'role="alert"')

    def test_foreign_entries_are_not_in_results_or_total(self):
        other = get_user_model().objects.create_user(username='other_health_filter_owner')
        HealthEntry.objects.create(
            owner=other,
            date=self.today,
            mood='Хорошее',
            condition='Нормальное',
            symptoms='Скрытый текст',
            pain_intensity=0,
        )
        response = self.get(q='скрытый')
        self.assertEqual(self.ids(response), [])
        self.assertEqual(response.context['total_records'], 3)

    def test_search_results_have_distinct_empty_message(self):
        self.assertContains(self.get(q='нет такого'), 'По заданным условиям записи не найдены')
        HealthEntry.objects.filter(owner=self.user).delete()
        self.assertContains(self.get(), 'В дневнике пока нет ни одной записи')

    def test_health_pagination_keeps_filters(self):
        for offset in range(3, 27):
            HealthEntry.objects.create(
                owner=self.user,
                date=self.today - timedelta(days=offset),
                mood='Хорошее',
                condition='Нормальное',
                symptoms='Список',
                pain_intensity=2,
            )
        first = self.get(q='список', pain_min=0, sort='date_asc')
        second = self.get(q='список', pain_min=0, sort='date_asc', page=2)
        self.assertEqual(len(self.ids(first)), 20)
        self.assertEqual(len(self.ids(second)), 4)
        self.assertFalse(set(self.ids(first)) & set(self.ids(second)))
        self.assertContains(first, 'pain_min=0')
        self.assertContains(first, 'sort=date_asc')
