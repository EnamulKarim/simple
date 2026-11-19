"""
A record built from several Kobo submissions must not vanish when only one of
them is deleted.

A fistula patient is one row fed by up to five stage forms, and the row keeps
only the LATEST submission id. If that latest stage form is deleted in Kobo,
the stored id disappears while the registration is still live, and the sweep
used to remove the whole patient. Merged MPDSR cases and response-plan actions
have the same shape. The sweep now looks for another live submission that
feeds the same record and, when it finds one, keeps the record and points it
at that submission instead.
"""
import os
from datetime import date
from unittest import mock

from django.test import TestCase

from fistula.ciprb_models import CIPRBFistulaCase
from mpdsr.models import MPDSRCase
from programs import kobo_withdrawals as kw
from programs.ciprb_handlers import _mpdsr_hash

REG_ID, DIAG_ID = '900000101', '900000102'


def _fistula(code='1-0901', kobo=DIAG_ID):
    return CIPRBFistulaCase.objects.create(
        patient_code=code, organisation='CIPRB', district='Bhola',
        name='Rahima', approval_status='APPROVED', current_stage='diagnosed',
        kobo_submission_id=kobo)


def _registration(code='1-0901', sid=REG_ID):
    return {'_id': int(sid), 'stage': 'suspected', 'patient_code': code,
            'district': 'bhola', 'name': 'Rahima'}


@mock.patch.dict(os.environ, {'KOBO_TOKEN': 'tok'})
class MultiSubmissionRescueTest(TestCase):

    def test_patient_survives_when_a_later_stage_form_is_deleted(self):
        case = _fistula()
        with mock.patch.object(kw, 'live_submission_ids',
                               return_value=({REG_ID}, {})), \
                mock.patch('programs.ciprb_replay._fetch',
                           return_value=[_registration()]):
            result = kw.reconcile(apply=True)
        case.refresh_from_db()
        self.assertEqual(case.kobo_submission_id, REG_ID)
        self.assertEqual(result['candidates'], [])
        self.assertEqual(len(result['rescued']), 1)

    def test_patient_with_no_live_submission_is_still_a_candidate(self):
        _fistula(code='1-0999')
        rows = kw.find_withdrawn({REG_ID})
        with mock.patch('programs.ciprb_replay._fetch',
                        return_value=[_registration(code='1-0901')]):
            kept, rescued = kw.rescue_multi_submission(rows, 'tok')
        self.assertEqual(len(kept), 1)
        self.assertEqual(rescued, [])

    def test_unreadable_form_keeps_its_records_out_of_deletion(self):
        _fistula()
        rows = kw.find_withdrawn(set())
        with mock.patch('programs.ciprb_replay._fetch',
                        side_effect=RuntimeError('kobo down')):
            kept, rescued = kw.rescue_multi_submission(rows, 'tok')
        self.assertEqual(kept, [])
        self.assertEqual(rescued, [])
        self.assertEqual(CIPRBFistulaCase.objects.count(), 1)

    def test_dry_run_does_not_repoint(self):
        case = _fistula()
        rows = kw.find_withdrawn({REG_ID})
        with mock.patch('programs.ciprb_replay._fetch',
                        return_value=[_registration()]):
            kept, rescued = kw.rescue_multi_submission(rows, 'tok', apply=False)
        case.refresh_from_db()
        self.assertEqual(kept, [])
        self.assertEqual(len(rescued), 1)
        self.assertEqual(case.kobo_submission_id, DIAG_ID)

    def test_merged_mpdsr_case_survives_deleting_its_latest_resubmission(self):
        case = MPDSRCase.objects.create(
            partner='CIPRB', sub_form_type='f1', district='Bhola',
            date_of_death=date(2026, 7, 1), death_type='maternal',
            case_hash=_mpdsr_hash('f1', 'Bhola', '3'),
            kobo_submission_id='860000002', approval_status='APPROVED')
        older = {'_id': 860000001, 'district': 'bhola', 'case_serial': '3',
                 'death_date': '2026-07-01'}

        def fetch(uid, token, limit=None):
            from programs.ciprb_replay import CIPRB_SLUG_TO_UID
            if uid == CIPRB_SLUG_TO_UID['ciprb_mpdsr_community_maternal_v1']:
                return [older]
            return []
        rows = kw.find_withdrawn({'860000001'})
        with mock.patch('programs.ciprb_replay._fetch', side_effect=fetch):
            kept, rescued = kw.rescue_multi_submission(rows, 'tok', apply=True)
        case.refresh_from_db()
        self.assertEqual(kept, [])
        self.assertEqual(case.kobo_submission_id, '860000001')
