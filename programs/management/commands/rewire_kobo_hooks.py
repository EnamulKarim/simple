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

Canonical mode (--canonical, implied by --on-boot)
--------------------------------------------------
After a project transfer/fork some Kobo forms post their asset UID as
``_xform_id_string`` instead of their XLSForm settings id_string. FORM_HANDLERS
is keyed by id_string, so the shared endpoint drops those as "unknown form
id_string". The per-form endpoint /webhook/programs/form/<slug>/ routes by the
URL slug regardless of the payload id_string, so --canonical wires every
recognised form to its exact FORM_HANDLERS key (resolved from the Kobo asset
NAME via NAME_TO_SLUG_RULES). Unrecognised assets are left untouched and
listed in the summary so the table can be extended. Nothing is ever deleted
unless --cutover is passed (never in --on-boot).
"""
import os
import re

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

KOBO_BASE = os.environ.get("KOBO_BASE", "https://kf.kobotoolbox.org").rstrip("/")
API = f"{KOBO_BASE}/api/v2"
HOOK_NAME = "SIMPLE Railway"

# Kobo asset name -> canonical FORM_HANDLERS key. Each rule is
# (all_of, any_of, slug): every term in all_of must appear in the lower-cased
# name, and (if any_of is non-empty) at least one term in any_of. Terms in
# any_of / all_of are regular expressions. First match wins, so the most
# specific rules come first. Names matching nothing are left unmapped.
NAME_TO_SLUG_RULES = [
    (("no report",), (), "no_report_v1"),
    (("mpdsr",), ("action plan", "response plan"), "ciprb_mpdsr_response_plan_v1"),
    (("mpdsr", "community", "maternal"), (), "ciprb_mpdsr_community_maternal_v1"),
    (("mpdsr", "community", "neonatal"), (), "ciprb_mpdsr_community_neonatal_v1"),
    (("mpdsr", "facility", "maternal"), (), "ciprb_mpdsr_facility_maternal_v1"),
    (("mpdsr", "facility", "neonatal"), (), "ciprb_mpdsr_facility_neonatal_v1"),
    (("fistula", "question"), (), "ciprb_fistula_questions_v1"),
    (("fistula", "campaign"), (), "ciprb_fistula_campaign_v1"),
    (("social", "autopsy"), (), "ciprb_social_autopsy_v1"),
    (("notification",), (r"\b0?1\b", r"\bone\b"), "ciprb_notification_slip_01_v1"),
    (("notification",), (r"\b0?2\b", r"\btwo\b"), "ciprb_notification_slip_02_v1"),
    (("near", "miss"), (), "ciprb_near_miss_v1"),
    (("safe", "surgery"), (), "ciprb_safe_surgery_v1"),
    (("mother list",), (), "bandhu_mother_list_v1"),
    (("beneficiary", "service"), (), "bandhu_service_log_v1"),
    (("bandhu",), ("training", "other services"), "bandhu_activity_ops_v1"),
    (("phd", "registration"), (), "phd_registration_v1"),
    (("phd", "service", "log"), (), "phd_service_log_v1"),
]

# MPDSR forms are distinguished only by the (community|facility) and
# (maternal|neonatal) words; if the name has both words of an axis we cannot
# tell which form it is, so it is treated as unmapped instead of guessed.
_MPDSR_AXES = (("community", "facility"), ("maternal", "neonatal"))


def resolve_canonical_slug(name):
    """Return the canonical FORM_HANDLERS key for a Kobo asset name, or None."""
    low = (name or "").lower()
    if "mpdsr" in low and any(a in low and b in low for a, b in _MPDSR_AXES):
        return None
    for all_of, any_of, slug in NAME_TO_SLUG_RULES:
        if not all(re.search(t, low) for t in all_of):
            continue
        if any_of and not any(re.search(t, low) for t in any_of):
            continue
        if slug.startswith("ciprb_notification_slip") and re.search(
                r"\b0?1\b|\bone\b", low) and re.search(r"\b0?2\b|\btwo\b", low):
            return None  # names both slips: ambiguous
        return slug
    return None


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
        parser.add_argument("--canonical", action="store_true",
                            help="Wire each form to /webhook/programs/form/<CANONICAL_SLUG>/ "
                                 "where the slug is an exact FORM_HANDLERS key resolved "
                                 "from the Kobo asset NAME. Unrecognised names are left "
                                 "untouched and listed. Implied by --on-boot.")
        parser.add_argument("--contains", default="",
                            help="Only touch assets whose name contains this text.")
        parser.add_argument("--asset", action="append", default=[],
                            help="Limit to these asset uid(s). Repeatable.")
        parser.add_argument("--on-boot", action="store_true",
                            help="Deploy-time mode: add-only (never cutover) and never "
                                 "raise, and implies --canonical. If prerequisites are "
                                 "missing it prints a notice and exits 0, so it is safe "
                                 "in the boot chain.")

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
        on_boot = opts["on_boot"]
        try:
            token = self._token()
            public = self._public_url()
            secret = self._secret()
        except CommandError as exc:
            if on_boot:
                # Boot-time: never crash the deploy. Report and move on.
                self.stdout.write(f"rewire_kobo_hooks skipped: {exc}")
                return
            raise
        try:
            self._rewire(opts, token, public, secret)
        except Exception as exc:  # noqa: BLE001 - boot mode must never crash the deploy
            if not on_boot:
                raise
            self.stdout.write(f"rewire_kobo_hooks aborted (non-fatal): {exc!r}")

    def _rewire(self, opts, token, public, secret):
        on_boot = opts["on_boot"]
        canonical = opts["canonical"] or on_boot
        headers = {"Authorization": f"Token {token}"}
        dry = opts["dry_run"]
        cutover = opts["cutover"] and not on_boot  # boot mode is always add-only
        handlers = None
        if canonical:
            from programs.webhook import FORM_HANDLERS as handlers

        host = requests.utils.urlparse(public).netloc
        self.stdout.write(f"Target instance : {public}")
        self.stdout.write(f"Kobo API        : {API}")
        self.stdout.write(f"Mode            : "
                          f"{'DRY RUN' if dry else 'LIVE'}"
                          f"{' + cutover' if cutover else ''}"
                          f"{' [canonical per-form routing]' if canonical else ''}")
        self.stdout.write("")

        touched = added = updated = removed = skipped = 0
        unmapped = []
        for a in self._assets(headers, opts["contains"], set(opts["asset"])):
            uid = a["uid"]
            name = a.get("name") or uid
            if canonical:
                slug = resolve_canonical_slug(name)
                if not slug or slug not in handlers:
                    self.stdout.write(f"  [unmapped]    {name} ({uid})  -> left untouched")
                    unmapped.append((name, uid))
                    continue
                endpoint = f"{public}/webhook/programs/form/{slug}/"
            elif opts["by_form"]:
                slug = (a.get("deployment__identifier") or "").rstrip("/").rsplit("/", 1)[-1] \
                       or uid
                endpoint = f"{public}/webhook/programs/form/{slug}/"
            else:
                endpoint = f"{public}/webhook/programs/"

            hooks = requests.get(f"{API}/assets/{uid}/hooks/", headers=headers,
                                 timeout=60).json().get("results", [])
            mine = [h for h in hooks if h.get("endpoint") == endpoint]
            if canonical and not mine:
                # Re-point our own earlier hook (same host, /webhook/programs...)
                # instead of adding a second hook that would double-post.
                mine = [h for h in hooks
                        if h.get("name") == HOOK_NAME
                        and requests.utils.urlparse(h.get("endpoint", "")).netloc == host
                        and "/webhook/programs" in (h.get("endpoint") or "")][:1]
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
        if canonical:
            self.stdout.write(f"Canonical hooks: added={added} updated={updated}")
            if unmapped:
                self.stdout.write(self.style.WARNING(
                    f"UNMAPPED deployed assets ({len(unmapped)}), left untouched; "
                    "extend NAME_TO_SLUG_RULES to route them:"))
                for n, u in unmapped:
                    self.stdout.write(f"  - {n}  (uid {u})")
            else:
                self.stdout.write("No unmapped deployed assets.")
        if not dry:
            self.stdout.write(
                "Next: submit one test record from Kobo and confirm it appears in this "
                "instance's pending-approval queue. Historical data comes from the DB "
                "backup restore, not from this command.")
