"""
Apply the PHD indicator remap confirmed in Activity.docx (2026-11-11):

- SL1: redefine to "Number of FSWs reached" (Mother List registry), so the
  upper headline card and the lower SL1 card agree. Target/unit unchanged
  (3,500 / FSWs).
- SL2 -> SL2.1: rename to "Number of GBV screenings conducted" (GBV SCREENING
  = Yes), unit changed survivors -> screenings (a screening count, not a
  distinct-survivor count). Target unchanged (100). SL2.2 ("cases mitigated")
  never existed as a row and is not created.
- SL3: redefine to "Number of group mental health counselling sessions"
  (TOTAL MENTAL HEALTH GROUP COUNSELLING (COUNT)). Unit FSWs -> sessions.
  Target unchanged (100). No separate 1,000-beneficiary field exists in the
  form (see completion report) so no second row is added for it.
- SL4: redefine to "Number of FSWs / clients reached through outreach
  sessions" (sum of NUMBER OF PARTICIPANTS). Unit sessions -> participants.
  Target 897 -> 3,595 (the reach target in Activity.docx).
- SL4a (new): "Number of outreach sessions conducted" — the session-count
  measure SL4 used to carry, moved here with its old target (897) so it is
  not lost.
- SL15a: target 99 -> 180 (Activity.docx "Done by them" confirmed total).
  SL15b/c and SL16 targets already matched (9/11/44) — left unchanged.
- SL5f label: drop the "/ STI" qualifier now that SL1 no longer shares the
  sti_screening_done field with it (SL1 moved to the registry definition),
  removing the ambiguity that comment used to flag.

Data-only migration; reversible.
"""
from django.db import migrations


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    service_log = KoboFormMapping.objects.filter(form_slug='phd_service_log_v1').first()

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL1').update(
        indicator_label='Number of FSWs reached',
    )

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL2').update(
        activity_code='SL2.1',
        indicator_label='Number of GBV screenings conducted',
        unit='screenings',
    )

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL3').update(
        indicator_label='Number of group mental health counselling sessions',
        unit='sessions',
    )

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL4').update(
        indicator_label='Number of FSWs / clients reached through outreach sessions',
        unit='participants',
        target_value=3595,
    )

    IndicatorTarget.objects.update_or_create(
        partner=phd, activity_code='SL4a',
        indicator_label='Number of outreach sessions conducted',
        defaults={
            'objective_number': 0,
            'activity_label': 'Conduct targeted outreach and health education',
            'target_value': 897,
            'unit': 'sessions',
            'source_form': service_log,
            'is_active': True,
        },
    )

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL15a').update(
        target_value=180,
    )

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL5f').update(
        indicator_label='Syphilis screenings performed (Patient Record)',
    )


def _reverse(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL1').update(
        indicator_label='Number of FSWs receiving HIV/STI screening and FP counselling',
    )

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL2.1').update(
        activity_code='SL2',
        indicator_label='Number of GBV survivors identified and referred for services',
        unit='survivors',
    )

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL3').update(
        indicator_label='Number of FSWs receiving mental health counselling sessions',
        unit='FSWs',
    )

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL4').update(
        indicator_label='Number of outreach sessions conducted and FSWs / clients reached',
        unit='sessions',
        target_value=897,
    )

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL4a').delete()

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL15a').update(
        target_value=99,
    )

    IndicatorTarget.objects.filter(partner=phd, activity_code='SL5f').update(
        indicator_label='Syphilis / STI screenings performed (Patient Record)',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0020_phd_sl5_unit_fix'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
