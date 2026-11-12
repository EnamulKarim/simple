# Moving SIMPLE to a new deployment: data flow checklist

When this project is forked and redeployed to a new Railway URL, the dashboard
shows the forms (they are built from code) but no data arrives. That is expected:
the data does not live in the code, it flows in from KoboToolbox, and Kobo only
knows the OLD deployment's address. This checklist points the data at the new
instance.

## Why the dashboard looks empty on a fresh deployment

Every Kobo form has a **REST Service hook** that stores a full URL pointing at one
specific deployment:

    https://<old-app>.up.railway.app/webhook/programs/      (Authorization: Token <secret>)

A new deployment has a different URL, so Kobo keeps posting every submission to the
old instance. The new one receives nothing. Two more things must line up:

1. The receiver is **fail-closed**. It rejects every post unless
   `KOBO_WEBHOOK_SECRET` on the new instance matches the `Token` the hooks send.
2. **Historical records** are in the old database, not in the form definitions, so
   the new instance starts empty until the database backup is restored.

## Steps, in order

### 1. Set the environment variables on the new Railway web service

| Variable | Value |
|---|---|
| `SIMPLE_PUBLIC_URL` | this new app's own https URL, no trailing slash |
| `KOBO_WEBHOOK_SECRET` | the shared webhook secret (same string the hooks will send) |
| `FERNET_KEY` | the SAME key as the old instance, or encrypted PII cannot be read |
| `SECRET_KEY` | a Django secret key |
| `DATABASE_URL` | `${{ Postgres.DATABASE_URL }}` (the attached Postgres plugin) |

`FERNET_KEY` must be carried over exactly. Fistula and MPDSR data is encrypted with
it; a new key makes the restored data unreadable.

### 2. Restore the historical data

Restore the backup `.dump` into the new instance's Postgres (Postgres 18):

    pg_restore --no-owner --no-privileges -d "$DATABASE_URL" <backup>.dump

### 3. Repoint the Kobo hooks at the new instance

With a Kobo API token that owns the forms set as `KOBO_API_TOKEN` in the
environment, run (preview first):

    railway run python manage.py rewire_kobo_hooks --dry-run
    railway run python manage.py rewire_kobo_hooks

This adds or updates each form's hook so Kobo posts to `SIMPLE_PUBLIC_URL`, using
the secret this instance validates against. It is non-destructive by default: the
old deployment keeps receiving too, so nothing breaks during the transition.

When the old deployment is being retired, cut the old hooks over as well:

    railway run python manage.py rewire_kobo_hooks --cutover

### 4. Confirm

Submit one test record from Kobo (web form or KoboCollect) and confirm it lands in
this instance's pending-approval queue.

## Separate issue: KoboCollect "Error (404) at .../submission"

A 404 when a field phone uploads (`kf.kobotoolbox.org/submission`) is **not** about
this dashboard. It means the form is not deployed or not shared to the account the
KoboCollect app is logged into. Fix it on the Kobo side:

- Confirm the form is deployed on the account whose credentials the device uses.
- Re-share the form to that collector account, or re-issue the collect QR for the
  correct account (the QR must carry the account that owns the deployed form).
- Then re-finalise and resend the queued submission from the device.
