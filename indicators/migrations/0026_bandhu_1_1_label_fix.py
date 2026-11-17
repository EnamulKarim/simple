"""
Bandhu 1.1 label corrected to match the live computation.

Migration 0018 set the 1.1 labels to "Mother List registry" when "KP reached"
was briefly defined as the registration count. Rafi's M&E decision (2026-11-12,
indicators/bandhu.py:compute_I_BND_1_1) changed 1.1 back to the DISTINCT persons
served in the F-01 Beneficiary Service Log, NOT the Mother List registration
count. The stored labels were never updated, so the card read
"KP individuals reached (Mother List registry)" while the number was the
service-log distinct-served figure (e.g. 30), making it look like data loss
against the 3,253 registrations. This aligns the labels with the computation.
Target (4,000) and the monthly split are unchanged.
"""
from django.db import migrations


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner         = apps.get_model('partners', 'Partner')

    bandhu = Partner.objects.filter(code='Bandhu').first()
    if bandhu is None:
        return

    IndicatorTarget.objects.filter(partner=bandhu, activity_code='1.1').update(
        activity_label='Reach key-population individuals through the Beneficiary Service Log (F-01)',
        indicator_label='KP individuals reached (distinct served, F-01 service log)',
    )


def _reverse(apps, schema_editor):
    """Restore the labels set by 0018 (Mother List wording)."""
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner         = apps.get_model('partners', 'Partner')
    bandhu = Partner.objects.filter(code='Bandhu').first()
    if bandhu is None:
        return
    IndicatorTarget.objects.filter(partner=bandhu, activity_code='1.1').update(
        activity_label='Enrol key-population individuals into the Mother List registry',
        indicator_label='KP individuals reached (Mother List registry)',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0025_phd_sl6_rename_sti_referral'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
