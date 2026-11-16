"""Backfill live PHD Kobo submissions into this instance through the real handlers.

Recovery tool for after a PHD webhook was misrouted (hooks pointing at a
dead/old deployment) and reconnected with ``rewire_kobo_hooks``: it pulls every
submission the live PHD forms hold in Kobo and runs each through the exact
handler the webhook dispatches to, PERSISTING new records. It is idempotent —
already-landed submissions are 200 no-ops — so it only fills the gap, and is
safe to re-run. New records land PENDING for manager approval, just like a live
delivery.

    railway run python manage.py backfill_phd --dry-run     # size the gap, write nothing
    railway run python manage.py backfill_phd               # persist the gap
    railway run python manage.py backfill_phd --slug phd_service_log_v1
    railway run python manage.py backfill_phd --limit 50    # smoke test (few per form)

Exit code is non-zero if any handler crashed on live data.
"""
import os
import sys

from django.core.management.base import BaseCommand, CommandError

from programs.phd_replay import backfill_phd


class Command(BaseCommand):
    help = ('Backfill live PHD Kobo submissions through the handlers '
            '(persists new records; idempotent).')

    def add_arguments(self, parser):
        parser.add_argument('--slug', action='append', dest='slugs',
                            help='Limit to these PHD slug(s); repeatable.')
        parser.add_argument('--asset', action='append', dest='assets', default=[],
                            help='Limit to these Kobo asset uid(s); repeatable.')
        parser.add_argument('--limit', type=int, default=None,
                            help='Max submissions per form (smoke test).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Fetch and classify but roll back every write.')

    def handle(self, *args, **opts):
        token = (os.environ.get('KOBO_TOKEN')
                 or os.environ.get('KOBO_API_TOKEN') or '').strip()
        if not token:
            raise CommandError(
                'KOBO_TOKEN (or KOBO_API_TOKEN) is not set — run via `railway run`.')

        dry = opts['dry_run']
        self.stdout.write('Mode : %s' % (
            'DRY RUN (nothing written)' if dry else 'LIVE (persisting new records)'))
        self.stdout.write('')

        results = backfill_phd(
            token,
            slugs=opts.get('slugs') or None,
            limit=opts.get('limit'),
            dry_run=dry,
            only_uids=set(opts['assets']) or None,
        )

        if not results:
            self.stdout.write(self.style.WARNING(
                'No live PHD forms resolved in Kobo (name must contain "PHD" and '
                'map to a phd_* slug). Nothing to backfill.'))
            return

        total_created = total_skipped = total_bad = 0
        crashed = []
        for name, rec in results.items():
            total_created += rec['created']
            total_skipped += rec['skipped']
            total_bad += rec['bad']
            line = ('  %-28s n=%-4d created=%-4d skipped=%-4d bad=%-3d crashes=%d'
                    % (name, rec['n'], rec['created'], rec['skipped'],
                       rec['bad'], len(rec['errors'])))
            style = self.style.ERROR if rec['errors'] else self.style.SUCCESS
            self.stdout.write(style(line))
            for err in rec['errors']:
                crashed.append('%s [%s]: %s' % (name, err['id'], err['error']))
                self.stdout.write(self.style.ERROR(
                    '      CRASH %s: %s' % (err['id'], err['error'])))

        self.stdout.write('')
        self.stdout.write('Totals: created=%d skipped(existing)=%d bad=%d%s' % (
            total_created, total_skipped, total_bad,
            '   (dry run — nothing persisted)' if dry else ''))
        if not dry and total_created:
            self.stdout.write(self.style.SUCCESS(
                '%d new PHD record(s) backfilled — PENDING, need manager approval.'
                % total_created))

        if crashed:
            self.stdout.write(self.style.ERROR(
                '\n%d handler crash(es) on live data.' % len(crashed)))
            sys.exit(1)
