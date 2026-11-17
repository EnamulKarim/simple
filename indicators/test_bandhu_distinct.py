"""Bandhu person indicators must never count the same person twice.

Rafi 2026-11-17: 1.1, 1.2, 1.3, 1.5a and 1.5b count DISTINCT beneficiaries.
Repeat visits, and the same visit submitted twice, collapse to one person.
"""
from datetime import date

from django.test import TestCase

from indicators import bandhu as bnd
from programs.models import ServiceCenter, WellnessLogbookEntry

P0, P1 = date(2026, 10, 1), date(2026, 10, 31)


class BandhuDistinctPersonsTest(TestCase):
    def setUp(self):
        self.center = ServiceCenter.objects.create(
            organisation='Bandhu', name='Bandhu DIC', code='BAN-001',
            center_type=ServiceCenter.DIC, district='Dhaka', is_active=True,
        )
        self._n = 0

    def _visit(self, pid, day=5, status='APPROVED', norm=True, **flags):
        self._n += 1
        return WellnessLogbookEntry.objects.create(
            organisation='Bandhu', center=self.center,
            service_date=date(2026, 10, day),
            client_id=pid, client_id_norm=pid if norm else '',
            approval_status=status, kobo_submission_id=f'k{self._n}', **flags,
        )

    def test_repeat_visits_by_one_person_count_once(self):
        all_services = dict(sti_screening=True, htc=True, gbv=True, mental_health=True)
        self._visit('09-0001', day=3, **all_services)
        self._visit('09-0001', day=17, **all_services)
        for fn in (bnd.compute_I_BND_1_1, bnd.compute_I_BND_1_2, bnd.compute_I_BND_1_3,
                   bnd.compute_I_BND_1_5_sti, bnd.compute_I_BND_1_5_hiv):
            self.assertEqual(fn('Bandhu', P0, P1), 1, fn.__name__)

    def test_duplicate_submission_same_day_counts_once(self):
        self._visit('05-0278', day=16, htc=True)
        self._visit('05-0278', day=16, htc=True)   # same visit sent twice
        self.assertEqual(bnd.compute_I_BND_1_5_hiv('Bandhu', P0, P1), 1)

    def test_different_people_each_count(self):
        self._visit('09-0001', sti_screening=True)
        self._visit('09-0002', sti_screening=True)
        self._visit('01-0001', sti_screening=True)  # same serial, other district = other person
        self.assertEqual(bnd.compute_I_BND_1_5_sti('Bandhu', P0, P1), 3)

    def test_raw_id_and_normalised_id_of_same_person_count_once(self):
        self._visit('09-0007', htc=True)
        self._visit(' 09-0007 ', htc=True, norm=False)  # norm blank, raw id with spaces
        self.assertEqual(bnd.compute_I_BND_1_5_hiv('Bandhu', P0, P1), 1)

    def test_unapproved_visits_are_not_counted(self):
        self._visit('09-0001', htc=True, status='MANAGER_APPROVED')
        self._visit('09-0002', htc=True, status='PENDING')
        self.assertEqual(bnd.compute_I_BND_1_5_hiv('Bandhu', P0, P1), 0)
        self.assertEqual(bnd.compute_I_BND_1_1('Bandhu', P0, P1), 0)

    def test_person_without_the_service_is_not_counted_for_it(self):
        self._visit('09-0001', htc=True)
        self._visit('09-0002', recreation=True)
        self.assertEqual(bnd.compute_I_BND_1_1('Bandhu', P0, P1), 2)
        self.assertEqual(bnd.compute_I_BND_1_5_hiv('Bandhu', P0, P1), 1)
        self.assertEqual(bnd.compute_I_BND_1_2('Bandhu', P0, P1), 0)
