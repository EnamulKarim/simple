"""UNFPA stage-2 bulk approval (POST /api/programs/pending-approvals/bulk-approve/).

One click finalises the Bandhu records a manager already approved, but every
item still goes through _apply_decision, so the two-stage rules hold exactly as
for a single click: only a UNFPA reviewer closes stage 2, each approval is
recorded under the person who clicked, and nothing at stage 1 is touched.
"""
import datetime
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from indicators import bandhu as bnd
from programs.models import ServiceCenter, WellnessLogbookEntry as W

URL = '/api/programs/pending-approvals/bulk-approve/'
DAY = datetime.date(2026, 10, 5)


def _user(email, org, role):
    return User.objects.create_user(
        email=email, password='x', full_name=email.split('@')[0],
        organisation=org, role=role)


class BulkApproveTest(TestCase):
    def setUp(self):
        self.centre = ServiceCenter.objects.create(
            organisation='Bandhu', name='DIC', code='BND-DIC-BULK',
            center_type='DIC', district='Dhaka')
        self.unfpa = _user('u@unfpa', Organisation.UNFPA, Role.SUPERVISOR)
        self.dev = _user('d@dev', Organisation.UNFPA, Role.DEVELOPER)
        self.mgr = _user('m@bandhu', Organisation.BANDHU, Role.MANAGER)

    def _log(self, cid, status='MANAGER_APPROVED'):
        return W.objects.create(
            organisation='Bandhu', center=self.centre, client_id=cid,
            client_id_norm=cid, service_date=DAY, htc=True,
            approval_status=status)

    def _post(self, user, body):
        c = APIClient()
        c.force_authenticate(user)
        return c.post(URL, body, format='json')

    @staticmethod
    def _items(*objs, model_type='wellness_logbook'):
        return [{'id': str(o.id), 'model_type': model_type} for o in objs]

    def test_unfpa_finalises_every_manager_approved_item(self):
        rows = [self._log(f'09-000{i}') for i in range(3)]
        r = self._post(self.unfpa, {'items': self._items(*rows)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['approved'], 3)
        self.assertEqual(r.data['skipped'], [])
        for row in rows:
            row.refresh_from_db()
            self.assertEqual(row.approval_status, 'APPROVED')
            self.assertEqual(row.approved_by_id, self.unfpa.id)  # the clicker
            self.assertIsNotNone(row.approved_at)

    def test_approved_items_reach_the_indicators(self):
        rows = [self._log(f'09-001{i}') for i in range(2)]
        p0, p1 = datetime.date(2026, 10, 1), datetime.date(2026, 10, 31)
        self.assertEqual(bnd.compute_I_BND_1_1('Bandhu', p0, p1), 0)
        self._post(self.unfpa, {'items': self._items(*rows)})
        self.assertEqual(bnd.compute_I_BND_1_1('Bandhu', p0, p1), 2)
        self.assertEqual(bnd.compute_I_BND_1_5_hiv('Bandhu', p0, p1), 2)

    def test_developer_cannot_bulk_finalise(self):
        # The 2026-06 self-approve fix must hold in bulk too.
        row = self._log('09-0020')
        r = self._post(self.dev, {'items': self._items(row)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['approved'], 0)
        self.assertEqual(len(r.data['skipped']), 1)
        row.refresh_from_db()
        self.assertEqual(row.approval_status, 'MANAGER_APPROVED')

    def test_stage_one_items_are_skipped_not_promoted(self):
        # Bulk is for the UNFPA final stage only; a PENDING item must not move.
        ready = self._log('09-0030')
        pending = self._log('09-0031', status='PENDING')
        r = self._post(self.mgr, {'items': self._items(pending)})
        self.assertEqual(r.data['approved'], 0)
        pending.refresh_from_db()
        self.assertEqual(pending.approval_status, 'PENDING')

        r = self._post(self.unfpa, {'items': self._items(ready, pending)})
        self.assertEqual(r.data['approved'], 1)
        self.assertEqual([s['id'] for s in r.data['skipped']], [str(pending.id)])
        pending.refresh_from_db()
        self.assertEqual(pending.approval_status, 'PENDING')

    def test_bad_items_are_reported_and_the_rest_still_approved(self):
        row = self._log('09-0040')
        items = self._items(row) + [
            {'id': '00000000-0000-0000-0000-000000000000', 'model_type': 'wellness_logbook'},
            {'id': str(row.id), 'model_type': 'no_such_model'},
            {'model_type': 'wellness_logbook'},
        ]
        r = self._post(self.unfpa, {'items': items})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['approved'], 1)
        self.assertEqual(len(r.data['skipped']), 3)
        row.refresh_from_db()
        self.assertEqual(row.approval_status, 'APPROVED')

    def test_already_approved_item_is_skipped(self):
        row = self._log('09-0050', status='APPROVED')
        r = self._post(self.unfpa, {'items': self._items(row)})
        self.assertEqual(r.data['approved'], 0)
        self.assertEqual(len(r.data['skipped']), 1)

    def test_body_must_be_a_non_empty_bounded_list(self):
        self.assertEqual(self._post(self.unfpa, {}).status_code, 400)
        self.assertEqual(self._post(self.unfpa, {'items': []}).status_code, 400)
        self.assertEqual(self._post(self.unfpa, {'items': 'x'}).status_code, 400)
        too_many = [{'id': str(i), 'model_type': 'wellness_logbook'}
                    for i in range(501)]
        self.assertEqual(self._post(self.unfpa, {'items': too_many}).status_code, 400)

    def test_requires_authentication(self):
        r = APIClient().post(URL, {'items': []}, format='json')
        self.assertIn(r.status_code, (401, 403))

    def test_one_telegram_summary_not_one_per_item(self):
        rows = [self._log(f'09-006{i}') for i in range(4)]
        with mock.patch('programs.views._send_approval_telegram') as tg:
            self._post(self.unfpa, {'items': self._items(*rows)})
        self.assertEqual(tg.call_count, 1)
        kwargs = tg.call_args.kwargs
        self.assertEqual(kwargs['org'], 'Bandhu')
        self.assertTrue(kwargs['approved'])
        self.assertIn('4', kwargs['form_label'])
