"""
Remove the SL5b-e "Screening Kits" (stock) cards from the PHD dashboard
entirely, per user request (2026-11-11).

These were the commodity/stock measure (StockEntry.quantity_issued, unit
"boxes"/"tests") kept alongside the SL5f-i "screenings performed" cards after
the 2026-11-10 fix. The user now wants the stock-kit cards gone from the
grid outright, leaving only SL5f-i (screenings performed).

Deactivated (is_active=False), not deleted: this hides them from every
indicator feed (get_partner_indicator_progress filters is_active=True) while
preserving the row and its history. Reversible.
"""
from django.db import migrations


CODES = ['SL5b', 'SL5c', 'SL5d', 'SL5e']


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    IndicatorTarget.objects.filter(
        partner=phd, activity_code__in=CODES,
    ).update(is_active=False)


def _reverse(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    IndicatorTarget.objects.filter(
        partner=phd, activity_code__in=CODES,
    ).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0021_phd_activity_docx_remap'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
