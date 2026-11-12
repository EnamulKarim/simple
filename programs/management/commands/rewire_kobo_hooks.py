"""
Repoint every SIMPLE Kobo REST Service hook at THIS deployment.

Why this exists
---------------
Each KoboToolbox form carries a "REST Service" hook that stores a FULL
endpoint URL pointing at one specific SIMPLE deployment, e.g.

    https://<old-app>.up.railway.app/webhook/programs/

When the project is forked and redeployed to a new Railway URL, those
hooks still post to the OLD url, so the NEW instance receives no
submissions at all, so the dashboard renders the forms (they come from
code) but shows no live data. This command rewrites the hooks so Kobo
posts to the instance named by settings.SIMPLE_PUBLIC_URL, using the
secret this instance validates against (settings.KOBO_WEBHOOK_SECRET).

It is idempotent and, by default, NON-DESTRUCTIVE: it only adds or
updates this instance's own hook and never deletes a hook that points
somewhere else. Pass --cutover to also remove hooks that point at a
different host (use this once the old deployment is being retired).

Setup on the new instance BEFORE running
-----------------------------------------
Set these env vars on the Railway web service:
    SIMPLE_PUBLIC_URL    = https://<this-new-app>.up.railway.app   (no trailing slash)
    KOBO_WEBHOOK_SECRET  = <the shared webhook secret>
Then provide a Kobo API token that owns the forms, as either
KOBO_API_TOKEN or KOBO_TOKEN in the environment (not committed).

Usage
-----
    railway run python manage.py rewire_kobo_hooks --dry-run
    railway run python manage.py rewire_kobo_hooks
    railway run python manage.py rewire_kobo_hooks --cutover
    railway run python manage.py rewire_kobo_hooks --contains CIPRB

The default endpoint is the shared fallback (/webhook/programs/), which
dispatches on the form id_string in the payload and therefore needs no
per-form slug. Pass --by-form to wire the slug-in-URL endpoint instead.
"""
import os

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

KOBO_BASE = os.environ.get("KOBO_BASE", "https://kf.kobotoolbox.org").rstrip("/")
API = f"{KOBO_BASE}/api/v2"
HOOK_NAME = "SIMPLE Railway"


