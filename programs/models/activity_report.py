"""Bandhu Activity & Operations — aggregate periodic report.

The live Activity & Operations form (bandhu_activity_ops_v1, enketo 0FkX1AXb) is
an AGGREGATE tally: one submission = one centre's counts for a reporting period
(outreach sessions, camps, trainings, meetings, IEC, displays, ...). Unlike the
per-event programs models, this stores the reported numbers verbatim; the Bandhu
activity indicators SUM these fields over APPROVED reports in the period (see
indicators/bandhu.py). Goes through the two-stage approval flow (PENDING by
SubmissionBase default → Bandhu manager → UNFPA).
"""
from django.db import models

from ._base import SubmissionBase


class BandhuActivityReport(SubmissionBase):
    organisation = models.CharField(max_length=20, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT,
        related_name='bandhu_activity_reports',
    )
    report_date = models.DateField(db_index=True)
    reporter_name = models.CharField(max_length=200, blank=True)

    # Objective 1 — service reach / outreach
    new_mother_list = models.PositiveIntegerField(default=0)
    outreach_sessions = models.PositiveIntegerField(default=0)
    outreach_participants = models.PositiveIntegerField(default=0)
    supported_clinics = models.PositiveIntegerField(default=0)
    wellness_centres_improved = models.PositiveIntegerField(default=0)
    mobile_health_camps = models.PositiveIntegerField(default=0)
    mobile_camp_participants = models.PositiveIntegerField(default=0)
    mh_counseling_sessions = models.PositiveIntegerField(default=0)
    mh_participants = models.PositiveIntegerField(default=0)

    # Objective 2 — capacity building
    orientation_sessions = models.PositiveIntegerField(default=0)
    orientation_participants = models.PositiveIntegerField(default=0)
    midwife_training_sessions = models.PositiveIntegerField(default=0)
    midwife_trainees = models.PositiveIntegerField(default=0)
    gov_ngo_meetings = models.PositiveIntegerField(default=0)
    gov_ngo_participants = models.PositiveIntegerField(default=0)
    cbo_meetings = models.PositiveIntegerField(default=0)
    cbo_participants = models.PositiveIntegerField(default=0)
    peer_educator_trainings = models.PositiveIntegerField(default=0)
    peer_educator_participants = models.PositiveIntegerField(default=0)
    observance_event_count = models.PositiveIntegerField(default=0)
    observance_participants = models.PositiveIntegerField(default=0)

    # Objective 4 — SBCC / IEC
    iec_sbcc_distributed = models.PositiveIntegerField(default=0)
    messaging_displays_installed = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Bandhu activity & operations report'

    def __str__(self):
        return f'Bandhu activity report {self.report_date} ({self.center_id})'
