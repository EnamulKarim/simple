"""
Rename/redefine PHD SL6 to "Number of STI Referral" (Rafi, 2026-11-15).

SL6 was "Number of HIV/STI positive cases successfully referred and enrolled in
treatment", read from the free-text Referral Register as distinct positive
clients. It is now the single "STI referral" count read from the Patient Record
form (o7GhleIk) referral ticks: STI-confirmatory (covers HIV / syphilis / hep B
/ hep C) OR STI-non-responsive / complicated. The compute change is in
indicators/phd.py; this migration only updates the stored label and unit so the
card reads "Number of STI Referral ... / 135 referrals". Target value unchanged.

Data-only migration; reversible.
"""
from django.db import migrations


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL6').update(
        indicator_label='Number of STI Referral',
        unit='referrals',
    )


def _reverse(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL6').update(
        indicator_label=(
            'Number of HIV/STI positive cases successfully referred and '
            'enrolled in treatment'
        ),
        unit='cases',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0024_phd_sl2_1_rename_gbv_referral'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
