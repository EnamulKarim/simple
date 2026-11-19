"""
Kobo write-backs must only leave the building when the database work commits.

The hourly CIPRB reconciliation (mpdsr.reconcile) replays every Kobo submission
through the real handler inside a savepoint and rolls it back. The handler
allocates a system ref and used to start the Kobo write-back thread right
away, so a rolled-back replay still PATCHed Kobo: 16 Notification Slip 01
submissions were rewritten every hour with a ref SIMPLE never kept
(3,621 edits between 12 and 19 Nov 2026). Deferring the write-back with
transaction.on_commit makes a rolled-back replay a true no-op on Kobo.
"""
from unittest import mock

from django.db import transaction
from django.test import TestCase, override_settings

from mpdsr.ciprb_models import MPDSRDeathNotification
from mpdsr.reconcile import _counter, _replay_form
from programs.bandhu_handlers import _writeback_kobo_id
from programs.webhook import FORM_HANDLERS

SLIP01 = 'ciprb_notification_slip_01_v1'


def _slip_sub(kobo_id='920001'):
    return {'_id': kobo_id, '_submission_time': '2026-08-02T10:00:00',
            'district': 'bhola', 'death_date': '2026-08-01',
            'mother_name': 'Amena', 'case_serial': '7',
            'death_kind': 'maternal', 'slip_date': '2026-08-02',
            '_submitted_by': 'ciprb_field'}


@override_settings(KOBO_API_TOKEN='test-token')
class WritebackCommitTest(TestCase):

    def test_rolled_back_writeback_never_reaches_kobo(self):
        with mock.patch('threading.Thread') as thread:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with transaction.atomic():
                    _writeback_kobo_id('assetuid', '920001', 'NS1-BH-0001',
                                       field_path='system_ref')
                    transaction.set_rollback(True)
        self.assertEqual(callbacks, [])
        thread.assert_not_called()

    def test_committed_writeback_still_reaches_kobo(self):
        with mock.patch('threading.Thread') as thread:
            with self.captureOnCommitCallbacks(execute=True):
                _writeback_kobo_id('assetuid', '920001', 'NS1-BH-0001',
                                   field_path='system_ref')
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()

    def test_reconcile_replay_does_not_write_to_kobo(self):
        """The real reconcile path: a stranded slip is counted, its row and
        its ref are rolled back, and nothing is sent to Kobo."""
        with mock.patch('mpdsr.reconcile._fetch', return_value=[_slip_sub()]), \
                mock.patch('threading.Thread') as thread:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with transaction.atomic():
                    rec = _replay_form(SLIP01, 'assetuid', FORM_HANDLERS[SLIP01],
                                       _counter(SLIP01), 'tok', None)
        self.assertEqual(rec['stranded'], 1)
        self.assertEqual(MPDSRDeathNotification.objects.count(), 0)
        self.assertEqual(callbacks, [])
        thread.assert_not_called()

    def test_reconcile_skips_a_record_deleted_from_the_dashboard(self):
        """Deleting from the approval queue keeps the Kobo copy on purpose.
        That submission is a decision, not a gap, so the hourly check must
        not keep reporting it as stranded."""
        from programs.models import KoboWithdrawal
        KoboWithdrawal.objects.create(
            model_label='mpdsr.MPDSRDeathNotification', record_pk='x',
            kobo_submission_id='920001', organisation='CIPRB',
            approval_status='PENDING', snapshot={},
            actor='manager@example.org', reason='wrong entry')
        with mock.patch('mpdsr.reconcile._fetch', return_value=[_slip_sub()]):
            with transaction.atomic():
                rec = _replay_form(SLIP01, 'assetuid', FORM_HANDLERS[SLIP01],
                                   _counter(SLIP01), 'tok', None)
        self.assertEqual(rec['stranded'], 0)
        self.assertEqual(rec['kobo_count'], 0)
        self.assertEqual(rec['deleted_in_dashboard'], 1)

    def test_gap_audit_does_not_write_to_kobo(self):
        from mpdsr.reconcile import audit_ciprb_gap
        with mock.patch('mpdsr.reconcile._fetch', return_value=[_slip_sub()]), \
                mock.patch('threading.Thread') as thread:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with transaction.atomic():
                    res = audit_ciprb_gap('tok', slugs=[SLIP01])
        self.assertEqual(res[0]['missing_total'], 1)
        self.assertEqual(MPDSRDeathNotification.objects.count(), 0)
        self.assertEqual(callbacks, [])
        thread.assert_not_called()
