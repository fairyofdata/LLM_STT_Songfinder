"""Data-quality check of the lyric-line index and its effect on retrieval.

    venv/Scripts/python eval/data_quality.py

Counts outlier lines (unsplit lyrics, punctuation-only, very short), measures
which kinds of line attract wrong top-1 hits in run_eval.py's results, and
re-runs seed-0 queries against filtered copies of the index. app.py and the
data files are not changed. Writes eval/results/data_quality.json (counts,
indices and rates only).
"""
import collections
import json
import os
import re
import sys

import faiss
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO_ROOT, SongDB  # noqa: E402
from negatives import NEGATIVES  # noqa: E402
import queries as Q  # noqa: E402
from stats import mcnemar_exact  # noqa: E402

RESULTS = os.path.join(REPO_ROOT, 'eval', 'results')
UNSPLIT_CHARS = 100   # a "line" this long is several lines that were never split
SHORT_LIMITS = [2, 4, 6]


def nonspace(text):
    return len(re.sub(r'\s', '', text))


def kind(text):
    t = text.strip()
    if nonspace(t) > UNSPLIT_CHARS:
        return 'unsplit'
    if re.fullmatch(r'[\W_]+', t):
        return 'punct_only'
    if nonspace(t) <= 6:
        return 'short_le6'
    if re.fullmatch(r'[\[\(（【].*[\]\)）】]', t):
        return 'bracket_only'
    return 'normal'


def main():
    db = SongDB()
    lines = [m['line_text'] for m in db.line_metadata]
    kinds = [kind(t) for t in lines]
    n_lines = len(lines)
    per_song = collections.Counter(m['original_song_index'] for m in db.line_metadata)

    rows = []
    for s in range(5):
        with open(os.path.join(RESULTS, f'seed_{s}.json'), encoding='utf-8') as f:
            rows += [r for r in json.load(f)['queries'] if not r['ambiguous']]
    wrong = [r for r in rows if r['audio_path_pred'] != r['song']]
    right = [r for r in rows if r['audio_path_pred'] == r['song']]

    def share(rs):
        c = collections.Counter(kinds[r['lyric_line_idx']] for r in rs)
        return {k: round(v / len(rs), 4) for k, v in c.items()}

    unsplit = [i for i, k in enumerate(kinds) if k == 'unsplit']
    hub = collections.Counter(r['lyric_line_idx'] for r in wrong).most_common(10)
    out = {
        'index': {
            'lines': n_lines,
            'kinds': dict(collections.Counter(kinds)),
            'unsplit_lines': [{'line_idx': i, 'song': db.line_metadata[i]['original_song_index'],
                               'nonspace_chars': nonspace(lines[i])} for i in unsplit],
            'songs_with_one_line': sorted(s for s, n in per_song.items() if n == 1),
            'songs_without_lines': sorted(set(range(len(db.song_metadata))) - set(per_song)),
        },
        'top1_hit_line_kinds': {'index_share': {k: round(v / n_lines, 4) for k, v in collections.Counter(kinds).items()},
                                'wrong_top1': share(wrong), 'correct_top1': share(right),
                                'n_wrong': len(wrong), 'n_correct': len(right)},
        'top_wrong_hit_lines': [{'line_idx': i, 'wrong_hits': n, 'kind': kinds[i],
                                 'nonspace_chars': nonspace(lines[i])} for i, n in hub],
        'queries_from_unsplit_lines': sum(1 for r in rows if kinds[r['src_lines'][0]] == 'unsplit'),
    }

    # counterfactual: the same seed-0 queries against filtered copies of the line index
    qs = [q for q in Q.generate(db, 0) if not q['ambiguous']]
    truth = np.array([q['song'] for q in qs])
    qv = db.encode([q['text'] for q in qs])
    nv = db.encode([t for v in NEGATIVES.values() for t in v])
    emb = np.load(os.path.join(REPO_ROOT, 'line_embeddings.npy'))
    ns = np.array([nonspace(t) for t in lines])
    punct = np.array([k == 'punct_only' for k in kinds])
    base_ok = None
    out['filtered_index_seed0'] = {}
    for limit in [0] + SHORT_LIMITS:
        keep = np.arange(n_lines) if limit == 0 else np.where(~punct & (ns > limit))[0]
        ix = faiss.IndexFlatIP(emb.shape[1])
        ix.add(emb[keep])
        _, idx = ix.search(qv, 1)
        ok = db.line_song[keep[idx[:, 0]]] == truth
        dn, _ = ix.search(nv, 1)
        entry = {'lines_kept': int(len(keep)), 'songs_kept': int(len(set(db.line_song[keep]))),
                 'recall@1': round(float(ok.mean()), 4),
                 'recall@1_by_type': {t: round(float(ok[[q['type'] == t for q in qs]].mean()), 4)
                                      for t in Q.QUERY_TYPES},
                 'negatives_lyric_score_above_0.4': round(float((dn[:, 0] > 0.4).mean()), 4)}
        if base_ok is None:
            base_ok = ok
        else:
            entry['vs_full_index'] = mcnemar_exact(list(ok), list(base_ok))
        out['filtered_index_seed0']['full' if limit == 0 else f'drop_punct_and_le{limit}'] = entry
    out['filtered_index_seed0']['note'] = (
        'base lines of the queries have >= 8 non-space chars, so filtering never removes a query\'s own '
        'line; a user who remembers only a short line would lose it')

    with open(os.path.join(RESULTS, 'data_quality.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: out[k] for k in ('index', 'top1_hit_line_kinds')}, indent=1))
    for k, v in out['filtered_index_seed0'].items():
        if isinstance(v, dict):
            print(k, v['recall@1'], v.get('vs_full_index'))


if __name__ == '__main__':
    main()
