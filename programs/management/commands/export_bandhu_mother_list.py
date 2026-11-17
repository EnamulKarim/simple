"""
Export the Bandhu Mother List as `mother_list.csv`, the person picker on the
live Bandhu Beneficiary Service Log (asset aMzxogjXhaE8FGdRhCjoe8).

That form reads this file twice:
  - `select_one_from_file mother_list.csv` for "Which person?", filtered by
    `centre = ${wellness_centre}` (the 2-digit Bandhu district code);
  - `pulldata('mother_list', <col>, 'name', ${person})` for label, tg,
    cruising_spot, age and father.

Before this module nothing in Spondon generated the file, so the form showed a
deploy-time snapshot and every later registration was missing from the picker
(field report 2026-11-17: Noakhali 04-0476..04-0592). It is now pushed on every
Bandhu Client change (programs/signals.py) and healed by resync_client_csvs.

Columns (order and names are read by the form; do not rename):
    name, label, centre, tg, cruising_spot, age, father, ml_id, source_kobo_id

    python manage.py export_bandhu_mother_list            # dry run
    python manage.py export_bandhu_mother_list --upload   # attach + redeploy
"""
import csv
import datetime
import io
import re

from django.core.management.base import BaseCommand

from programs._base_choices import BANDHU_DISTRICT_CODE
from programs.management.commands import export_bandhu_clients as _bandhu
from programs.models import Client

CSV_FILENAME = 'mother_list.csv'
FORM_UIDS = [
    ('aMzxogjXhaE8FGdRhCjoe8', 'Bandhu Beneficiary Service Log'),
]
HEADER = ['name', 'label', 'centre', 'tg', 'cruising_spot', 'age', 'father',
          'ml_id', 'source_kobo_id']
_DD_ID = re.compile(r'^(\d{2})-')

# Shared Kobo plumbing (token lookup, media replace, redeploy).
_kobo_token = _bandhu._kobo_token


def _centre_code(client) -> str:
    """The 2-digit district code the form filters on: the id's DD- prefix, or
    the client's centre district for an id kept verbatim without one."""
    m = _DD_ID.match(client.client_id or '')
    if m:
        return m.group(1)
    district = getattr(client.center, 'district', '') if client.center_id else ''
    return BANDHU_DISTRICT_CODE.get(district, '')


def _row(client, this_year):
    cid = _bandhu._norm_id(client.client_id)
    tg = (client.target_group_code or '').strip()
    return [
        cid,
        f'{cid} | {client.name}',
        _centre_code(client),
        tg.zfill(2) if tg.isdigit() else tg,
        (client.spot_name or '').strip(),
        (this_year - client.birth_year) if client.birth_year else '',
        (client.father_name or '').strip(),
        cid,
        client.kobo_submission_id or '',
    ]


def build_csv():
    """Generate the CSV in memory. Returns (csv_bytes, row_count).

    Same population as bandhu_clients.csv: APPROVED Bandhu clients with a real
    name (stubs from unregistered ids are left out)."""
    qs = (
        Client.objects
        .filter(organisation='Bandhu', approval_status=Client.APPROVED)
        .exclude(name='')
        .exclude(name='Unknown')
        .select_related('center')
        .order_by('client_id')
    )
    this_year = datetime.date.today().year
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(HEADER)
    count = 0
    for client in qs.iterator():
        writer.writerow(_row(client, this_year))
        count += 1
    return buf.getvalue().encode('utf-8'), count


def upload_to_kobo(csv_bytes: bytes, stdout) -> bool:
    return _bandhu.upload_media(FORM_UIDS, CSV_FILENAME, csv_bytes, stdout)


def redeploy_forms(stdout) -> bool:
    return _bandhu.redeploy_assets(FORM_UIDS, stdout)


class Command(BaseCommand):
    help = ('Export the Bandhu Mother List as mother_list.csv. With --upload, '
            'attach it to the live Beneficiary Service Log and redeploy.')

    def add_arguments(self, parser):
        parser.add_argument('--upload', action='store_true',
                            help='Attach the CSV to the form and redeploy.')

    def handle(self, *args, **options):
        csv_bytes, n = build_csv()
        self.stdout.write(f'  {n} client(s), {len(csv_bytes)} bytes')
        if not options['upload']:
            self.stdout.write('  (dry run — pass --upload to push to Kobo)')
            return
        if upload_to_kobo(csv_bytes, self.stdout):
            redeploy_forms(self.stdout)
        self.stdout.write(self.style.SUCCESS('  done'))
