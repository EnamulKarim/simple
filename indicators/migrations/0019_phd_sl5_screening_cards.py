"""
Add 4 PHD "screenings performed" cards (SL5f-SL5i) alongside the existing
SL5b-SL5e commodity/stock rows.

SL5b-e are the SUPPLY rows (test kits issued, unit "boxes", from the Stock
form) and keep their boxes targets. SL5f-i are the SEPARATE "how many
screenings were actually performed" rows, read from the Patient Record
(clinic visit screening questions) by indicators.phd.compute_SL5f-i. They
sort immediately after SL5e (before SL6) and carry NO preset target
(target_value=NULL -> "Not Set" pill) so they never show a misleading
percentage until a screening target is entered in Target Config.

Data-only migration; reversible (removes the 4 rows).
"""
from django.db import migrations


SERVICE_LOG_SLUG = 'phd_service_log_v1'

SCREEN_ACTIVITY = (
    'Provide counselling, screening and management for HIV, syphilis, '
    'Hepatitis B & C and FP counselling'
)

# (activity_code, indicator_label, unit)
SCREENING_ROWS = [
    ('SL5f', 'Syphilis screenings performed (Patient Record)', 'screenings'),
    ('SL5g', 'Hepatitis B screenings performed (Patient Record)', 'screenings'),
    ('SL5h', 'Hepatitis C screenings performed (Patient Record)', 'screenings'),
    ('SL5i', 'HIV screenings performed (Patient Record)', 'screenings'),
]

NEW_CODES = [c for c, _, _ in SCREENING_ROWS]


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    service_log = KoboFormMapping.objects.filter(form_slug=SERVICE_LOG_SLUG).first()

    for code, label, unit in SCREENING_ROWS:
        IndicatorTarget.objects.update_or_create(
            partner=phd,
            activity_code=code,
            indicator_label=label,
            defaults={
                'objective_number': 0,
                'activity_label': SCREEN_ACTIVITY,
                'target_value': None,      # "Not Set" until a screening target is entered
                'unit': unit,
                'source_form': service_log,
                'is_active': True,
            },
        )


def _reverse(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return
    IndicatorTarget.objects.filter(partner=phd, activity_code__in=NEW_CODES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0018_bandhu_1_1_mother_list'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
