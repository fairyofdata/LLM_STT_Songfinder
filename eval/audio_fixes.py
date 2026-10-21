"""Estimate two fixes for the voice path from the transcripts audio_local_eval.py already made.

    venv/Scripts/python eval/audio_fixes.py

1. ko -> ja fallback: keep Whisper's auto-detected transcript unless it detected
   Korean, then use the language='ja' transcript (one extra STT call, only then).
2. windowed search: split the transcript into line-sized windows, search each,
   and vote per song (sum of top-1 scores), instead of embedding the whole
   multi-line transcript against a line-level index. 'hybrid' adds the
   whole-transcript top-1 as one more vote weighted by sqrt(number of windows),
   so a one-line query is not hurt. The weight was picked among 0.5/1/2 on
   these same transcripts (1 = the simplest); confirm on held-out queries.

Reads transcripts from the local cache (outside the repo); writes
eval/results/audio_fixes.json with accuracies and paired tests only.
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audio_local_eval import CACHE_DIR, CONDITIONS, RESULT  # noqa: E402
from common import REPO_ROOT, SongDB  # noqa: E402
from stats import cluster_bootstrap_ci, mcnemar_exact  # noqa: E402

WINDOW_CHARS, STRIDE_CHARS = 14, 7   # median indexed line is 12 non-space chars


def windows(text):
    """Line-sized pieces: split at spaces/punctuation, merge pieces to >= WINDOW_CHARS,
    and fall back to sliding character windows for long unbroken runs."""
    pieces = [p for p in re.split(r'[\s、。,.!?！？「」]+', text) if p]
    out, cur = [], ''
    for p in pieces:
        cur += p
        if len(cur) >= WINDOW_CHARS:
            out.append(cur)
            cur = ''
    if cur:
        out.append(cur)
    final = []
    for w in out:
        if len(w) <= 2 * WINDOW_CHARS:
            final.append(w)
        else:
            final += [w[i:i + WINDOW_CHARS] for i in range(0, len(w) - WINDOW_CHARS // 2, STRIDE_CHARS)]
    return final or [text]


def windowed_predictions(db, texts, hybrid=False):
    flat, owner = [], []
    for i, t in enumerate(texts):
        for w in windows(t):
            flat.append(w)
            owner.append(i)
    hits = db.search(db.encode(flat))
    votes = [collections.defaultdict(float) for _ in texts]
    n_windows = collections.Counter(owner)
    for i, h in zip(owner, hits):
        votes[i][int(db.line_song[h['lyric_line_idx']])] += h['lyric_score']
    if hybrid:
        for i, h in enumerate(db.search(db.encode(texts))):
            votes[i][int(db.line_song[h['lyric_line_idx']])] += h['lyric_score'] * max(1, n_windows[i]) ** 0.5
    return [max(v, key=v.get) if v else None for v in votes]


def main():
    db = SongDB()
    with open(RESULT, encoding='utf-8') as f:
        rows = [r for r in json.load(f)['rows'] if not r['unsplit_line']]
    trans = {}
    with open(os.path.join(CACHE_DIR, 'transcripts.jsonl'), encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            trans[r['key']] = r
    by_key = {r['id']: r for r in rows}

    out = {'ko_to_ja_fallback': {}, 'windowed_search': {}}
    for cond in CONDITIONS:
        for ch in ('clean', 'phone_reverb_noise'):
            auto = [r for r in rows if r['condition'] == cond and r['channel'] == ch and r['lang_mode'] == 'auto']
            fb = []
            for r in auto:
                ja = by_key[r['id'].replace('|auto', '|ja')]
                fb.append(ja['correct'] if r['detected_language'] == 'ko' else r['correct'])
            base = [r['correct'] for r in auto]
            out['ko_to_ja_fallback'][f'{cond}|{ch}'] = {
                'n': len(auto), 'app_auto': sum(base) / len(auto), 'fallback': sum(fb) / len(auto),
                'extra_stt_calls_share': sum(r['detected_language'] == 'ko' for r in auto) / len(auto),
                'fallback_vs_app': mcnemar_exact(fb, base)}

    # windowed search on the app-like transcript (auto) and on the typed text of the same query
    sel = [r for r in rows if r['channel'] == 'clean' and r['lang_mode'] == 'auto']
    texts = [trans[r['id']]['text'] or ' ' for r in sel]
    preds = windowed_predictions(db, texts)
    hyb = windowed_predictions(db, texts, hybrid=True)
    for cond in CONDITIONS:
        idx = [i for i, r in enumerate(sel) if r['condition'] == cond]
        base = [sel[i]['correct'] for i in idx]
        win = [preds[i] == sel[i]['song'] for i in idx]
        hy = [hyb[i] == sel[i]['song'] for i in idx]
        rs = [dict(sel[i], hy=h) for i, h in zip(idx, hy)]
        out['windowed_search'][f'{cond}|clean|auto'] = {
            'n': len(idx), 'app_whole_transcript': sum(base) / len(idx), 'windowed_vote': sum(win) / len(idx),
            'hybrid': sum(hy) / len(idx), 'hybrid_ci': cluster_bootstrap_ci(rs, lambda r: 1.0 if r['hy'] else 0.0),
            'windowed_vs_app': mcnemar_exact(win, base), 'hybrid_vs_app': mcnemar_exact(hy, base)}

    # both fixes: ko -> ja fallback transcript, then hybrid voting
    def fallback_text(r):
        key = r['id'].replace('|auto', '|ja') if r['detected_language'] == 'ko' else r['id']
        return trans[key]['text'] or ' '
    for ch in ('clean', 'phone_reverb_noise'):
        chosen = [r for r in rows if r['channel'] == ch and r['lang_mode'] == 'auto']
        both = windowed_predictions(db, [fallback_text(r) for r in chosen], hybrid=True)
        for cond in CONDITIONS:
            idx = [i for i, r in enumerate(chosen) if r['condition'] == cond]
            base = [chosen[i]['correct'] for i in idx]
            ok = [both[i] == chosen[i]['song'] for i in idx]
            rs = [dict(chosen[i], ok=o) for i, o in zip(idx, ok)]
            out.setdefault('both_fixes', {})[f'{cond}|{ch}'] = {
                'n': len(idx), 'app': sum(base) / len(idx), 'both_fixes': sum(ok) / len(idx),
                'app_ci': cluster_bootstrap_ci([chosen[i] for i in idx], lambda r: 1.0 if r['correct'] else 0.0),
                'both_fixes_ci': cluster_bootstrap_ci(rs, lambda r: 1.0 if r['ok'] else 0.0),
                'both_vs_app': mcnemar_exact(ok, base)}

    # the same for typed multi-line text (no speech): is the line-level index the cause?
    from audio_local_eval import build_queries
    import perturb as P
    qs = {q['song']: q for q in build_queries(db, P.Resources(m['line_text'] for m in db.line_metadata))}
    songs = sorted({r['song'] for r in sel})
    for memory in ('exact', 'blurred'):
        texts = [qs[s]['text'][memory] for s in songs]
        whole = [db.identify_audio(h) == s for h, s in zip(db.search(db.encode(texts)), songs)]
        win = [p == s for p, s in zip(windowed_predictions(db, texts), songs)]
        hy = [p == s for p, s in zip(windowed_predictions(db, texts, hybrid=True), songs)]
        out['windowed_search'][f'typed_{memory}'] = {
            'n': len(songs), 'app_whole_text': sum(whole) / len(songs), 'windowed_vote': sum(win) / len(songs),
            'hybrid': sum(hy) / len(songs), 'windowed_vs_app': mcnemar_exact(win, whole),
            'hybrid_vs_app': mcnemar_exact(hy, whole)}
    # held-out check of the hybrid weight: typed multi-line queries built from other seeds' base lines
    import random
    import queries as Q
    from audio_local_eval import BLUR, UNSPLIT_CHARS, window
    res = P.Resources(m['line_text'] for m in db.line_metadata)
    for seed in (1, 2):
        bases = {q['song']: q for q in Q.generate(db, seed) if q['type'] == 'exact' and q['id'].endswith('-b0-exact')}
        wins = {s: window(db, s, b['src_lines'][0]) for s, b in bases.items()}
        songs = [s for s in sorted(wins) if all(Q.nonspace_len(db.line_text(x)) <= UNSPLIT_CHARS for x in wins[s])]
        exact = [' '.join(db.line_text(x).strip() for x in wins[s]) for s in songs]
        blurred = [(P.perturb(t, *BLUR, random.Random(f'heldout-blur|{seed}|{s}'), res) or (t, 0))[0]
                   for t, s in zip(exact, songs)]
        for memory, texts in (('exact', exact), ('blurred', blurred)):
            whole = [db.identify_audio(h) == s for h, s in zip(db.search(db.encode(texts)), songs)]
            hy = [p == s for p, s in zip(windowed_predictions(db, texts, hybrid=True), songs)]
            out['windowed_search'][f'heldout_seed{seed}_typed_{memory}'] = {
                'n': len(songs), 'app_whole_text': sum(whole) / len(songs), 'hybrid': sum(hy) / len(songs),
                'hybrid_vs_app': mcnemar_exact(hy, whole)}
    out['design'] = {'window_chars': WINDOW_CHARS, 'stride_chars': STRIDE_CHARS,
                     'vote': 'sum of top-1 lyric-line cosine per song across windows',
                     'hybrid': 'plus the whole-text top-1 cosine x sqrt(n windows); weight picked on these data',
                     'note': 'estimates from existing transcripts; app.py unchanged'}

    with open(os.path.join(REPO_ROOT, 'eval', 'results', 'audio_fixes.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    for part in ('ko_to_ja_fallback', 'windowed_search', 'both_fixes'):
        for k, v in out[part].items():
            vals = {kk: (round(vv * 100, 1) if isinstance(vv, float) else vv) for kk, vv in v.items()}
            print(part, k, vals)


if __name__ == '__main__':
    main()
