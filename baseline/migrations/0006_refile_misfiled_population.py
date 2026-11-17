"""Re-file the 20 FSW interviews stored as Hijra before the 2026-07-10 fix.

See baseline/refile.py. Re-derives each mismatched row from its own submission;
rows that already agree are untouched, so this is safe to re-run. There is no
meaningful reverse (it would re-introduce the corruption), so reverse is a no-op.
"""
from django.db import migrations


def _forward(apps, schema_editor):
    from baseline.refile import refile_misfiled_populations
    BaselineResponse = apps.get_model('baseline', 'BaselineResponse')
    changed = refile_misfiled_populations(BaselineResponse)
    print(f'\n  baseline: re-filed {len(changed)} response(s) to the population '
          f'of the form they were submitted on')


class Migration(migrations.Migration):

    dependencies = [
        ('baseline', '0005_alter_anomalyreview_status'),
    ]

    operations = [
        migrations.RunPython(_forward, migrations.RunPython.noop),
    ]
