"""Bandhu Activity & Operations reports must be approvable.

BandhuActivityReport (added 0bb94ce, 2026-11-12) lands PENDING and every Bandhu
activity indicator (1.4a, 1.6, 1.8, 1.9, 2.1-2.6, 4.1, 4.2) sums APPROVED
reports only. It was never added to _APPROVAL_MODELS, so no queue, endpoint or
role could approve one: 39 sat PENDING in production and every one of those
cards read 0 (found 2026-11-17). Same trap StockEntry fell into on 2026-08-14.

The completeness test at the bottom closes the class of bug: any model with an
approval_status must be in the queue or on the allowlist with a reason.
"""
import datetime

from django.apps import apps
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from indicators import bandhu as bnd
from programs.models import BandhuActivityReport, ServiceCenter
from programs.views import _APPROVAL_MODELS

DAY = datetime.date(2026, 10, 15)


def _user(email, org, role):
    return User.objects.create_user(email=email, password='x', full_name=email,
                                    organisation=org, role=role)


class ActivityReportApprovalTest(TestCase):
    def setUp(self):
        cache.clear()
        self.centre = ServiceCenter.objects.create(
            organisation='Bandhu', name='WC Noakhali', code='BND-DIC-AR',
            center_type='DIC', district='Noakhali')
        self.mgr = _user('m@bandhu', Organisation.BANDHU, Role.MANAGER)
        self.unfpa = _user('u@unfpa', Organisation.UNFPA, Role.SUPERVISOR)
        self.report = BandhuActivityReport.objects.create(
            organisation='Bandhu', center=self.centre, report_date=DAY,
            outreach_sessions=6, iec_sbcc_distributed=120)

    def _as(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def _decide(self, user):
        return self._as(user).post('/api/programs/pending-approvals/', {
            'id': str(self.report.id), 'model_type': 'activity_report',
            'action': 'approve', 'reason': ''}, format='json')

    def test_surfaces_in_the_bandhu_manager_queue_with_a_readable_summary(self):
        r = self._as(self.mgr).get('/api/programs/pending-approvals/')
        self.assertEqual(r.status_code, 200)
        item = next(i for i in r.data['items'] if i['model_type'] == 'activity_report')
        self.assertEqual(item['endpoint'], 'activity-reports')
        self.assertIn('WC Noakhali', item['summary'])
        self.assertIn('2026-10-15', item['summary'])
        self.assertIn('6 outreach sessions', item['summary'])

    def test_two_stage_approval_releases_it_to_the_indicators(self):
        p0, p1 = datetime.date(2026, 10, 1), datetime.date(2026, 10, 31)
        self.assertEqual(self._decide(self.mgr).status_code, 200)
        self.report.refresh_from_db()
        self.assertEqual(self.report.approval_status, 'MANAGER_APPROVED')
        self.assertEqual(bnd.compute_I_BND_1_4A('Bandhu', p0, p1), 0)

        self.assertEqual(self._decide(self.unfpa).status_code, 200)
        self.report.refresh_from_db()
        self.assertEqual(self.report.approval_status, 'APPROVED')
        self.assertEqual(bnd.compute_I_BND_1_4A('Bandhu', p0, p1), 6)
        self.assertEqual(bnd.compute_I_BND_4_1('Bandhu', p0, p1), 120)

    def test_unfpa_can_bulk_finalise_it(self):
        self._decide(self.mgr)
        r = self._as(self.unfpa).post(
            '/api/programs/pending-approvals/bulk-approve/',
            {'items': [{'id': str(self.report.id), 'model_type': 'activity_report'}]},
            format='json')
        self.assertEqual(r.data['approved'], 1)

    def test_detail_endpoint_serves_the_reviewer(self):
        r = self._as(self.unfpa).get(f'/api/programs/activity-reports/{self.report.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['outreach_sessions'], 6)


# Models that carry approval_status but are approved somewhere else on purpose.
NOT_IN_QUEUE = {
    'programs.KoboWithdrawal': 'deletion audit log; approval_status is a snapshot',
    'pharmacy.PrescriptionRecord': 'own approval flow in PrescriptionRecordViewSet',
}


class ApprovalRegistryCompletenessTest(TestCase):
    def test_every_approvable_model_is_in_the_queue(self):
        queued = {qs().model._meta.label for _slug, qs in _APPROVAL_MODELS}
        missing = []
        for model in apps.get_models():
            try:
                model._meta.get_field('approval_status')
            except Exception:
                continue
            label = model._meta.label
            if label not in queued and label not in NOT_IN_QUEUE:
                missing.append(label)
        self.assertEqual(missing, [], 'add these to _APPROVAL_MODELS (or to '
                         'NOT_IN_QUEUE with a reason), or they can never be approved')
