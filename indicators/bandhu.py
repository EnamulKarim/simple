"""
Bandhu (SOGIEC) indicator compute functions.
All filter on approval_status='APPROVED' only.
Period args: period_start, period_end are date objects.
"""
from django.db.models import Sum
from programs.models import (
    Referral, WellnessLogbookEntry, BandhuActivityReport,
)


def _logbook(org, period_start, period_end):
    """APPROVED F-01 logbook rows in the period — the canonical Bandhu service
    source. Bandhu files no F-05/F-06, so counting these plus the (near-empty)
    specific-form models is a single source, not a double-count."""
    return WellnessLogbookEntry.objects.filter(
        organisation=org, approval_status=APPROVED,
        service_date__range=(period_start, period_end),
    )


ORG = 'Bandhu'
APPROVED = 'APPROVED'


def _rsum(org, period_start, period_end, field):
    """Sum a field across APPROVED Bandhu Activity & Operations reports in the
    period. The live Activity form is an aggregate per-centre tally, so each
    activity indicator is the sum of its reported number (Rafi 2026-11-12)."""
    return BandhuActivityReport.objects.filter(
        organisation=org, approval_status=APPROVED,
        report_date__range=(period_start, period_end),
    ).aggregate(t=Sum(field))['t'] or 0


def _distinct_persons(qs):
    """Count DISTINCT beneficiaries in a logbook queryset, never visits.

    A person is their normalised DD-NNNN id, falling back to the raw id when the
    norm is blank (ids compared trimmed + upper-cased). Rafi 2026-11-17: no
    person may be counted twice in any Bandhu person indicator; repeat visits
    and duplicate submissions of the same visit collapse to one person."""
    ids = set()
    for norm, raw in qs.values_list('client_id_norm', 'client_id'):
        pid = (norm or raw or '').strip().upper()
        if pid:
            ids.add(pid)
    return len(ids)


def compute_I_BND_1_1(org, period_start, period_end):
    """KP individuals reached — distinct beneficiaries served in the Beneficiary
    Service Log. Target: 4,000.

    Rafi's M&E decision (2026-11-12): 'KP reached' is now measured by the
    DISTINCT persons appearing in the Beneficiary Service Log
    (bandhu_service_log_v1), NOT the Mother List registration count. The
    canonical per-client row the Service Log always writes is the F-01
    WellnessLogbookEntry (programs/bandhu_handlers.py _bnd_logbook), which stamps
    each served beneficiary's normalised id. So distinct reached = distinct
    normalised client id on APPROVED logbook rows in the period, falling back to
    the raw id where the norm is blank. Cumulative = all distinct served;
    monthly = distinct served that month. The Mother List registry (Client) is
    retained but no longer drives 1.1."""
    return _distinct_persons(_logbook(org, period_start, period_end))


def compute_I_BND_1_2(org, period_start, period_end):
    """GBV survivors screened and referred. Target: 120 survivors (MIS doc).

    SINGLE SOURCE — the F-01 logbook gbv tick. Bandhu records GBV only in the
    logbook (the F-02 record type is removed from the Bandhu Service Log), so the
    logbook is counted alone — never summed with GBVCase — to guarantee no
    double-count if a stray/legacy F-02 row ever coexists. Counts DISTINCT
    persons (2026-11-17), not visits."""
    return _distinct_persons(_logbook(org, period_start, period_end).filter(gbv=True))


def compute_I_BND_1_3(org, period_start, period_end):
    """Individuals receiving MHPSS counselling. Target: 48 persons (MIS doc).

    M2: counts ONLY IndividualCounselling(issue_psychosocial=True) — the F-03
    Mental Health Counseling tool is the single canonical source. The previous
    GroupEducationSession(topic~'mental') term was dead weight (no Bandhu
    handler writes GroupEducationSession) that could inflate 1.3 if a generic
    group-ed row ever landed under org=Bandhu, so it is removed."""
    # SINGLE SOURCE — the F-01 logbook mental_health tick (F-03 record type is
    # removed from the Bandhu Service Log), counted alone to avoid any double-count.
    # DISTINCT persons (2026-11-17): target unit is persons, not sessions.
    return _distinct_persons(_logbook(org, period_start, period_end).filter(mental_health=True))


