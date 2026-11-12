"""Widen WellnessLogbookEntry.tg_code 10 -> 50.

The live Beneficiary Service Log pulldata can emit a free-text TG value such as
'Source gender code 1 (unmapped)' (31 chars) into tg_code, which overflowed
varchar(10) and 500'd the submission. tg_code is display-only (no indicator
reads it), so widening is safe. Mirrors the earlier occupation_code fix.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('programs', '0026_stockentry_source_submission_ids'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wellnesslogbookentry',
            name='tg_code',
            field=models.CharField(blank=True, max_length=50),
        ),
    ]
