"""Human check of the perturbations: are they plausible misrememberings?

    venv/Scripts/python eval/review_sheet.py make      # writes the sheet OUTSIDE the repo
    venv/Scripts/python eval/review_sheet.py ingest    # reads ratings -> eval/results/review_summary.json

The sheet holds lyric text, so it lives in REVIEW_DIR (user cache), never in
the repo. Only ids, types and ratings come back into eval/results.
Rating: 2 = a person could plausibly misremember the line like this,
1 = borderline, 0 = mechanical / implausible.
"""
import csv
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO_ROOT, SongDB  # noqa: E402
import perturb as P  # noqa: E402
import queries as Q  # noqa: E402
from run_noise import item_rng  # noqa: E402
from stats import cluster_bootstrap_ci  # noqa: E402

REVIEW_DIR = os.path.join(os.path.expanduser('~'), '.cache', 'songfinder_eval', 'review')
SHEET = os.path.join(REVIEW_DIR, 'review_sheet_seed0.csv')
KEY = os.path.join(REVIEW_DIR, 'review_key_seed0.json')  # blind id -> query id and type
SEED, LEVEL = 0, 0.4
PER_TYPE = {'meaning_sub': 15, 'sound_sub': 15, 'function_change': 15, 'drop': 15,
            'context_sub': 15, 'homophone': 15, 'mixed': 10}
COLUMNS = ['no', 'original', 'perturbed', 'rating (0/1/2)', 'note']


def make():
    db = SongDB()
    res = P.Resources(m['line_text'] for m in db.line_metadata)
    bases = [q for q in Q.generate(db, SEED) if q['type'] == 'exact' and not q['ambiguous']]
    rng = random.Random(7)
    rows = []
    for ptype, n in PER_TYPE.items():
        picked = 0
        for q in rng.sample(bases, len(bases)):
            out = P.perturb(q['text'], ptype, LEVEL, item_rng(SEED, ptype, LEVEL, q['id']), res)
            if out is None:
                continue
            rows.append({'id': f"{q['id'].rsplit('-', 1)[0]}-{ptype}-{int(LEVEL * 100)}", 'type': ptype,
                         'song': q['song'], 'original': q['text'], 'perturbed': out[0]})
            picked += 1
            if picked == n:
                break
    random.Random(8).shuffle(rows)  # blind: the rater sees neither the type nor its order
    os.makedirs(REVIEW_DIR, exist_ok=True)
    key = {}
    with open(SHEET, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for i, r in enumerate(rows, 1):
            no = f'R{i:03d}'
            key[no] = {'id': r['id'], 'type': r['type'], 'song': r['song']}
            w.writerow([no, r['original'], r['perturbed'], '', ''])
    with open(KEY, 'w', encoding='utf-8') as f:
        json.dump(key, f, indent=1)
    print(f'{len(rows)} rows -> {SHEET}')


def ingest():
    with open(SHEET, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    with open(KEY, encoding='utf-8') as f:
        key = json.load(f)
    rated = []
    for r in rows:
        v = (r.get('rating (0/1/2)') or '').strip()
        if v in ('0', '1', '2'):
            k = key[r['no']]
            rated.append({'id': k['id'], 'type': k['type'], 'song': k['song'], 'rating': int(v)})
    out = {'sheet_rows': len(rows), 'rated': len(rated), 'by_type': {}}
    for t in list(PER_TYPE) + ['all']:
        rs = [r for r in rated if t == 'all' or r['type'] == t]
        if not rs:
            continue
        out['by_type'][t] = {
            'n': len(rs),
            'plausible_share': sum(r['rating'] == 2 for r in rs) / len(rs),
            'plausible_or_borderline_share': sum(r['rating'] >= 1 for r in rs) / len(rs),
            'plausible_share_ci': cluster_bootstrap_ci(rs, lambda r: 1.0 if r['rating'] == 2 else 0.0),
        }
    out['ratings'] = [{k: r[k] for k in ('id', 'type', 'rating')} for r in rated]
    path = os.path.join(REPO_ROOT, 'eval', 'results', 'review_summary.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    for t, v in out['by_type'].items():
        print(f"{t}: plausible {v['plausible_share']:.2f} (n={v['n']})")


if __name__ == '__main__':
    {'make': make, 'ingest': ingest}[sys.argv[1]]()
