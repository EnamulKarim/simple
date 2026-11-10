"""
PHD indicator compute functions — SL1 through SL16, directly from
PHD_SIDA_Activities_Indicators_Output_Outcome.docx.

All counts are over APPROVED submissions only. Data comes from the
3 consolidated PHD forms via the new phd_handlers.py:

  phd_registration_v1      → Client
  phd_patient_services_v1  → ClinicVisit, HIVSTITestResult, Referral
  phd_activity_ops_v1      → GroupEducationSession, TrainingEvent,
                             IECMaterial, StockEntry, GBVCornerRecord
"""
from django.db.models import Q, Sum

from programs.models import (
    Client, ClinicVisit, Referral,
    GroupEducationSession,
    ServiceCenter, TrainingEvent, StockEntry, IECMaterial,
    GBVCornerRecord, PHDCounsellingReport,
)
from ._centers import active_center_ids

APPROVED = 'APPROVED'


# ── SL1R — FSWs reached (Mother List registry) ───────────────────────────────
# The PHD "FSWs reached" HEADLINE metric, measured the same way as Bandhu 1.1
# (Rafi's M&E decision 2026-07-01: "reached" = the Mother List registry, the
# register of individuals the programme has enrolled). This is distinct from
# SL1 below, which is the narrower SIDA service indicator (FSWs who actually
# received HIV/STI screening). SL1R intentionally has NO IndicatorTarget row and
# is served only to the PHD headline card via get_phd_registry_kpi() — so it
# never enters the SIDA framework table or the indicator roll-ups.
def compute_SL1R(org, period_start, period_end):
    """Distinct registered, APPROVED, non-stub PHD clients by registration date
    (Client.created_at). Cumulative = the whole registry over the programme
    period; monthly = new registrations that month. Stubs (name ''/'Unknown',
    created by a service log citing an unregistered ID) are excluded, mirroring
    the client lookup-CSV exporter and Bandhu 1.1."""
    return (
        Client.objects.filter(
            organisation=org, approval_status=APPROVED,
            created_at__date__range=(period_start, period_end),
        )
        .exclude(name='').exclude(name='Unknown')
        .values('client_id').distinct().count()
    )


# ── SL1 — FSWs receiving HIV/STI screening and FP counselling ────────────────
def compute_SL1(org, period_start, period_end):
    return ClinicVisit.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        visit_date__range=(period_start, period_end),
    ).filter(
        Q(hiv_screening_done=True) | Q(sti_screening_done=True)
    ).values('client_id').distinct().count()


# ── SL2 — GBV survivors identified and referred for services ─────────────────
def compute_SL2(org, period_start, period_end):
    # Sourced from the REFERRAL register (the form's "referred for" field), per the
    # client Indicators->Kobo map. NOT the Patient Record GBV tick: field staff log
    # GBV referrals in the Referral section, so in production (2026-11) the clinic
    # referral_gbv tick carried only 1 case while the Referral register carried 5
    # (referral_reason ~ "GBV"). Count distinct survivors referred for GBV.
    return Referral.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        referral_date__range=(period_start, period_end),
    ).filter(
        Q(referral_reason__icontains='gbv')
        | Q(referral_reason__icontains='gender based')
        | Q(referral_reason__icontains='gender-based')
    ).values('client_id').distinct().count()


# ── SL3 — FSWs receiving mental health counselling sessions ──────────────────
def compute_SL3(org, period_start, period_end):
    # "Receiving MH counselling sessions" comes from the PHD monthly Counselling
    # Report (PHDCounsellingReport.mh_count — individual MH counselling), NOT the
    # ClinicVisit mh_screening tick. mh_screening_done is routine on ~97% of
    # visits, which inflated this to ~all screened FSWs (verified 2 Nov 2026:
    # 2309 screened, 0 MH diagnoses). Sum the reported counts over the period.
    return PHDCounsellingReport.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        report_date__range=(period_start, period_end),
    ).aggregate(t=Sum('mh_count'))['t'] or 0


# ── SL4 — Outreach sessions conducted ────────────────────────────────────────
def compute_SL4(org, period_start, period_end):
    return GroupEducationSession.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        session_date__range=(period_start, period_end),
    ).count()


