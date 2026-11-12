"""
Set the SL5f-i ("screenings performed") targets to 3,500 each, per the PHD
master indicator table (2026-11-12): every one of the four screening types
carries the same 3,500 target as SL1 ("FSW reach") — i.e. PHD's goal is to
screen everyone reached for syphilis, Hep B, Hep C and HIV.

These rows were deliberately left target_value=NULL ("Not Set") in migration
0019/0020 because no target had been confirmed at the time. It now has been.

SL4a is NOT touched here: production already shows target=719 (matching this
same table's "719 group sessions [5 person/group]" figure), having already
been corrected via Target Config since the last deploy — no gap there.

Data-only migration; reversible.
"""
from django.db import migrations


CODES = ['SL5f', 'SL5g', 'SL5h', 'SL5i']


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    IndicatorTarget.objects.filter(
        partner=phd, activity_code__in=CODES,
    ).update(target_value=3500)


def _reverse(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    IndicatorTarget.objects.filter(
        partner=phd, activity_code__in=CODES,
    ).update(target_value=None)


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0022_phd_remove_sl5_stock_kit_cards'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
