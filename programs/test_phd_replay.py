"""backfill_phd: status-code classification, idempotent skip, commit/rollback.

The hermetic tests patch ``phd_assets`` and ``_fetch`` and inject a fake handler
into ``FORM_HANDLERS``, so the persist-on-2xx / roll-back-on-4xx-5xx-or-dry-run
behaviour and the created/skipped/bad/error classification are tested without a
token or network. A separate live-Kobo smoke test (skipped without KOBO_TOKEN)
dry-runs the real PHD forms and fails if any handler crashes — the recovery
analogue of test_ciprb_replay.
"""
import os
import unittest
from unittest import mock

from django.http import HttpResponse
from django.test import TestCase

from programs import phd_replay
from programs.webhook import FORM_HANDLERS
from programs.models import ServiceCenter

TEST_SLUG = 'phd_service_log_v1'   # a real phd_* key so the slug filter passes
TEST_FORM = 'PHD 2 — Service Log'


def _subs(*outcomes):
    """Fake Kobo results: each carries an _id (the dedup key) and an outcome
    the fake handler reads."""
    return [{'_id': i, 'outcome': o} for i, o in enumerate(outcomes)]


class BackfillPhdLogicTest(TestCase):
    def _run(self, handler, subs, **kw):
        with mock.patch.object(phd_replay, 'phd_assets',
                               return_value=[('aUID', TEST_FORM, TEST_SLUG)]), \
             mock.patch.object(phd_replay, '_fetch', return_value=subs), \
             mock.patch.dict(FORM_HANDLERS, {TEST_SLUG: handler}):
            return phd_replay.backfill_phd('tok', **kw)

    def test_classifies_created_skipped_bad_and_errors(self):
        # Arrange — one handler that maps an outcome to a response (or a crash)
        def handler(payload, lat, lng):
            o = payload['outcome']
            if o == 'raise':
                raise ValueError('boom')
            return HttpResponse(status={'created': 201, 'skip': 200,
                                        'bad': 400, 'err': 500}[o])

        # Act
        rec = self._run(handler, _subs(
            'created', 'created', 'skip', 'bad', 'err', 'raise'))[TEST_FORM]

        # Assert — 201->created, 200->skipped(idempotent no-op), 400->bad,
        # 500 and crash both land in errors
        self.assertEqual(rec['n'], 6)
        self.assertEqual(rec['created'], 2)
        self.assertEqual(rec['skipped'], 1)
        self.assertEqual(rec['bad'], 1)
        self.assertEqual(len(rec['errors']), 2)

    def test_live_commits_but_dry_run_rolls_back(self):
        # Handler writes a real row (side effect) then reports 201 Created
        def handler(payload, lat, lng):
            ServiceCenter.objects.create(
                organisation='PHD', name='T', code='C-%s' % payload['_id'],
                center_type='brothel', district='D')
            return HttpResponse(status=201)

        before = ServiceCenter.objects.count()

        # dry run — classified as created, but the savepoint is rolled back
        rec = self._run(handler, _subs('x', 'x'), dry_run=True)[TEST_FORM]
        self.assertEqual(rec['created'], 2)
        self.assertEqual(ServiceCenter.objects.count(), before)

        # live run — the same payloads now persist
        rec = self._run(handler, _subs('x', 'x'))[TEST_FORM]
        self.assertEqual(rec['created'], 2)
        self.assertEqual(ServiceCenter.objects.count(), before + 2)

    def test_slug_filter_excludes_unrequested_forms(self):
        def handler(payload, lat, lng):
            return HttpResponse(status=201)
        # The resolved asset is phd_service_log_v1; ask only for registration ->
        # nothing is processed.
        out = self._run(handler, _subs('x'), slugs=['phd_registration_v1'])
        self.assertEqual(out, {})


@unittest.skipUnless(os.environ.get('KOBO_TOKEN'),
                     'KOBO_TOKEN not set — run with `railway run` to hit live Kobo')
class BackfillPhdLiveTest(TestCase):
    def test_dry_run_has_no_handler_crashes_on_live_phd(self):
        from django.db import transaction
        res = phd_replay.backfill_phd(os.environ['KOBO_TOKEN'], dry_run=True)
        transaction.set_rollback(True)
        crashed = ['%s [%s]: %s' % (name, e['id'], e['error'])
                   for name, rec in res.items() for e in rec['errors']]
        summary = '  '.join(
            '%s n=%d created=%d skipped=%d' % (
                name, rec['n'], rec['created'], rec['skipped'])
            for name, rec in res.items())
        self.assertEqual(crashed, [],
                         'handler crashed on live PHD data:\n' + '\n'.join(crashed)
                         + '\n\nsummary: ' + summary)
