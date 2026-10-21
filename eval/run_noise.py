"""Robustness curves: song-level recall vs word-level noise level.

    venv/Scripts/python eval/run_noise.py              # seeds 0-4
    venv/Scripts/python eval/run_noise.py --summarize  # rebuild the summary from saved seed files

Uses the same base lines as run_eval.py (the 'exact' queries of each seed)
and corrupts them with eval/perturb.py at several noise levels. Writes
eval/results/noise_seed_<n>.json (ids, indices, ranks; no text) and
eval/results/noise_summary.json.
"""
import argparse
import datetime
import json
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import MODEL_NAME, SongDB  # noqa: E402
import perturb as P  # noqa: E402
import queries as Q  # noqa: E402
from stats import cluster_bootstrap_ci  # noqa: E402

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')


def item_rng(seed, ptype, level, qid):
    return random.Random(f'{seed}|{ptype}|{level}|{qid}')


def generate(db, seed, res):
    bases = [q for q in Q.generate(db, seed) if q['type'] == 'exact']
    out = []
    for q in bases:
        for ptype in P.PERTURB_TYPES:
            for level in P.NOISE_LEVELS:
                out_ = P.perturb(q['text'], ptype, level, item_rng(seed, ptype, level, q['id']), res)
                if out_ is None:
                    continue
                text, changed = out_
                out.append({'id': f"{q['id'].rsplit('-', 1)[0]}-{ptype}-{int(level * 100)}",
                            'ptype': ptype, 'level': level, 'song': q['song'], 'src_lines': q['src_lines'],
                            'ambiguous': q['ambiguous'], 'script': q['script'],
                            'changed': round(changed, 4), 'text': text})
    return out


def metrics(rows):
    n = len(rows)
    if not n:
        return {'n': 0}
    ranks = [r['rank'] for r in rows]
    out = {'n': n, 'mean_changed': statistics.fmean(r['changed'] for r in rows)}
    for k in (1, 5, 10):
        out[f'recall@{k}'] = sum(1 for x in ranks if x is not None and x <= k) / n
    out['mrr'] = sum(1 / x for x in ranks if x is not None) / n
    return out


def mean_std(vals):
    vals = [v for v in vals if v is not None]
    return {'mean': statistics.fmean(vals), 'std': statistics.stdev(vals) if len(vals) > 1 else 0.0} if vals else None


def seed_metrics(rows):
    m = {}
    for ptype in P.PERTURB_TYPES:
        for level in P.NOISE_LEVELS:
            sel = [r for r in rows if r['ptype'] == ptype and r['level'] == level]
            m[f'{ptype}@{level}'] = {'unambiguous': metrics([r for r in sel if not r['ambiguous']]),
                                     'all': metrics(sel)}
    return m


def base_id(row):
    return row['id'].rsplit('-', 2)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2, 3, 4])
    ap.add_argument('--summarize', action='store_true', help='only rebuild noise_summary.json from seed files')
    args = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)

    if args.summarize:
        all_rows = []
        for seed in args.seeds:
            with open(os.path.join(RESULTS_DIR, f'noise_seed_{seed}.json'), encoding='utf-8') as f:
                all_rows.extend(json.load(f)['queries'])
        summarize(args.seeds, all_rows)
        return

    db = SongDB()
    res = P.Resources(m['line_text'] for m in db.line_metadata)

    all_rows = []
    for seed in args.seeds:
        qs = generate(db, seed, res)
        hits = db.search(db.encode([q['text'] for q in qs]))
        rows = []
        for q, h in zip(qs, hits):
            ranking = h['song_ranking']
            rows.append({k: q[k] for k in ('id', 'ptype', 'level', 'song', 'src_lines', 'ambiguous', 'script', 'changed')}
                        | {'rank': ranking.index(q['song']) + 1 if q['song'] in ranking else None,
                           'audio_path_pred': db.identify_audio(h)})
        m = seed_metrics(rows)
        with open(os.path.join(RESULTS_DIR, f'noise_seed_{seed}.json'), 'w', encoding='utf-8') as f:
            json.dump({'seed': seed, 'metrics': m, 'queries': rows}, f)
        print(f'seed {seed}: ' + ', '.join(
            f"{k} R@1={v['unambiguous']['recall@1']:.3f}" for k, v in m.items() if k.endswith('@0.4')))
        all_rows.extend(rows)
    summarize(args.seeds, all_rows)


