import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("programs", "0027_widen_wellness_tg_code"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BandhuActivityReport",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "kobo_submission_id",
                    models.CharField(
                        blank=True, max_length=100, null=True, unique=True
                    ),
                ),
                (
                    "approval_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("MANAGER_APPROVED", "Manager approved — awaiting UNFPA"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("manager_approved_at", models.DateTimeField(blank=True, null=True)),
                ("rejected_reason", models.TextField(blank=True)),
                (
                    "latitude",
                    models.DecimalField(
                        blank=True, decimal_places=6, max_digits=9, null=True
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        blank=True, decimal_places=6, max_digits=9, null=True
                    ),
                ),
                (
                    "submitted_by_kobo_user",
                    models.CharField(blank=True, max_length=100),
                ),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("organisation", models.CharField(db_index=True, max_length=20)),
                ("report_date", models.DateField(db_index=True)),
                ("reporter_name", models.CharField(blank=True, max_length=200)),
                ("new_mother_list", models.PositiveIntegerField(default=0)),
                ("outreach_sessions", models.PositiveIntegerField(default=0)),
                ("outreach_participants", models.PositiveIntegerField(default=0)),
                ("supported_clinics", models.PositiveIntegerField(default=0)),
                ("wellness_centres_improved", models.PositiveIntegerField(default=0)),
                ("mobile_health_camps", models.PositiveIntegerField(default=0)),
                ("mobile_camp_participants", models.PositiveIntegerField(default=0)),
                ("mh_counseling_sessions", models.PositiveIntegerField(default=0)),
                ("mh_participants", models.PositiveIntegerField(default=0)),
                ("orientation_sessions", models.PositiveIntegerField(default=0)),
                ("orientation_participants", models.PositiveIntegerField(default=0)),
                ("midwife_training_sessions", models.PositiveIntegerField(default=0)),
                ("midwife_trainees", models.PositiveIntegerField(default=0)),
                ("gov_ngo_meetings", models.PositiveIntegerField(default=0)),
                ("gov_ngo_participants", models.PositiveIntegerField(default=0)),
                ("cbo_meetings", models.PositiveIntegerField(default=0)),
                ("cbo_participants", models.PositiveIntegerField(default=0)),
                ("peer_educator_trainings", models.PositiveIntegerField(default=0)),
                ("peer_educator_participants", models.PositiveIntegerField(default=0)),
                ("observance_event_count", models.PositiveIntegerField(default=0)),
                ("observance_participants", models.PositiveIntegerField(default=0)),
                ("iec_sbcc_distributed", models.PositiveIntegerField(default=0)),
                (
                    "messaging_displays_installed",
                    models.PositiveIntegerField(default=0),
                ),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "center",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bandhu_activity_reports",
                        to="programs.servicecenter",
                    ),
                ),
                (
                    "manager_approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Bandhu activity & operations report",
            },
        ),
    ]
