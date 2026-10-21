"""Song-identification evaluation for Songfinder.

    venv/Scripts/python eval/run_eval.py            # seeds 0-4

Writes eval/results/seed_<n>.json (per-query raw records, no query text),
eval/results/negatives.json, eval/results/summary_probe.json and
eval/results/summary.json.
"""
import argparse
import datetime
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RANK_DEPTH, TEXT_THRESHOLD, MODEL_NAME, SongDB, normalize  # noqa: E402
from negatives import NEGATIVES  # noqa: E402
from stats import cluster_bootstrap_ci  # noqa: E402
import queries as Q  # noqa: E402

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
THRESHOLDS = [round(0.30 + 0.05 * i, 2) for i in range(13)]  # 0.30 .. 0.90
SUBSETS = ['unambiguous', 'ambiguous', 'all']


def record(q, hit, db):
    ranking = hit['song_ranking']
    rank = ranking.index(q['song']) + 1 if q['song'] in ranking else None
    return {
        'id': q['id'], 'type': q['type'], 'song': q['song'], 'src_lines': q['src_lines'],
        'ambiguous': q['ambiguous'], 'script': q['script'], 'rank': rank,
        'lyric_score': round(hit['lyric_score'], 6), 'lyric_line_idx': hit['lyric_line_idx'],
        'summary_score': round(hit['summary_score'], 6), 'summary_idx': hit['summary_idx'],
        'audio_path_pred': db.identify_audio(hit),
        'text_path_pred_current': db.identify_text(hit),
        'text_path_pred_fixed': db.identify_text(hit, fixed=True),
    }


def text_path_stats(rows, db, threshold):
    n = len(rows)
    accepted = correct_cur = correct_fix = summary_wins = 0
    for r in rows:
        hit = {k: r[k] for k in ('lyric_score', 'lyric_line_idx', 'summary_score', 'summary_idx')}
        cur = db.identify_text(hit, threshold)
        if cur is None:
            continue
        accepted += 1
        summary_wins += r['summary_score'] > r['lyric_score']
        correct_cur += cur == r['song']
        correct_fix += db.identify_text(hit, threshold, fixed=True) == r['song']
    return {
        'pass_rate': accepted / n if n else None,
        'accuracy_current': correct_cur / n if n else None,
        'accuracy_fixed': correct_fix / n if n else None,
        'precision_current': correct_cur / accepted if accepted else None,
        'precision_fixed': correct_fix / accepted if accepted else None,
        'summary_win_share': summary_wins / accepted if accepted else None,
    }


def metrics(rows, db):
    n = len(rows)
    if not n:
        return {'n': 0}
    ranks = [r['rank'] for r in rows]
    out = {'n': n}
    for k in (1, 5, 10):
        out[f'recall@{k}'] = sum(1 for x in ranks if x is not None and x <= k) / n
    out['mrr'] = sum(1 / x for x in ranks if x is not None) / n
    out['audio_path_accuracy'] = sum(r['audio_path_pred'] == r['song'] for r in rows) / n
    out.update({f'text_path_{k}': v for k, v in text_path_stats(rows, db, TEXT_THRESHOLD).items()})
    return out


def subset(rows, name):
    if name == 'all':
        return rows
    return [r for r in rows if r['ambiguous'] == (name == 'ambiguous')]


def seed_metrics(rows, db):
    out = {}
    for s in SUBSETS:
        rs = subset(rows, s)
        out[s] = {t: metrics([r for r in rs if r['type'] == t], db) for t in Q.QUERY_TYPES}
        out[s]['pooled'] = metrics(rs, db)
    return out


