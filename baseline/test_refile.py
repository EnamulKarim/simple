"""Re-filing baseline responses stored under the wrong population (2026-11-17).

20 FSW interviews from 9 Jul were stored as Hijra before the 10 Jul
populations.py fix and never corrected. refile_misfiled_populations re-derives
each from its own submission.
"""
from django.test import TestCase

from baseline.models import BaselineResponse
from baseline.populations import FSW_ASSET, HIJRA_ASSET
from baseline.refile import refile_misfiled_populations
from baseline.test_approval import make_baseline_sub
from submissions.models import SubmissionStatus


def _row(asset, population, sid, **extra):
    """An approved submission (which materialises its response), then stored
    under `population` with `extra` overrides, the way the pre-10-Jul bug left it."""
    raw = {'_xform_id_string': asset, 'submission_id': sid, 'district': 'Dhaka'}
    sub = make_baseline_sub(raw, status=SubmissionStatus.APPROVED)
    r, _ = BaselineResponse.objects.get_or_create(
        submission=sub, defaults=dict(population=population, survey_round='baseline',
                                      partner='CIPRB', raw_data=raw))
    fields = dict(population=population, is_duplicate=False, duplicate_of=None)
    fields.update(extra)
    BaselineResponse.objects.filter(pk=r.pk).update(**fields)
    r.refresh_from_db()
    return r


class RefileMisfiledPopulationTest(TestCase):
    def test_fsw_interview_stored_as_hijra_is_refiled(self):
        r = _row(FSW_ASSET, 'hijra', 'S-1', serial='')  # the legacy corruption
        changed = refile_misfiled_populations(BaselineResponse)
        r.refresh_from_db()
        self.assertEqual(r.population, 'fsw')
        self.assertEqual(r.serial, 'S-1')               # re-derived, not just relabelled
        self.assertEqual(changed, [(r.pk, 'hijra', 'fsw')])

    def test_correct_rows_are_untouched_and_rerun_is_a_no_op(self):
        ok_h = _row(HIJRA_ASSET, 'hijra', 'H-1', serial='kept')
        ok_f = _row(FSW_ASSET, 'fsw', 'F-1', serial='kept')
        self.assertEqual(refile_misfiled_populations(BaselineResponse), [])
        for r in (ok_h, ok_f):
            r.refresh_from_db()
            self.assertEqual(r.serial, 'kept')          # not re-derived
        _row(FSW_ASSET, 'hijra', 'S-2')
        self.assertEqual(len(refile_misfiled_populations(BaselineResponse)), 1)
        self.assertEqual(refile_misfiled_populations(BaselineResponse), [])  # idempotent

    def test_duplicate_flag_is_recomputed_in_the_new_population(self):
        first = _row(FSW_ASSET, 'fsw', 'DUP')
        moved = _row(FSW_ASSET, 'hijra', 'DUP')
        refile_misfiled_populations(BaselineResponse)
        moved.refresh_from_db()
        self.assertTrue(moved.is_duplicate)
        self.assertEqual(moved.duplicate_of_id, first.pk)

    def test_stale_duplicate_link_to_a_moved_row_is_cleared(self):
        moved = _row(FSW_ASSET, 'hijra', 'X')
        left = _row(HIJRA_ASSET, 'hijra', 'X', is_duplicate=True)
        left.duplicate_of = moved
        left.save()
        refile_misfiled_populations(BaselineResponse)
        left.refresh_from_db()
        self.assertFalse(left.is_duplicate)
        self.assertIsNone(left.duplicate_of_id)

    def test_dry_run_reports_without_writing(self):
        r = _row(FSW_ASSET, 'hijra', 'S-9')
        self.assertEqual(len(refile_misfiled_populations(BaselineResponse, commit=False)), 1)
        r.refresh_from_db()
        self.assertEqual(r.population, 'hijra')