# ── SL5 — Essential SRHR & GBV supplies (5 commodity sub-rows) ───────────────
# StockEntry.item_name is operator-entered FREE TEXT with dozens of spelling
# variants ("HBsAg", "HbsAG", "HBSag Tast kit", "Hepatitis B kits", ...) and the
# item_category dropdown is unused — every PHD row is category 'Other'. So the
# only reliable classifier is a case-insensitive match on name fragments. Each
# commodity maps to a TUPLE of fragments (OR'd); the fragment sets are mutually
# exclusive so nothing is double-counted. The naming is the health reality:
#   Hep B  → "HBsAg" (surface-antigen test), NOT "hepatitis b"
#   Hep C  → "HCV"   (antibody test),        NOT "hepatitis c"
# Penicillin injections ("Inj. Benjapen") are syphilis TREATMENT, not a test
# kit, and are deliberately excluded from SL5b. Lubricant/gel is not a SIDA SL5
# commodity row (that sheet lists condoms) and is excluded from SL5a.
SL5_COMMODITY_FRAGMENTS = {
    'SL5a': ('condom',),               # condoms (incl. "Free Condom", "Condom ( Free)")
    'SL5b': ('syphilis',),             # syphilis test kits / quick strips
    'SL5c': ('hbsag', 'hepatitis b'),  # Hep B surface-antigen test
    'SL5d': ('hcv', 'hepatitis c'),    # Hep C antibody test
    'SL5e': ('hiv',),                  # HIV test kits (incl. "Determine HIV1/2")
}


def _kit_issued(org, period_start, period_end, fragments):
    """Sum quantity_issued of approved StockEntry rows whose item_name contains
    ANY of `fragments` (case-insensitive). Accepts a single string or an
    iterable of strings."""
    if isinstance(fragments, str):
        fragments = (fragments,)
    name_q = Q()
    for frag in fragments:
        name_q |= Q(item_name__icontains=frag)
    return StockEntry.objects.filter(
        organisation=org,
        approval_status=APPROVED,   # only manager-approved stock counts (system rule)
        reporting_month__range=(period_start, period_end),
    ).filter(name_q).aggregate(t=Sum('quantity_issued'))['t'] or 0


def compute_SL5a(org, period_start, period_end):   # condoms
    return _kit_issued(org, period_start, period_end, SL5_COMMODITY_FRAGMENTS['SL5a'])


# SL5b-e are the COMMODITY / test-kit stock rows — number of test kits issued,
# read from the Stock form (StockEntry.quantity_issued), matching the SIDA
# indicator sheet (label "… Screening Kits", unit "boxes", small boxes target).
# These are the SUPPLY measure. The count of screenings PERFORMED is a separate
# metric, served by SL5f-i below (Patient Record), so both views coexist.
def compute_SL5b(org, period_start, period_end):   # syphilis test kits issued
    return _kit_issued(org, period_start, period_end, SL5_COMMODITY_FRAGMENTS['SL5b'])


def compute_SL5c(org, period_start, period_end):   # hep B test kits issued
    return _kit_issued(org, period_start, period_end, SL5_COMMODITY_FRAGMENTS['SL5c'])


def compute_SL5d(org, period_start, period_end):   # hep C test kits issued
    return _kit_issued(org, period_start, period_end, SL5_COMMODITY_FRAGMENTS['SL5d'])


def compute_SL5e(org, period_start, period_end):   # HIV test kits issued
    return _kit_issued(org, period_start, period_end, SL5_COMMODITY_FRAGMENTS['SL5e'])


# SL5f-i — SCREENINGS PERFORMED, read from the Patient Record (clinic visit),
# a SEPARATE metric from the SL5b-e commodity/stock rows above. Per the client
# Indicators->Kobo map the screening questions clinic_syphilis_screen /
# clinic_hepb_screen / clinic_hepc_screen / clinic_hiv_screen land on these
# ClinicVisit booleans (syphilis has no dedicated field; clinic_syphilis_screen
# maps to sti_screening_done). Count approved visits in the period where that
# screen is Yes. These cards carry their own screening targets (set in Target
# Config); SL5b-e keep the stock "boxes" targets.
SL5_SCREEN_FIELD = {
    'SL5f': 'sti_screening_done',     # syphilis screening (clinic_syphilis_screen)
    'SL5g': 'hep_b_screening_done',
    'SL5h': 'hep_c_screening_done',
    'SL5i': 'hiv_screening_done',
}


def _screenings_done(org, period_start, period_end, field):
    return ClinicVisit.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        visit_date__range=(period_start, period_end),
        **{field: True},
    ).count()


def compute_SL5f(org, period_start, period_end):   # syphilis screenings performed
    return _screenings_done(org, period_start, period_end, SL5_SCREEN_FIELD['SL5f'])