def summarize(seeds, all_rows):
    per_seed = [seed_metrics([r for r in all_rows if r['id'].startswith(f's{seed}-')]) for seed in seeds]
    keys = list(per_seed[0])
    unamb = [r for r in all_rows if not r['ambiguous']]

    def hit_at(k):
        return lambda r: 1.0 if r['rank'] is not None and r['rank'] <= k else 0.0

    bootstrap, by_script = {}, {}
    for key in keys:
        ptype, level = key.split('@')
        sel = [r for r in unamb if r['ptype'] == ptype and r['level'] == float(level)]
        bootstrap[key] = {f'recall@{k}': cluster_bootstrap_ci(sel, hit_at(k)) for k in (1, 10)}
        by_script[key] = {}
        for sc in ('kana', 'kanji', 'latin'):
            ss = [r for r in sel if r['script'] == sc]
            by_script[key][sc] = {'n_all_seeds': len(ss),
                                  'recall@1': sum(map(hit_at(1), ss)) / len(ss) if ss else None}

    # types apply to different lines (e.g. homophone needs kanji); compare them on the
    # base lines where every type produced a query at every level
    combos = {(p, l) for p in P.PERTURB_TYPES for l in P.NOISE_LEVELS}
    seen = {}
    for r in unamb:
        seen.setdefault(base_id(r), set()).add((r['ptype'], r['level']))
    common = {b for b, c in seen.items() if c == combos}
    paired = {}
    for key in keys:
        ptype, level = key.split('@')
        sel = [r for r in unamb if base_id(r) in common and r['ptype'] == ptype and r['level'] == float(level)]
        paired[key] = {'n_all_seeds': len(sel),
                       'recall@1': sum(map(hit_at(1), sel)) / len(sel) if sel else None,
                       'recall@1_ci': cluster_bootstrap_ci(sel, hit_at(1)),
                       'recall@10': sum(map(hit_at(10), sel)) / len(sel) if sel else None,
                       'mean_changed': statistics.fmean(r['changed'] for r in sel) if sel else None}
    summary = {
        'generated': datetime.date.today().isoformat(),
        'model': MODEL_NAME, 'mlm': P.MLM_NAME, 'mlm_top_k': P.MLM_TOP_K,
        'seeds': seeds, 'noise_levels': P.NOISE_LEVELS,
        'design': {
            'base': 'the exact-line base queries of run_eval.py for the same seed',
            'unit': 'bunsetsu-like unit (content word + following particles/auxiliaries, UniDic via fugashi); '
                    'level r changes max(1, round(r*n)) of n units, leaving at least one; types that do not apply '
                    'to a unit skip it, and a query with no applicable unit is left out',
            'types': P.__doc__.split('Types')[1].strip(),
            'wordnet': P.WORDNET,
            'validity': 'synthetic corruption for robustness curves; plausibility as human misremembering is '
                        'checked separately by a human-rated sample (review_summary.json), not assumed',
        },
        'common_base_lines_all_seeds': {'n_base_lines': len(common), 'metrics': paired},
        'bootstrap_ci_unambiguous_all_seeds': bootstrap,
        'by_script_unambiguous_all_seeds': by_script,
        'metrics': {k: {sub: {mk: (mean_std([s[k][sub].get(mk) for s in per_seed]) if mk != 'n'
                                    else [s[k][sub]['n'] for s in per_seed])
                              for mk in per_seed[0][k][sub]}
                        for sub in ('unambiguous', 'all')} for k in keys},
    }
    with open(os.path.join(RESULTS_DIR, 'noise_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=1)


if __name__ == '__main__':
    main()
