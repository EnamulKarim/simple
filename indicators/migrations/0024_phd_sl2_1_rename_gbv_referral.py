"""
Rename PHD SL2.1 from "Number of GBV screenings conducted" to
"Number of GBV Referral" (Rafi, 2026-11-15).

The compute function was already repointed to the GBV REFERRAL tick
(clinic_ref_gbv -> ClinicVisit.referral_gbv) in indicators/phd.py; this
migration only updates the stored label and unit so the dashboard card and the
indicator tables read "Number of GBV Referral ... / <target> referrals". Target
value is unchanged.

Data-only migration; reversible.
"""
from django.db import migrations


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL2.1').update(
        indicator_label='Number of GBV Referral',
        unit='referrals',
    )


def _reverse(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL2.1').update(
        indicator_label='Number of GBV screenings conducted',
        unit='screenings',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0023_phd_sl5fi_targets'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