def mean_std(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {'mean': statistics.fmean(values),
            'std': statistics.stdev(values) if len(values) > 1 else 0.0}


def aggregate(per_seed):
    """per_seed: list of nested dicts with identical keys -> same shape of {mean, std} (n: per-seed list)."""
    dicts = [d for d in per_seed if isinstance(d, dict)]
    if dicts:
        keys = list(dict.fromkeys(k for d in dicts for k in d))
        return {k: aggregate([d.get(k) for d in dicts]) for k in keys}
    if all(isinstance(v, int) for v in per_seed if v is not None):
        return per_seed
    return mean_std(per_seed)


def run_negatives(db):
    items = []
    for lang, sentences in NEGATIVES.items():
        for i, text in enumerate(sentences):
            if normalize(text) in db.songs_by_text:
                continue  # an indexed line; not a valid negative
            items.append({'id': f'neg-{lang}-{i}', 'lang': lang, 'text': text})
    hits = db.search(db.encode([it['text'] for it in items]))
    rows = []
    for it, hit in zip(items, hits):
        rows.append({
            'id': it['id'], 'lang': it['lang'],
            'lyric_score': round(hit['lyric_score'], 6),
            'summary_score': round(hit['summary_score'], 6),
            'summary_idx': hit['summary_idx'], 'lyric_line_idx': hit['lyric_line_idx'],
        })
    return rows


def run_summary_probe(db):
    """Queries that reach the summary branch of the text path: each song's own
    summary (full, and its first half). Shows what the line_metadata[summary_idx]
    lookup does when the summary hit wins; seed-independent."""
    items = []
    for song, meta in enumerate(db.song_metadata):
        summary = (meta.get('summary') or '').strip()
        if summary:
            items.append({'id': f'sum-song{song}-full', 'song': song, 'text': summary})
            items.append({'id': f'sum-song{song}-half', 'song': song, 'text': Q.make_half(summary)})
    hits = db.search(db.encode([it['text'] for it in items]))
    rows = []
    for it, hit in zip(items, hits):
        rows.append({'id': it['id'], 'song': it['song'],
                     'summary_wins': hit['summary_score'] > hit['lyric_score'],
                     'text_path_pred_current': db.identify_text(hit),
                     'text_path_pred_fixed': db.identify_text(hit, fixed=True)})
    out = {}
    for kind in ('full', 'half'):
        rs = [r for r in rows if r['id'].endswith(kind)]
        out[kind] = {
            'n': len(rs),
            'summary_win_share': sum(r['summary_wins'] for r in rs) / len(rs),
            'accuracy_current': sum(r['text_path_pred_current'] == r['song'] for r in rs) / len(rs),
            'accuracy_fixed': sum(r['text_path_pred_fixed'] == r['song'] for r in rs) / len(rs),
            'distinct_songs_returned_current': len({r['text_path_pred_current'] for r in rs} - {None}),
        }
    return out, rows


def quantiles(xs):
    xs = sorted(xs)
    return {f'p{int(p * 100)}': round(xs[round(p * (len(xs) - 1))], 4) for p in (0.05, 0.25, 0.5, 0.75, 0.95)}


def false_accept(rows, threshold):
    if not rows:
        return None
    return sum(1 for r in rows if max(r['summary_score'], r['lyric_score']) > threshold) / len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2, 3, 4])
    args = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)

    db = SongDB()
    per_seed, raw_by_seed = [], {}
    for seed in args.seeds:
        qs = Q.generate(db, seed)
        hits = db.search(db.encode([q['text'] for q in qs]))
        assert min(len(h['song_ranking']) for h in hits) >= 10, 'RANK_DEPTH too small for Recall@10'
        rows = [record(q, h, db) for q, h in zip(qs, hits)]
        m = seed_metrics(rows, db)
        with open(os.path.join(RESULTS_DIR, f'seed_{seed}.json'), 'w', encoding='utf-8') as f:
            json.dump({'seed': seed, 'metrics': m, 'queries': rows}, f, ensure_ascii=False)
        per_seed.append(m)
        raw_by_seed[seed] = rows
        p = m['unambiguous']['pooled']
        print(f"seed {seed}: {len(rows)} queries ({p['n']} unambiguous) "
              f"R@1={p['recall@1']:.3f} R@10={p['recall@10']:.3f} "
              f"text acc current={p['text_path_accuracy_current']:.3f} fixed={p['text_path_accuracy_fixed']:.3f}")

    neg = run_negatives(db)
    with open(os.path.join(RESULTS_DIR, 'negatives.json'), 'w', encoding='utf-8') as f:
        json.dump(neg, f, ensure_ascii=False, indent=1)
    langs = sorted({r['lang'] for r in neg})
    negatives_summary = {
        'n': len(neg),
        'n_by_lang': {l: sum(r['lang'] == l for r in neg) for l in langs},
        'false_accept_rate': false_accept(neg, TEXT_THRESHOLD),
        'false_accept_rate_by_lang': {l: false_accept([r for r in neg if r['lang'] == l], TEXT_THRESHOLD) for l in langs},
        'summary_win_share_when_accepted': (
            lambda acc: sum(r['summary_score'] > r['lyric_score'] for r in acc) / len(acc) if acc else None
        )([r for r in neg if max(r['summary_score'], r['lyric_score']) > TEXT_THRESHOLD]),
    }

    probe_summary, probe_rows = run_summary_probe(db)
    with open(os.path.join(RESULTS_DIR, 'summary_probe.json'), 'w', encoding='utf-8') as f:
        json.dump({'metrics': probe_summary, 'queries': probe_rows}, f, ensure_ascii=False, indent=1)

    pos = [r for seed in args.seeds for r in subset(raw_by_seed[seed], 'unambiguous')]
    score_quantiles = {
        'positives_top1_correct_lyric_score': quantiles([r['lyric_score'] for r in pos if r['audio_path_pred'] == r['song']]),
        'positives_top1_wrong_lyric_score': quantiles([r['lyric_score'] for r in pos if r['audio_path_pred'] != r['song']]),
        'positives_summary_score': quantiles([r['summary_score'] for r in pos]),
        'negatives_lyric_score': quantiles([r['lyric_score'] for r in neg]),
        'negatives_summary_score': quantiles([r['summary_score'] for r in neg]),
    }

    def hit_at(k):
        return lambda r: 1.0 if r['rank'] is not None and r['rank'] <= k else 0.0

    bootstrap = {}
    for t in Q.QUERY_TYPES + ['pooled']:
        rs = [r for r in pos if t == 'pooled' or r['type'] == t]
        bootstrap[t] = {f'recall@{k}': cluster_bootstrap_ci(rs, hit_at(k)) for k in (1, 5, 10)}
    by_script = {}
    for sc in ('kana', 'kanji', 'latin'):
        by_script[sc] = {}
        for t in Q.QUERY_TYPES + ['pooled']:
            rs = [r for r in pos if r['script'] == sc and (t == 'pooled' or r['type'] == t)]
            by_script[sc][t] = {'n_all_seeds': len(rs),
                                'recall@1': sum(map(hit_at(1), rs)) / len(rs) if rs else None,
                                'recall@1_ci': cluster_bootstrap_ci(rs, hit_at(1)),
                                'recall@10': sum(map(hit_at(10), rs)) / len(rs) if rs else None}

    sweep = []
    for t in THRESHOLDS:
        entry = {'threshold': t, 'negative_false_accept_rate': false_accept(neg, t)}
        for s in ('unambiguous', 'all'):
            entry[s] = aggregate([text_path_stats(subset(raw_by_seed[seed], s), db, t) for seed in args.seeds])
        sweep.append(entry)

    summary = {
        'generated': datetime.date.today().isoformat(),
        'model': MODEL_NAME,
        'seeds': args.seeds,
        'n_songs_with_lines': len(db.lines_by_song),
        'n_lines': len(db.line_metadata),
        'text_threshold': TEXT_THRESHOLD,
        'design': {
            'query_source': 'synthetic queries generated from indexed lyric lines (not real user queries)',
            'base_lines_per_song': Q.LINES_PER_SONG,
            'min_base_nonspace_chars': Q.MIN_BASE_CHARS,
            'query_types': {
                'exact': 'base line as indexed',
                'half': 'first half of the characters',
                'word_drop': f'{int(Q.WORD_DROP_RATE * 100)}% of word-like units removed (whitespace tokens if 3+, else script runs)',
                'typo': f'~{int(Q.TYPO_RATE * 100)}% of non-space characters edited (insert/delete/substitute, same script)',
                'concat': 'second half of a line + first half of the adjacent line in the same song',
            },
            'ambiguous': 'a source line, or the query itself, matches (normalized) a line of another song',
            'uncertainty': 'mean +- SD over seeds (line sampling); bootstrap_ci: 95% CI resampling songs (2000x) over all seeds pooled',
            'script': 'base line letters: latin majority, else Japanese with kanji (kanji) or without (kana)',
            'ranking': f'top-{RANK_DEPTH} lyric-line hits grouped by song, first occurrence order; MRR counts songs beyond that as 0',
            'text_path': 'app.py search_pipeline_from_text: summary top-1 vs lyric top-1, accept if either > threshold',
            'text_path_variants': {
                'current': "as written: summary win -> line_metadata[summary_idx]['original_song_index']",
                'fixed': 'summary win -> summary_idx',
            },
            'audio_path': 'app.py search_pipeline_from_audio on the typed query (= perfect transcription): lyric top-1 song, no threshold',
        },
        'queries_per_seed': {str(s): len(raw_by_seed[s]) for s in args.seeds},
        'metrics': aggregate(per_seed),
        'bootstrap_ci_unambiguous_all_seeds': bootstrap,
        'by_script_unambiguous_all_seeds': by_script,
        'negatives': negatives_summary,
        'summary_probe': probe_summary,
        'score_quantiles': score_quantiles,
        'threshold_sweep': sweep,
    }
    with open(os.path.join(RESULTS_DIR, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(f"negatives: n={len(neg)} false accept @ {TEXT_THRESHOLD} = {negatives_summary['false_accept_rate']:.3f}")
    for kind, v in probe_summary.items():
        print(f"summary probe ({kind}): summary wins {v['summary_win_share']:.3f}, "
              f"accuracy current={v['accuracy_current']:.3f} fixed={v['accuracy_fixed']:.3f}")


if __name__ == '__main__':
    main()
