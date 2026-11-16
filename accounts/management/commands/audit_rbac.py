"""Read-only RBAC audit: who can approve what, and are any pending rows orphaned.

Diagnostic for "<org> is unable to approve". Nothing is written. It answers
three questions with LIVE data, which the approval-path source code cannot
answer on its own because the outcome depends on each account's stored
``role`` / ``organisation`` and on the ``organisation`` stamped on the pending
rows:

  1. Every user account: email, organisation, role, is_active, and the two
     capability flags that gate approval (``can_approve_submissions``,
     ``can_see_all_orgs``).
  2. The PENDING backlog broken down by organisation and model, so a
     mis-stamped organisation on backfilled rows shows up immediately.
  3. A simulation of the real authorisation predicate (the exact rule in
     programs.views._authorise_review) for every ACTIVE account against the
     live PENDING rows — so we see, per account, how many rows it may approve,
     and we flag any PENDING organisation that NO active account can approve
     (an orphaned queue — the data-level shape of "unable to approve").

    railway ssh   # web / production — then:
    python manage.py audit_rbac
    python manage.py audit_rbac --org PHD     # focus one partner
"""
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


def _approval_models():
    """(model_type, queryset_factory) pairs — the single source the approval
    queue itself iterates, imported so this audit can never drift from it."""
    from programs.views import _APPROVAL_MODELS
    return _APPROVAL_MODELS


def _is_super(user):
    """Mirror of _authorise_review: a developer, or any see-all-orgs role that
    is not UNFPA, acts across every org."""
    urole = getattr(user, 'role', '')
    uorg = getattr(user, 'organisation', '')
    return (urole == 'developer') or (
        bool(getattr(user, 'can_see_all_orgs', False)) and uorg != 'UNFPA')


def _is_unfpa(user):
    uorg = getattr(user, 'organisation', '')
    urole = getattr(user, 'role', '')
    return (uorg == 'UNFPA') and urole != 'developer'


def _may_approve(user, record_org):
    """Exact replica of programs.views._authorise_review's allow condition for
    an ``approve`` on a record whose organisation is ``record_org``."""
    if not getattr(user, 'can_approve_submissions', False):
        return False
    uorg = getattr(user, 'organisation', '')
    return (_is_super(user)
            or record_org == uorg
            or (_is_unfpa(user) and record_org == 'Bandhu'))


class Command(BaseCommand):
    help = 'Read-only RBAC audit of approval access and the PENDING backlog.'

    def add_arguments(self, parser):
        parser.add_argument('--org', dest='org', default=None,
                            help='Limit the pending breakdown to one organisation.')

    def handle(self, *args, **opts):
        User = get_user_model()
        focus = opts.get('org')

        # ── 1. Accounts ─────────────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('\n== ACCOUNTS =='))
        header = ('  %-32s %-8s %-14s %-6s %-9s %-8s'
                  % ('email', 'org', 'role', 'active', 'approve', 'seeall'))
        self.stdout.write(header)
        users = list(User.objects.order_by('organisation', 'role', 'email'))
        for u in users:
            line = ('  %-32s %-8s %-14s %-6s %-9s %-8s' % (
                (u.email or '')[:32],
                getattr(u, 'organisation', '') or '-',
                getattr(u, 'role', '') or '-',
                'yes' if u.is_active else 'NO',
                'yes' if getattr(u, 'can_approve_submissions', False) else 'no',
                'yes' if getattr(u, 'can_see_all_orgs', False) else 'no',
            ))
            # Highlight an inactive account or a non-approver in a partner org —
            # the two shapes that silently break "I can't approve".
            style = self.style.SUCCESS
            if not u.is_active:
                style = self.style.ERROR
            elif (getattr(u, 'organisation', '') in ('PHD', 'Bandhu')
                  and not getattr(u, 'can_approve_submissions', False)):
                style = self.style.WARNING
            self.stdout.write(style(line))

        # ── 2. Pending backlog by org × model ───────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('\n== PENDING BACKLOG (by org x model) =='))
        pending_by_org = defaultdict(int)
        rows_by_org_model = defaultdict(int)   # (org, model_type) -> n
        for model_type, qs_fn in _approval_models():
            try:
                qs = qs_fn().filter(approval_status='PENDING')
            except Exception as exc:  # a model without approval_status, etc.
                self.stdout.write(self.style.WARNING(
                    '  (skipped %s: %s)' % (model_type, exc)))
                continue
            # Count per organisation without loading rows.
            try:
                from django.db.models import Count
                grouped = (qs.values('organisation')
                             .order_by()
                             .annotate(n=Count('id')))
            except Exception:
                grouped = []
            for g in grouped:
                org = g['organisation'] or '(blank)'
                n = g['n']
                pending_by_org[org] += n
                rows_by_org_model[(org, model_type)] += n

        if not pending_by_org:
            self.stdout.write('  (no PENDING rows)')
        for org in sorted(pending_by_org):
            if focus and org != focus:
                continue
            self.stdout.write(self.style.SUCCESS(
                '  %-10s total PENDING = %d' % (org, pending_by_org[org])))
            for (o, mt), n in sorted(rows_by_org_model.items()):
                if o == org:
                    self.stdout.write('      %-26s %d' % (mt, n))

        # ── 3. Who can clear each pending org ───────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('\n== APPROVER COVERAGE (active accounts) =='))
        active = [u for u in users if u.is_active]
        for org in sorted(pending_by_org):
            approvers = [u.email for u in active if _may_approve(u, org)]
            if approvers:
                self.stdout.write(self.style.SUCCESS(
                    '  %-10s (%d pending) -> approvable by: %s'
                    % (org, pending_by_org[org], ', '.join(approvers))))
            else:
                # No active account can approve this org's rows: this is the
                # data-level cause of "unable to approve".
                self.stdout.write(self.style.ERROR(
                    '  %-10s (%d pending) -> NO active account can approve these'
                    % (org, pending_by_org[org])))

        self.stdout.write('')
        self.stdout.write(
            'Read-only: nothing was written. "approve"=can_approve_submissions, '
            '"seeall"=can_see_all_orgs. A partner-org row with approve=no is a '
            'view-only/field account and will get 403 on approve.')