def compute_I_BND_1_4A(org, period_start, period_end):
    """Outreach + health-education sessions conducted. Target: 288 (MIS doc).
    Sum of the Activity report `outreach_sessions` tally."""
    return _rsum(org, period_start, period_end, 'outreach_sessions')


# NOTE: indicator 1.4b ("KP reached via outreach", 4,000) was retired per the
# framework review — it duplicated 1.1 (KP receiving services, also 4,000).
# Only 1.4a (outreach sessions conducted) remains for the outreach activity.


def compute_I_BND_1_5_hiv(org, period_start, period_end):
    """KP receiving HIV testing services. Target: 2,000 (MIS doc, code 1.5b).

    Counts EVERY HTC Service Register (F-06) row as one HIV test received —
    there is NO hiv_result gate, so records with any result (or no result yet)
    are all counted as a testing-service delivered. M4: this is the M&E
    framework's definition of "received HIV testing services" and is a
    DEFINITION choice for UNFPA to confirm, not a bug — do not add a result
    filter without their sign-off."""
    # SINGLE SOURCE — the F-01 logbook htc tick (F-06 record type is removed from
    # the Bandhu Service Log), counted alone to avoid any double-count.
    # DISTINCT persons (Rafi 2026-11-17): "KP receiving HIV testing" counts
    # people; a person tested on two visits is one KP, not two.
    return _distinct_persons(_logbook(org, period_start, period_end).filter(htc=True))


def compute_I_BND_1_5_sti(org, period_start, period_end):
    """KP receiving STI services. Target: 2,000 (MIS doc, code 1.5a).

    Counts clinic visits where STI screening was done (Patient Record Register
    F-05, sti_screening_done=True). M3: sti_screening_done is used as the proxy
    for "received STI services" — this is a DEFINITION choice for UNFPA to
    confirm (screening vs treatment/case), not a bug. Do not narrow to
    STI-case/treatment fields without their sign-off."""
    # SINGLE SOURCE — the F-01 logbook sti_screening tick (F-05 record type is
    # removed from the Bandhu Service Log), counted alone to avoid any double-count.
    # DISTINCT persons (Rafi 2026-11-17): "KP receiving STI services" counts
    # people; repeat visits by the same person collapse to one.
    return _distinct_persons(_logbook(org, period_start, period_end).filter(sti_screening=True))


def compute_I_BND_1_6(org, period_start, period_end):
    """KP clinics supported with logistics/supplies/maintenance. Target: 1.
    Sum of the Activity report `supported_clinics` tally (Rafi 2026-11-12)."""
    return _rsum(org, period_start, period_end, 'supported_clinics')


def compute_I_BND_1_7(org, period_start, period_end):
    """KP referred and linked to ART/treatment. Target: 25 (MIS doc)."""
    return Referral.objects.filter(
        organisation=org, approval_status=APPROVED,
        referral_date__range=(period_start, period_end),
        referral_type__in=['art', 'hiv', 'sti_kp'],
        outcome='completed',
    ).values('client').distinct().count()


def compute_I_BND_1_8(org, period_start, period_end):
    """Community-friendly drop-in centres established/strengthened. Target: 8.
    Sum of the Activity report `wellness_centres_improved` tally (Rafi 2026-11-12)."""
    return _rsum(org, period_start, period_end, 'wellness_centres_improved')


def compute_I_BND_1_9(org, period_start, period_end):
    """Mobile outreach health camps conducted. Target: 40 camps (MIS doc).
    Sum of the Activity report `mobile_health_camps` tally."""
    return _rsum(org, period_start, period_end, 'mobile_health_camps')