class Command(BaseCommand):
    help = "Repoint SIMPLE Kobo REST Service hooks at this deployment (SIMPLE_PUBLIC_URL)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Show what would change without touching Kobo.")
        parser.add_argument("--cutover", action="store_true",
                            help="Also delete hooks that point at a DIFFERENT host "
                                 "(retire the old deployment). Default keeps them.")
        parser.add_argument("--by-form", action="store_true",
                            help="Wire the slug-in-URL endpoint "
                                 "(/webhook/programs/form/<id_string>/) instead of the "
                                 "shared fallback (/webhook/programs/).")
        parser.add_argument("--contains", default="",
                            help="Only touch assets whose name contains this text.")
        parser.add_argument("--asset", action="append", default=[],
                            help="Limit to these asset uid(s). Repeatable.")

    # ── helpers ──────────────────────────────────────────────────────────────
    def _token(self):
        tok = (os.environ.get("KOBO_API_TOKEN")
               or os.environ.get("KOBO_TOKEN")
               or getattr(settings, "KOBO_API_TOKEN", "")).strip()
        if not tok:
            raise CommandError(
                "No Kobo API token. Set KOBO_API_TOKEN (or KOBO_TOKEN) in the "
                "environment to a token that owns the forms.")
        return tok

    def _public_url(self):
        url = (getattr(settings, "SIMPLE_PUBLIC_URL", "") or "").strip().rstrip("/")
        if not url or "web-production-091fa" in url:
            raise CommandError(
                "SIMPLE_PUBLIC_URL is unset or still the default example. Set it on "
                "this Railway service to this app's own https URL before rewiring, "
                "or every hook would point back at the old deployment.")
        return url

    def _secret(self):
        sec = (getattr(settings, "KOBO_WEBHOOK_SECRET", "") or "").strip()
        if not sec:
            raise CommandError(
                "KOBO_WEBHOOK_SECRET is unset. The receiver is fail-closed and would "
                "reject every post. Set it on this service first.")
        return sec

    def _assets(self, headers, contains, only):
        """Yield deployed survey assets owned by the token's account."""
        url = f"{API}/assets/?limit=200&q=asset_type:survey"
        while url:
            r = requests.get(url, headers=headers, timeout=60)
            r.raise_for_status()
            data = r.json()
            for a in data.get("results", []):
                if only and a.get("uid") not in only:
                    continue
                if contains and contains.lower() not in (a.get("name") or "").lower():
                    continue
                if not a.get("has_deployment"):
                    continue
                yield a
            url = data.get("next")

    # ── main ─────────────────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        token = self._token()
        public = self._public_url()
        secret = self._secret()
        headers = {"Authorization": f"Token {token}"}
        dry = opts["dry_run"]
        cutover = opts["cutover"]

        host = requests.utils.urlparse(public).netloc
        self.stdout.write(f"Target instance : {public}")
        self.stdout.write(f"Kobo API        : {API}")
        self.stdout.write(f"Mode            : "
                          f"{'DRY RUN' if dry else 'LIVE'}"
                          f"{' + cutover' if cutover else ''}")
        self.stdout.write("")

        touched = added = updated = removed = skipped = 0
        for a in self._assets(headers, opts["contains"], set(opts["asset"])):
            uid = a["uid"]
            name = a.get("name") or uid
            if opts["by_form"]:
                slug = (a.get("deployment__identifier") or "").rstrip("/").rsplit("/", 1)[-1] \
                       or uid
                endpoint = f"{public}/webhook/programs/form/{slug}/"
            else:
                endpoint = f"{public}/webhook/programs/"

            hooks = requests.get(f"{API}/assets/{uid}/hooks/", headers=headers,
                                 timeout=60).json().get("results", [])
            mine = [h for h in hooks if h.get("endpoint") == endpoint]
            stale = [h for h in hooks
                     if requests.utils.urlparse(h.get("endpoint", "")).netloc
                     not in ("", host)
                     and "/webhook/programs" in (h.get("endpoint") or "")]

            payload = {
                "name": HOOK_NAME,
                "endpoint": endpoint,
                "active": True,
                "export_type": "json",
                "email_notification": False,
                "settings": {"custom_headers": {"Authorization": f"Token {secret}"}},
            }

            touched += 1
            if mine:
                self.stdout.write(f"  [keep/update] {name}  ->  {endpoint}")
                if not dry:
                    requests.patch(f"{API}/assets/{uid}/hooks/{mine[0]['uid']}/",
                                   headers=headers, json=payload, timeout=60)
                updated += 1
            else:
                self.stdout.write(f"  [add]         {name}  ->  {endpoint}")
                if not dry:
                    r = requests.post(f"{API}/assets/{uid}/hooks/", headers=headers,
                                      json=payload, timeout=60)
                    if r.status_code not in (200, 201):
                        self.stderr.write(f"      ! add failed ({r.status_code}): {r.text[:200]}")
                        skipped += 1
                        continue
                added += 1

            if cutover and stale:
                for h in stale:
                    self.stdout.write(f"      [cutover] remove stale hook -> {h.get('endpoint')}")
                    if not dry:
                        requests.delete(f"{API}/assets/{uid}/hooks/{h['uid']}/",
                                        headers=headers, timeout=60)
                    removed += 1
            elif stale:
                for h in stale:
                    self.stdout.write(f"      (left in place; --cutover removes) {h.get('endpoint')}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Done. assets touched={touched} added={added} updated={updated} "
            f"stale_removed={removed} skipped={skipped}"
            f"{'  (dry run, nothing written)' if dry else ''}"))
        if not dry:
            self.stdout.write(
                "Next: submit one test record from Kobo and confirm it appears in this "
                "instance's pending-approval queue. Historical data comes from the DB "
                "backup restore, not from this command.")
