"""Clean Bandhu service/activity data in place, KEEPING the Mother List.

Rafi, 2026-11-12: the Bandhu dashboard was showing wrong service/activity
numbers (557 outreach, 36 counselling, 9 referrals, ...) carried over from the
OLD duplicate forms. The three LIVE forms now wire straight into these same
models, so once the stale rows are cleared the indicators repopulate fresh:

    bandhu_service_log_v1  -> WellnessLogbookEntry, ClinicVisit,
                              HIVSTITestResult, HTCCounselling,
                              IndividualCounselling, GBVCase, Referral   (1.1-1.7)
    bandhu_activity_ops_v1 -> OutreachSession, MobileHealthCamp,
                              TrainingEvent, CoordMeeting, IECMaterial    (1.4a, 1.9, 2.x, 4.x)
    bandhu_mother_list_v1  -> Client                                     (kept)

This deletes only rows whose organisation == 'Bandhu' in the service/activity
models below. Client (the Mother List registry, old dump + new) is NOT in the
list, so it is untouched. PHD / CIPRB / MPDSR / Fistula data is untouched
because every delete is filtered to organisation='Bandhu'.

Safety: DRY RUN by default (counts, then rolls back). --apply requires --yes.
Uses the ORM so PROTECT/cascade are honoured; Client is kept, so deleting the
service rows that reference it is always the child side (never blocked).
"""
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.deletion import ProtectedError

ORG = 'Bandhu'

# Deleted in this order: inter-service children before parents where an FK with
# PROTECT exists (e.g. GBVAccessLog -> GBVCase). Each is filtered to
# organisation='Bandhu'; models without that field, or with no Bandhu rows, are
# reported as skipped/0 and never error.
SERVICE_MODELS = [
    'programs.GBVAccessLog', 'programs.GBVCornerRecord', 'programs.GBVCase',
    'programs.HTCCounselling', 'programs.IndividualCounselling',
    'programs.MHScreening', 'programs.PHDCounsellingReport',
    'programs.HIVSTITestResult', 'programs.ADRRecord', 'programs.AntenatalCard',
    'programs.AutoclaveLog', 'programs.ClinicVisit',
    'programs.OutreachSession', 'programs.GroupEducationSession',
    'programs.WellnessLogbookEntry', 'programs.MobileHealthCamp',
    'programs.VisitorRegister', 'programs.CoordMeeting',
    'programs.TrainingEvent', 'programs.StockEntry', 'programs.TemperatureLog',
    'programs.SafetyHygieneKit', 'programs.StoreRequisition',
    'programs.Referral', 'programs.IECMaterial', 'programs.NilReport',
]

# NEVER deleted here — proves the Mother List is preserved.
KEEP = {'programs.Client'}


def _has_org(model):
    try:
        model._meta.get_field('organisation')
        return True
    except Exception:
        return False


class Command(BaseCommand):
    help = "Clear Bandhu service/activity data in place, keeping the Mother List (Client)."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Actually delete. Without it, dry run (rolls back).')
        parser.add_argument('--yes', action='store_true',
                            help='Required with --apply. Confirms the Bandhu wipe.')

    def handle(self, *args, **opts):
        apply = opts['apply']
        if apply and not opts['yes']:
            raise CommandError('--apply requires --yes.')
        if KEEP & set(SERVICE_MODELS):
            raise CommandError('Client must never be in SERVICE_MODELS.')

        client = apps.get_model('programs', 'Client')
        kept_clients = client.objects.filter(organisation=ORG).count()

        rows = []
        try:
            with transaction.atomic():
                for label in SERVICE_MODELS:
                    model = apps.get_model(*label.split('.'))
                    if not _has_org(model):
                        rows.append((label, None, 0, 'no organisation field'))
                        continue
                    qs = model.objects.filter(organisation=ORG)
                    before = qs.count()
                    deleted = qs.delete()[0] if before else 0
                    rows.append((label, before, deleted, ''))
                if not apply:
                    transaction.set_rollback(True)
        except ProtectedError as exc:
            raise CommandError(
                'PROTECT blocked a delete; nothing committed. Detail: %s' % exc)

        hdr = 'APPLY' if apply else 'DRY RUN'
        self.stdout.write(self.style.MIGRATE_HEADING(
            '\nClean Bandhu services  (%s)' % hdr))
        self.stdout.write('  %-40s %8s %8s  %s' % ('model', 'before', 'deleted', 'note'))
        self.stdout.write('  ' + '-' * 72)
        total = 0
        for label, before, deleted, note in rows:
            total += deleted
            self.stdout.write('  %-40s %8s %8d  %s' % (
                label, '-' if before is None else before, deleted, note))
        self.stdout.write('  ' + '-' * 72)
        self.stdout.write('  %-40s %8s %8d' % ('TOTAL deleted', '', total))
        self.stdout.write('  Mother List (Client, organisation=%s) KEPT: %d rows'
                          % (ORG, kept_clients))
        if apply:
            self.stdout.write(self.style.SUCCESS(
                '\nApplied. Bandhu indicators now repopulate from the live forms.'))
        else:
            self.stdout.write(self.style.WARNING(
                '\nDry run - rolled back, nothing changed. Re-run with --apply --yes.'))