def compute_I_BND_2_1(org, period_start, period_end):
    """Gov health managers/supervisors oriented. Target: 192.
    Sum of the Activity report `orientation_participants` tally."""
    return _rsum(org, period_start, period_end, 'orientation_participants')


def compute_I_BND_2_2(org, period_start, period_end):
    """Midwives/frontline providers trained. Target: 192.
    Sum of the Activity report `midwife_trainees` tally."""
    return _rsum(org, period_start, period_end, 'midwife_trainees')


def compute_I_BND_2_3(org, period_start, period_end):
    """GOB/midwife/NGO coordination meetings. Target: 16.
    Sum of the Activity report `gov_ngo_meetings` tally."""
    return _rsum(org, period_start, period_end, 'gov_ngo_meetings')


def compute_I_BND_2_4(org, period_start, period_end):
    """CBO/community-network coordination meetings. Target: 16.
    Sum of the Activity report `cbo_meetings` tally."""
    return _rsum(org, period_start, period_end, 'cbo_meetings')


def compute_I_BND_2_5(org, period_start, period_end):
    """Community leaders/peer educators trained. Target: 160.
    Sum of the Activity report `peer_educator_participants` tally."""
    return _rsum(org, period_start, period_end, 'peer_educator_participants')


def compute_I_BND_2_6(org, period_start, period_end):
    """National/international observance events supported. Target: 2.
    Sum of the Activity report `observance_event_count` tally."""
    return _rsum(org, period_start, period_end, 'observance_event_count')


def compute_I_BND_4_1(org, period_start, period_end):
    """IEC/SBCC materials disseminated. Target: 16,800.
    Sum of the Activity report `iec_sbcc_distributed` tally (Rafi 2026-11-12:
    the Activity form's dedicated SBCC field; the Service Log's per-person IEC
    is stored but not summed here, to avoid a double-count)."""
    return _rsum(org, period_start, period_end, 'iec_sbcc_distributed')


def compute_I_BND_4_2(org, period_start, period_end):
    """Public messaging displays installed. Target: 56.
    Sum of the Activity report `messaging_displays_installed` tally."""
    return _rsum(org, period_start, period_end, 'messaging_displays_installed')


# ─── Activity-code registry ──────────────────────────────────────────────────
#
# Maps the canonical `activity_code` from IndicatorTarget rows (set by data
# migration 0004_load_target_fixtures) to the compute function above.
#
# Codes absent from this registry are treated as UNLINKED by the service
# layer — the row still renders on the org page with achievement=0 and a
# small "module not built yet" badge, never a crash.
#
# Sources (Rafi 2026-11-12): 1.1-1.3 and 1.5a/b read APPROVED F-01 logbook
# rows; 1.7 reads Referral; every other code sums a BandhuActivityReport tally
# over APPROVED reports (_rsum).

ACTIVITY_REGISTRY = {
    '1.1':  compute_I_BND_1_1,
    '1.2':  compute_I_BND_1_2,
    '1.3':  compute_I_BND_1_3,
    '1.4a': compute_I_BND_1_4A,
    '1.5a': compute_I_BND_1_5_sti,      # STI services (clinic)
    '1.5b': compute_I_BND_1_5_hiv,      # HIV testing (HTC register)
    '1.6':  compute_I_BND_1_6,          # Activity report supported_clinics
    '1.7':  compute_I_BND_1_7,
    '1.8':  compute_I_BND_1_8,          # Activity report wellness_centres_improved
    '1.9':  compute_I_BND_1_9,
    '2.1':  compute_I_BND_2_1,
    '2.2':  compute_I_BND_2_2,
    '2.3':  compute_I_BND_2_3,
    '2.4':  compute_I_BND_2_4,
    '2.5':  compute_I_BND_2_5,
    '2.6':  compute_I_BND_2_6,
    '4.1':  compute_I_BND_4_1,
    '4.2':  compute_I_BND_4_2,
}

# Codes whose compute function takes only (org) — no period args.
ORG_ONLY_CODES = set()  # every Bandhu code is period-aware
