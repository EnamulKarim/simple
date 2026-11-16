"""Backfill live PHD Kobo submissions through the real handlers (PERSISTING).

Companion to ``ciprb_replay``, but for RECOVERY rather than diagnosis.
``replay_ciprb`` runs every CIPRB payload through its handler inside a
transaction the caller always rolls back — it proves handlers don't 500, and
nothing persists. This module instead **commits** each payload, so it fills the
gap left when a PHD webhook was misrouted (hooks pointing at a dead/old
deployment) and later reconnected via ``rewire_kobo_hooks``.

It is safe to run, and to re-run, because every PHD handler is idempotent:
each ``_phd_*`` section guards with ``_already_exists(Model, payload)`` on the
unique ``kobo_submission_id`` (programs/models/_base.py), registration guards on
``id_no``, and stock folds by ``source_submission_ids``. A submission already in
the DB is therefore a 200 no-op; only the missing ones are inserted. New records
land PENDING (per-record ``approval_status``), exactly as a live webhook
delivery would, so a manager still approves them before they count.

Each payload runs in its OWN savepoint and commits on a 2xx; a 4xx/5xx response
or a handler crash rolls back just that payload and is recorded. Forms are
discovered dynamically (Kobo asset NAME -> slug via the same
``resolve_canonical_slug`` the rewire command uses), so there are no hardcoded
UIDs to drift.
"""
import requests
from django.db import transaction

from programs.webhook import FORM_HANDLERS, _flatten_group_keys, _geolocation
from programs.ciprb_replay import KOBO_BASE, _fetch
from programs.management.commands.rewire_kobo_hooks import resolve_canonical_slug


def phd_assets(token, contains='PHD', only=None):
    """Yield ``(uid, name, slug)`` for deployed Kobo survey assets whose NAME
    resolves to a ``phd_*`` FORM_HANDLERS slug.

    Mirrors ``rewire_kobo_hooks._assets`` so the backfill targets exactly the
    PHD forms that actually exist in Kobo — no hardcoded UIDs, and legacy names
    that resolve to nothing are skipped.
    """
    headers = {'Authorization': 'Token ' + token}
    url = '%s/assets/?limit=200&q=asset_type:survey' % KOBO_BASE
    while url:
        r = requests.get(url, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        for a in data.get('results', []):
            uid = a.get('uid')
            name = a.get('name') or uid
            if only and uid not in only:
                continue
            if contains and contains.lower() not in (name or '').lower():
                continue
            if not a.get('has_deployment'):
                continue
            slug = resolve_canonical_slug(name)
            if not slug or not slug.startswith('phd_') or slug not in FORM_HANDLERS:
                continue
            yield uid, name, slug
        url = data.get('next')


def backfill_phd(token, slugs=None, limit=None, dry_run=False, only_uids=None):
    """Replay and PERSIST live PHD payloads for every resolved PHD form.

    Returns a per-form summary::

        { name: {uid, slug, n, created, skipped, bad, errors:[{id, error}]} }

    ``created`` counts 201s (new rows written), ``skipped`` counts 200s
    (idempotent no-ops — already in the DB), ``bad`` counts 4xx (e.g. centre not
    found), ``errors`` captures 5xx and crashes. Each payload is isolated in its
    own savepoint and committed only on 2xx; ``dry_run`` rolls every payload back
    so the gap can be sized without writing.
    """
    out = {}
    for uid, name, slug in phd_assets(token, only=only_uids):
        if slugs and slug not in slugs:
            continue
        handler = FORM_HANDLERS.get(slug)
        rec = {'uid': uid, 'slug': slug, 'n': 0,
               'created': 0, 'skipped': 0, 'bad': 0, 'errors': []}
        if handler is None:
            rec['errors'].append({'id': None, 'error': 'no handler for slug %s' % slug})
            out[name] = rec
            continue

        subs = _fetch(uid, token, limit)
        rec['n'] = len(subs)
        for s in subs:
            payload = _flatten_group_keys(s)
            lat, lng = _geolocation(payload)
            sid = s.get('_id')
            try:
                with transaction.atomic():   # savepoint: isolates this payload
                    resp = handler(payload, lat, lng)
                    code = getattr(resp, 'status_code', 200)
                    # Persist only clean writes. 4xx/5xx roll back any partial
                    # work; dry_run rolls back everything.
                    if dry_run or code >= 400:
                        transaction.set_rollback(True)
            except Exception as exc:  # noqa: BLE001 — any handler crash is a failure
                rec['errors'].append({'id': sid,
                                      'error': '%s: %s' % (type(exc).__name__, exc)})
                continue

            if code >= 500:
                rec['errors'].append({'id': sid, 'error': 'HTTP %s' % code})
            elif code >= 400:
                rec['bad'] += 1
            elif code == 201:
                rec['created'] += 1
            else:
                rec['skipped'] += 1
        out[name] = rec
    return out
