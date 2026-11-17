"""mother_list.csv: the person picker on the LIVE Bandhu Beneficiary Service Log.

Field report 2026-11-17 (Ashis, Noakhali): Mother List IDs 04-0476..04-0592
were registered in Spondon but never appeared under "Which person?". The live
form (aMzxogjXhaE8FGdRhCjoe8) reads `mother_list.csv`, which nothing in Spondon
generated or refreshed, so it was frozen at its deploy-time snapshot. The push
also still targeted forms marked "STALE - DO NOT USE".

Pinned here: the CSV's exact shape (the form's select_one_from_file filter and
five pulldata() calls read these columns by name), that a new registration
lands in it, and that the push and the resync backstop both cover it.
"""
import csv
import datetime
import io
from unittest import mock

from django.test import TestCase

from programs import signals
from programs.management.commands import export_bandhu_clients as bandhu
from programs.management.commands import export_bandhu_mother_list as ml
from programs.models import Client, ServiceCenter

LIVE_SERVICE_LOG = 'aMzxogjXhaE8FGdRhCjoe8'
LIVE_MOTHER_LIST = 'aUrcU9Adb9rJDgH5BVbiMM'
STALE = {'a7PgkrZcH8gMxqsdgkf6fF', 'a6nEhvxFfDr2xPpcqnYw4f'}


def _rows(csv_bytes):
    return list(csv.DictReader(io.StringIO(csv_bytes.decode('utf-8'))))


class MotherListCsvTest(TestCase):
    def setUp(self):
        self.noakhali = ServiceCenter.objects.create(
            organisation='Bandhu', name='WC Noakhali', code='BND-DIC-T04',
            center_type='DIC', district='Noakhali')

    def _client(self, cid, name='Rina', status=Client.APPROVED, **kw):
        return Client.objects.create(
            organisation='Bandhu', center=self.noakhali, client_id=cid,
            name=name, approval_status=status, **kw)

    def test_header_matches_the_live_form_exactly(self):
        csv_bytes, _ = ml.build_csv()
        header = csv_bytes.decode('utf-8').splitlines()[0]
        self.assertEqual(header, 'name,label,centre,tg,cruising_spot,age,father,ml_id,source_kobo_id')

    def test_registered_client_row_feeds_picker_and_pulldata(self):
        this_year = datetime.date.today().year
        self._client('04-0592', name='Marium Akter', father_name='Abdul',
                     birth_year=this_year - 30, target_group_code='05',
                     spot_name='Maijdee bazar', kobo_submission_id='901')
        csv_bytes, n = ml.build_csv()
        self.assertEqual(n, 1)
        row = _rows(csv_bytes)[0]
        self.assertEqual(row, {
            'name': '04-0592', 'label': '04-0592 | Marium Akter', 'centre': '04',
            'tg': '05', 'cruising_spot': 'Maijdee bazar', 'age': '30',
            'father': 'Abdul', 'ml_id': '04-0592', 'source_kobo_id': '901',
        })

    def test_single_digit_tg_code_is_zero_padded(self):
        self._client('04-0001', target_group_code='3')
        self.assertEqual(_rows(ml.build_csv()[0])[0]['tg'], '03')

    def test_stubs_and_unapproved_are_left_out(self):
        self._client('04-0010')
        self._client('04-0011', name='Unknown')
        self._client('04-0012', name='')
        self._client('04-0013', status=Client.PENDING)
        Client.objects.create(organisation='PHD', center=self.noakhali,
                              client_id='PHD-1', name='X',
                              approval_status=Client.APPROVED)
        self.assertEqual([r['name'] for r in _rows(ml.build_csv()[0])], ['04-0010'])

    def test_centre_falls_back_to_the_centre_district_for_odd_ids(self):
        # A typo id kept verbatim (no DD- prefix) still lands in its centre.
        self._client('040002')
        self.assertEqual(_rows(ml.build_csv()[0])[0]['centre'], '04')

    def test_rows_are_in_id_order(self):
        for cid in ('04-0477', '04-0476', '04-0592'):
            self._client(cid)
        self.assertEqual([r['name'] for r in _rows(ml.build_csv()[0])],
                         ['04-0476', '04-0477', '04-0592'])


class PushTargetsTest(TestCase):
    def test_mother_list_csv_goes_to_the_live_service_log(self):
        self.assertEqual(ml.CSV_FILENAME, 'mother_list.csv')
        self.assertEqual([u for u, _ in ml.FORM_UIDS], [LIVE_SERVICE_LOG])

    def test_bandhu_clients_csv_goes_to_live_mother_list_not_stale_forms(self):
        uids = {u for u, _ in bandhu.BANDHU_FORM_UIDS}
        self.assertIn(LIVE_MOTHER_LIST, uids)
        self.assertFalse(uids & STALE, 'still pushing to STALE - DO NOT USE forms')

    def test_upload_targets_only_the_module_forms(self):
        with mock.patch.object(bandhu, '_kobo_token', return_value='t'), \
                mock.patch('programs.management.commands.export_bandhu_clients.requests') as rq:
            rq.get.return_value.status_code = 200
            rq.get.return_value.json.return_value = {'results': []}
            rq.post.return_value.status_code = 201
            self.assertTrue(ml.upload_to_kobo(b'name\n', mock.Mock()))
        posted = [c.args[0] for c in rq.post.call_args_list]
        self.assertEqual(len(posted), 1)
        self.assertIn(LIVE_SERVICE_LOG, posted[0])
        self.assertEqual(rq.post.call_args.kwargs['files']['content'][0], 'mother_list.csv')


class PushWiringTest(TestCase):
    def test_bandhu_client_save_schedules_both_csvs(self):
        centre = ServiceCenter.objects.create(
            organisation='Bandhu', name='WC', code='BND-DIC-T05',
            center_type='DIC', district='Noakhali')
        with mock.patch.object(signals, '_schedule_push') as push, \
                self.captureOnCommitCallbacks(execute=True):
            Client.objects.create(organisation='Bandhu', center=centre,
                                  client_id='04-0600', name='New',
                                  approval_status=Client.APPROVED)
        self.assertEqual(sorted(c.args[0] for c in push.call_args_list),
                         ['Bandhu', 'BandhuMotherList'])

    def test_export_registry_knows_the_mother_list_module(self):
        self.assertIs(signals._load_export('BandhuMotherList'), ml)

    def test_resync_backstop_covers_the_mother_list(self):
        from programs.management.commands import resync_client_csvs as rs
        names = [fname for _mod, _label, _uids, fname, _recent in rs.sync_targets()]
        self.assertIn('mother_list.csv', names)
