"""Re-file BaselineResponse rows stored under the wrong population.

Before the 2026-07-10 fix in baseline/populations.py, FSW interviews were saved
as Hijra (the asset UID carries no 'fsw'). The code was fixed but the rows
already written were never corrected: 20 FSW interviews from 9 Jul stayed
population='hijra' (found 2026-11-17: Hijra 692 vs 672 submissions, FSW 608
vs 628).

Each row is RE-DERIVED from its own submission with the current, shared
derive_fields(), so population AND every field derived through the
population-specific field names (serial, district, site code, age, outcome,
round) become exactly what a correct ingest would have stored. The duplicate
flag is recomputed inside the new population.

Takes the model class so a migration can pass its historical model.
Idempotent: rows that already agree with their submission are untouched.
"""
from submissions.flatten import flatten_group_keys

from .derive import derive_fields

DERIVED = ('population', 'survey_round', 'district', 'site_code', 'serial',
           'age', 'interview_outcome')


def refile_misfiled_populations(BaselineResponse, *, commit=True):
    """Return [(response_pk, old_population, new_population)] for every row
    whose stored population disagrees with its submission's form."""
    changed = []
    rows = (BaselineResponse.objects.select_related('submission')
            .exclude(submission__isnull=True))
    for r in rows:
        sub = r.submission
        raw = flatten_group_keys(sub.raw_data or {})
        d = derive_fields(raw, fallback_district=sub.district or '')
        new_pop = d['population']
        if new_pop is None or new_pop == r.population:
            continue
        changed.append((r.pk, r.population, new_pop))
        if not commit:
            continue
        r.population = new_pop
        r.survey_round = 'endline' if d['survey_round'] == 'endline' else 'baseline'
        for f in ('district', 'site_code', 'serial', 'age', 'interview_outcome'):
            setattr(r, f, d[f])
        dup = None
        if r.serial:
            dup = (BaselineResponse.objects
                   .filter(population=new_pop, survey_round=r.survey_round,
                           serial__iexact=r.serial)
                   .exclude(pk=r.pk).order_by('created_at').first())
        r.is_duplicate = bool(dup)
        r.duplicate_of = dup
        r.save(update_fields=list(DERIVED) + ['is_duplicate', 'duplicate_of'])

    if commit and changed:
        # A row in the OLD population may have been flagged as a duplicate OF a
        # row that has now moved away; that flag no longer holds.
        moved = [pk for pk, _, _ in changed]
        for r in BaselineResponse.objects.filter(duplicate_of__in=moved):
            if r.duplicate_of.population != r.population:
                r.is_duplicate = False
                r.duplicate_of = None
                r.save(update_fields=['is_duplicate', 'duplicate_of'])
    return changed
