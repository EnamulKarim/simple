"""
Form 05 (facility neonatal death) makes the death date optional behind
'death_datetime_recorded', but the MPDSR case needs a date. A submission with
no death date was rejected with 400 and never reached SIMPLE (Gaibandha case 33,
Kobo 840212461, 14 Aug 2026). The reconciliation could not see it because a 400
creates no row.

Now the admission date (then the ER arrival date) stands in, and the case is
marked date_of_death_estimated so nobody reads it as a recorded date.
"""
from unittest import mock

from django.test import TestCase

from mpdsr.models import MPDSRCase
from programs.ciprb_handlers import handle_ciprb_mpdsr_facility_neonatal


def _f05(**extra):
    p = {'_id': '930001', 'district': 'gaibandha', 'case_serial': '33',
         'death_datetime_recorded': 'recorded', '_submitted_by': 'ciprb_field'}
    p.update(extra)
    return p


@mock.patch('programs.refs._writeback_kobo_id')
class F05MissingDeathDateTest(TestCase):

    def test_admission_date_stands_in_and_is_flagged(self, wb):
        resp = handle_ciprb_mpdsr_facility_neonatal(
            _f05(admission_date='2026-05-22', er_arrival_date='2026-05-21'),
            lat=None, lng=None)
        self.assertLess(getattr(resp, 'status_code', 200), 400)
        case = MPDSRCase.objects.get()
        self.assertEqual(str(case.date_of_death), '2026-05-22')
        self.assertTrue(case.date_of_death_estimated)

    def test_er_arrival_used_when_no_admission_date(self, wb):
        handle_ciprb_mpdsr_facility_neonatal(
            _f05(er_arrival_date='2026-05-21'), lat=None, lng=None)
        case = MPDSRCase.objects.get()
        self.assertEqual(str(case.date_of_death), '2026-05-21')
        self.assertTrue(case.date_of_death_estimated)

    def test_recorded_death_date_is_not_flagged(self, wb):
        handle_ciprb_mpdsr_facility_neonatal(
            _f05(death_date='2026-05-24', admission_date='2026-05-22'),
            lat=None, lng=None)
        case = MPDSRCase.objects.get()
        self.assertEqual(str(case.date_of_death), '2026-05-24')
        self.assertFalse(case.date_of_death_estimated)

    def test_no_date_at_all_is_still_rejected(self, wb):
        resp = handle_ciprb_mpdsr_facility_neonatal(_f05(), lat=None, lng=None)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(MPDSRCase.objects.count(), 0)
