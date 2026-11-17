"""Columns that real CIPRB Kobo values overflowed (2026-11-17).

SQLite (the test DB) does not enforce varchar length, so a plain save would pass
even on the old 100/200 limits. These tests use Django field validation, which
does fail on the old limits, plus the handler round-trip for the campaign form.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase

from fistula.ciprb_models import CIPRBFistulaCase
from fistula.models import FistulaCampaign, FistulaCampaignVisit, FistulaCornerCase

# The real worst case: a CHW ticked many unions -> 176 chars of space-joined codes.
LONG_UNION = ' '.join('union_code_%02d' % i for i in range(12))   # 167 chars


def _valid(model, **values):
    obj = model(**values)
    others = [f.name for f in model._meta.fields if f.name not in values]
    obj.clean_fields(exclude=others)


class FistulaFieldWidthTest(TestCase):
    def test_long_multi_union_fits_every_union_column(self):
        self.assertGreater(len(LONG_UNION), 100)
        for model in (FistulaCampaign, FistulaCampaignVisit, FistulaCornerCase, CIPRBFistulaCase):
            try:
                _valid(model, union=LONG_UNION)
            except ValidationError as e:
                self.fail(f'{model.__name__}.union rejects {len(LONG_UNION)} chars: {e}')

    def test_long_free_text_fits_fistula_case(self):
        _valid(CIPRBFistulaCase, current_condition='x' * 253,
               delivery_complication='y' * 307,
               time_duration_fistula_occurrence='z' * 150)

    def test_campaign_handler_saves_long_union(self):
        from fistula.tests import _daily_campaign_payload
        from fistula.webhook_handlers import handle_ciprb_fistula_campaign
        payload = _daily_campaign_payload()
        payload['union'] = LONG_UNION
        resp = handle_ciprb_fistula_campaign(payload, lat=23.75, lng=90.38)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(FistulaCampaign.objects.get().union, LONG_UNION)
