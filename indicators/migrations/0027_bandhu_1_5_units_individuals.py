"""
Bandhu 1.5a / 1.5b now count DISTINCT persons, so their unit becomes individuals.

Rafi's decision (2026-11-17): no person may be counted twice in any Bandhu person
indicator. 1.5a "KP receiving STI services" and 1.5b "KP receiving HIV testing
services" previously counted logbook ROWS, so a person seen on two visits was
counted twice (prod: STI 204 rows = 185 persons, HIV 201 rows = 181 persons).
indicators/bandhu.py now counts distinct persons; the stored units ("services",
"tests") are updated to match so the card reads "/ 2,000 individuals".
Targets and monthly splits are unchanged.
"""
from django.db import migrations

NEW_UNIT = {'1.5a': 'individuals', '1.5b': 'individuals'}
OLD_UNIT = {'1.5a': 'services', '1.5b': 'tests'}


def _apply(apps, units):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')
    bandhu = Partner.objects.filter(code='Bandhu').first()
    if bandhu is None:
        return
    for code, unit in units.items():
        IndicatorTarget.objects.filter(partner=bandhu, activity_code=code).update(unit=unit)


def _forward(apps, schema_editor):
    _apply(apps, NEW_UNIT)


def _reverse(apps, schema_editor):
    _apply(apps, OLD_UNIT)


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0026_bandhu_1_1_label_fix'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