def compute_SL5g(org, period_start, period_end):   # hep B screenings performed
    return _screenings_done(org, period_start, period_end, SL5_SCREEN_FIELD['SL5g'])


def compute_SL5h(org, period_start, period_end):   # hep C screenings performed
    return _screenings_done(org, period_start, period_end, SL5_SCREEN_FIELD['SL5h'])


def compute_SL5i(org, period_start, period_end):   # HIV screenings performed
    return _screenings_done(org, period_start, period_end, SL5_SCREEN_FIELD['SL5i'])


# ── SL6 — HIV/STI positive cases referred and enrolled in treatment ──────────
# Fragments that mark a Referral-register row as a POSITIVE HIV/STI case being
# sent on for treatment. Taken from the ACTUAL referral_reason values staff type
# in production (read 2026-11-10), not guessed:
#   'Syphilis positive' / 'Syphilis Positive'      -> 'positive'
#   'TPHA(+ve)' 'TPHA (+)' 'TPHA(+)ve' 'TPHA +ve'
#   'TPHA (+ve)' 'TPHA(+ ve)' 'TPHA+ ve'           -> 'tpha'
#   'HBsAg +ve' / 'HbsAg + tive'                   -> 'hbsag'
#   'Hepatitis B positive'                         -> 'positive'
#   'STI treatment'                                -> 'sti treatment'
# TPHA is the syphilis confirmatory test and is only recorded for positives, so
# the bare 'tpha' fragment is safe. Plain 'STI' / 'VIA' / 'General health'
# referrals are NOT positives and are deliberately excluded.
_SL6_POSITIVE_FRAGMENTS = (
    'tpha', 'positive', '+ve', '+ ve', '(+)', 'hbsag', 'sti treatment',
)


def compute_SL6(org, period_start, period_end):
    # "HIV/STI positive cases successfully referred and enrolled in treatment."
    # Sourced from the REFERRAL REGISTER ONLY, per the client Indicators->Kobo
    # map (SL6 -> Referral). The forms capture no separate "enrolled"
    # confirmation, so the recorded referral of a positive case is the
    # measurable step. Count distinct clients.
    reason_q = Q()
    for frag in _SL6_POSITIVE_FRAGMENTS:
        reason_q |= Q(referral_reason__icontains=frag)
    return Referral.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        referral_date__range=(period_start, period_end),
    ).filter(reason_q).values('client_id').distinct().count()


# ── SL7 — GBV survivors referred for MHPSS ───────────────────────────────────
def compute_SL7(org, period_start, period_end):
    # Sourced from the REFERRAL register ("referred for" = MHPSS / mental health),
    # per the client Indicators->Kobo map. NOT the Patient Record MHPSS tick: in
    # production (2026-11) the clinic tick carried 15 while the Referral register
    # carried 25 (referral_reason ~ "MHPSS"/"Mental health"). Count distinct
    # survivors referred for MHPSS. 'mhoss' covers a common field typo of MHPSS.
    return Referral.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        referral_date__range=(period_start, period_end),
    ).filter(
        Q(referral_reason__icontains='mhpss')
        | Q(referral_reason__icontains='mhoss')
        | Q(referral_reason__icontains='mental')
        | Q(referral_reason__icontains='psychosocial')
    ).values('client_id').distinct().count()


# ── SL8 — Functional brothel-based SRHR service centres ──────────────────────
# SIDA target is 9 BROTHEL-type centres. A centre counts as FUNCTIONAL only once
# it is actually delivering services in the period (>=1 approved record) — so a
# configured-but-idle brothel centre reads 0 until real activity arrives, and a
# pre-launch system shows 0, not 9. See indicators/_centers.py.
def compute_SL8(org, period_start, period_end):
    base = ServiceCenter.objects.filter(
        organisation=org,
        is_active=True,
        center_type=ServiceCenter.BROTHEL,
    )
    return len(active_center_ids(period_start, period_end, base))


# ── SL9 — Mobile health camps conducted ──────────────────────────────────────
def compute_SL9(org, period_start, period_end):
    # PHD mobile health camps are submitted through the Service Log event section
    # (record_type=event, event_subtype=camp) and stored as a TrainingEvent whose
    # event_type is the raw string 'camp' (programs.phd_handlers._phd_event writes
    # it directly; Django does not enforce `choices` on save). So the camp data
    # lives in TrainingEvent, NOT the MobileHealthCamp model (which only the
    # Bandhu / legacy standalone-form handlers populate). 0 until a camp is
    # submitted and approved.
    return TrainingEvent.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        event_date__range=(period_start, period_end),
        event_type='camp',
    ).count()


