"""Functional-centre indicators (Bandhu 1.8, PHD SL8) report 0 without real data.

A centre configured in the registry but with nothing reported must count 0 — a
pre-launch / freshly-wiped system shows 0 functional centres, not "all centres
at 100%". Pins the fix for "no indicator is on track if no data is there".

Bandhu 1.8 is the SUM of the Activity & Operations report's
`wellness_centres_improved` tally over APPROVED reports in the period (Rafi's
2026-11-12 M&E decision, indicators/bandhu.py). Per-centre service activity
(OutreachSession etc.) no longer drives it. PHD SL8 stays activity-gated.
"""
import datetime

from django.core.cache import cache
from django.test import TestCase

from programs.models import (
    ServiceCenter, OutreachSession, NilReport, BandhuActivityReport,
)
from indicators import bandhu, phd


class FunctionalCentresTest(TestCase):
    def setUp(self):
        cache.clear()
        self.today = datetime.date.today()
        self.start = self.today - datetime.timedelta(days=30)
        self.end = self.today + datetime.timedelta(days=1)
        self.dic1 = ServiceCenter.objects.create(
            organisation='Bandhu', name='DIC 1', code='BND-DIC-T1',
            center_type='DIC', district='Sunamganj')
        self.dic2 = ServiceCenter.objects.create(
            organisation='Bandhu', name='DIC 2', code='BND-DIC-T2',
            center_type='DIC', district='Habiganj')
        self.brothel = ServiceCenter.objects.create(
            organisation='PHD', name='Brothel 1', code='PHD-BR-T1',
            center_type=ServiceCenter.BROTHEL, district='Rajbari')

    def _report(self, centre, improved=1, status='APPROVED', day=None):
        return BandhuActivityReport.objects.create(
            organisation='Bandhu', center=centre,
            report_date=day or self.today,
            wellness_centres_improved=improved, approval_status=status)

    def _bnd_1_8(self, start=None, end=None):
        return bandhu.compute_I_BND_1_8(
            'Bandhu', start or self.start, end or self.end)

    def test_idle_centres_count_zero(self):
        # Centres exist in config but nothing has been reported → 0.
        self.assertEqual(self._bnd_1_8(), 0)
        self.assertEqual(phd.compute_SL8('PHD', self.start, self.end), 0)

    def test_reported_centre_improvements_are_summed(self):
        self._report(self.dic1)
        self.assertEqual(self._bnd_1_8(), 1)
        # A second centre's report adds to the running total.
        self._report(self.dic2)
        self.assertEqual(self._bnd_1_8(), 2)

    def test_pending_activity_does_not_count(self):
        self._report(self.dic1, status='PENDING')
        self._report(self.dic2, status='MANAGER_APPROVED')  # stage 1 of 2 only
        self.assertEqual(self._bnd_1_8(), 0)

    def test_nil_report_does_not_make_centre_functional(self):
        NilReport.objects.create(
            organisation='Bandhu', center=self.dic1, report_date=self.today,
            reason='No clients today', approval_status='APPROVED')
        self.assertEqual(self._bnd_1_8(), 0)

    def test_service_activity_alone_no_longer_counts(self):
        # The pre-2026-11-12 definition counted any centre with approved
        # service activity. Under the tally definition it must not.
        OutreachSession.objects.create(
            organisation='Bandhu', center=self.dic1, session_date=self.today,
            peer_educator_name='PE', approval_status='APPROVED')
        self.assertEqual(self._bnd_1_8(), 0)

    def test_activity_outside_period_excluded(self):
        self._report(self.dic1)  # report_date = today
        past_start = self.today - datetime.timedelta(days=60)
        past_end = self.today - datetime.timedelta(days=30)
        self.assertEqual(self._bnd_1_8(past_start, past_end), 0)
