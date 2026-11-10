"""
Fix the SL5b-e unit mismatch, and make the SL5f label honest.

SL5b-e sum StockEntry.quantity_issued, and the PHD stock items are INDIVIDUAL
tests, not boxes: 'Syphilis Quick Test strip', 'HBsAg Test Cassette',
'HCV Test Cassette', 'Determine HIV1/2'. The rows nevertheless carried
unit='boxes' with box targets (140/176/176/40), so the cards rendered
individual strips against a box target and showed 474% / 431% / 365% / 883%.

Set unit='tests' (what the number actually is) and clear the box targets to
NULL ("Not Set"), because a box target is not comparable to a test count and
the tests-per-box factor is not recorded anywhere. A real tests target can be
entered in Target Config.

Also relabel SL5f: the form has no dedicated syphilis screening field, so
clinic_syphilis_screen is stored in ClinicVisit.sti_screening_done, the same
boolean SL1 reads. The label now says so instead of implying a syphilis-only
measure.

Data-only migration; reversible.
"""
from django.db import migrations


KIT_CODES = ['SL5b', 'SL5c', 'SL5d', 'SL5e']

# code -> (old_unit, old_target) for the reverse.
OLD_KIT_TARGETS = {
    'SL5b': 140,
    'SL5c': 176,
    'SL5d': 176,
    'SL5e': 40,
}

SL5F_OLD = 'Syphilis screenings performed (Patient Record)'
SL5F_NEW = 'Syphilis / STI screenings performed (Patient Record)'


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    IndicatorTarget.objects.filter(
        partner=phd, activity_code__in=KIT_CODES,
    ).update(unit='tests', target_value=None)

    IndicatorTarget.objects.filter(
        partner=phd, activity_code='SL5f',
    ).update(indicator_label=SL5F_NEW)


def _reverse(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    for code, target in OLD_KIT_TARGETS.items():
        IndicatorTarget.objects.filter(
            partner=phd, activity_code=code,
        ).update(unit='boxes', target_value=target)

    IndicatorTarget.objects.filter(
        partner=phd, activity_code='SL5f',
    ).update(indicator_label=SL5F_OLD)


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0019_phd_sl5_screening_cards'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