# ── SL10 — Focal points (DGFP/DGHS/DGNM) oriented ────────────────────────────
def compute_SL10(org, period_start, period_end):
    return TrainingEvent.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        event_date__range=(period_start, period_end),
        event_type='orientation',
        participant_type='HM',
    ).aggregate(t=Sum('total_participants'))['t'] or 0


# ── SL11 — Health managers / District-Upazila GOB staff oriented ─────────────
def compute_SL11(org, period_start, period_end):
    return TrainingEvent.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        event_date__range=(period_start, period_end),
        event_type='orientation',
        participant_type='GOB',
    ).aggregate(t=Sum('total_participants'))['t'] or 0


# ── SL12 — Medical Assistants / Midwives / Counsellors trained ───────────────
def compute_SL12(org, period_start, period_end):
    return TrainingEvent.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        event_date__range=(period_start, period_end),
        event_type='training',
        participant_type='MW',
    ).aggregate(t=Sum('total_participants'))['t'] or 0


# ── SL13 — Peer educators / community leaders trained ────────────────────────
def compute_SL13(org, period_start, period_end):
    return TrainingEvent.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        event_date__range=(period_start, period_end),
        participant_type='PE',
    ).aggregate(t=Sum('total_participants'))['t'] or 0


# ── SL14 — Quarterly coordination meetings ───────────────────────────────────
def compute_SL14(org, period_start, period_end):
    # PHD coordination meetings are submitted through the Service Log event
    # section (event_subtype=coord_meeting) and stored as a TrainingEvent whose
    # event_type is the raw string 'coord_meeting' (programs.phd_handlers.
    # _phd_event). The PHD data lives in TrainingEvent, NOT the CoordMeeting model
    # (that is the Bandhu / legacy standalone-form path). 0 until one is approved.
    return TrainingEvent.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        event_date__range=(period_start, period_end),
        event_type='coord_meeting',
    ).count()


# ── SL15 — Awareness materials installed (3 sub-rows) ────────────────────────
def _iec_qty(org, period_start, period_end, mat_type):
    return IECMaterial.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        date_distributed__range=(period_start, period_end),
        material_type=mat_type,
    ).aggregate(t=Sum('quantity'))['t'] or 0


def compute_SL15a(org, period_start, period_end):  # message boards
    return _iec_qty(org, period_start, period_end, IECMaterial.MESSAGE_BOARD)


def compute_SL15b(org, period_start, period_end):  # signboards
    return _iec_qty(org, period_start, period_end, IECMaterial.SIGNBOARD)


def compute_SL15c(org, period_start, period_end):  # billboards
    return _iec_qty(org, period_start, period_end, IECMaterial.BILLBOARD)


# ── SL16 — GBV corners established and fully equipped ───────────────────────
def compute_SL16(org, period_start, period_end):
    return GBVCornerRecord.objects.filter(
        organisation=org,
        approval_status=APPROVED,
        date_of_establishment__range=(period_start, period_end),
        fully_functional=True,
    ).count()


# ─── Activity-code registry ──────────────────────────────────────────────────
ACTIVITY_REGISTRY = {
    'SL1R':  compute_SL1R,          # headline "FSWs reached" = Mother List registry
    'SL1':   compute_SL1,
    'SL2':   compute_SL2,
    'SL3':   compute_SL3,
    'SL4':   compute_SL4,
    'SL5a':  compute_SL5a,
    'SL5b':  compute_SL5b,
    'SL5c':  compute_SL5c,
    'SL5d':  compute_SL5d,
    'SL5e':  compute_SL5e,
    'SL5f':  compute_SL5f,          # syphilis screenings performed (Patient Record)
    'SL5g':  compute_SL5g,          # hep B screenings performed
    'SL5h':  compute_SL5h,          # hep C screenings performed
    'SL5i':  compute_SL5i,          # HIV screenings performed
    'SL6':   compute_SL6,
    'SL7':   compute_SL7,
    'SL8':   compute_SL8,           # functional brothel centres (activity-gated)
    'SL9':   compute_SL9,
    'SL10':  compute_SL10,
    'SL11':  compute_SL11,
    'SL12':  compute_SL12,
    'SL13':  compute_SL13,
    'SL14':  compute_SL14,
    'SL15a': compute_SL15a,
    'SL15b': compute_SL15b,
    'SL15c': compute_SL15c,
    'SL16':  compute_SL16,
}

ORG_ONLY_CODES = set()  # SL8 is now period-aware (activity-gated functional centres)
