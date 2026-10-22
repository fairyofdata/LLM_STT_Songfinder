"""Before/after on the shipped code: pre-refactor app logic (eval/common.py) vs search.py.

    venv/Scripts/python eval/compare_impl.py

Same inputs for both:
- typed queries of run_eval.py (5 seeds, unambiguous) through the text path
- summary-probe queries (each song's own summary) through the text path
- local-Whisper transcripts from audio_local_eval.py through the voice path, with
  the app's Korean -> Japanese retry emulated by taking the language='ja'
  transcript when Whisper detected Korean
- negative controls through the text path (threshold unchanged)

Writes eval/results/service_before_after.json (rates and paired tests only).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import REPO_ROOT, SongDB  # noqa: E402
from negatives import NEGATIVES  # noqa: E402
import queries as Q  # noqa: E402
from stats import mcnemar_exact  # noqa: E402
from search import SongIndex  # noqa: E402

RESULTS = os.path.join(REPO_ROOT, 'eval', 'results')


def paired(old_ok, new_ok):
    n = len(old_ok)
    return {'n': n, 'before': sum(old_ok) / n, 'after': sum(new_ok) / n, **mcnemar_exact(new_ok, old_ok)}


def main():
    old = SongDB()
    import numpy as np
    new = SongIndex(old.line_metadata, old.song_metadata, np.load(os.path.join(REPO_ROOT, 'line_embeddings.npy')),
                    np.load(os.path.join(REPO_ROOT, 'song_embeddings.npy')),
                    np.load(os.path.join(REPO_ROOT, 'summary_embeddings.npy')), old.embedder)
    out = {'note': 'only_a = right after the change only, only_b = right before only', 'text_path': {}}

    # typed queries, text path (threshold 0.4, as the app)
    for seed in range(5):
        qs = [q for q in Q.generate(old, seed) if not q['ambiguous']]
        hits = old.search(old.encode([q['text'] for q in qs]))
        for q, h in zip(qs, hits):
            q['old_ok'] = old.identify_text(h) == q['song']
            got = new.identify_text(q['text'])
            q['new_ok'] = got is not None and got['song'] == q['song']
        for t in Q.QUERY_TYPES + ['pooled']:
            sel = [q for q in qs if t == 'pooled' or q['type'] == t]
            out['text_path'].setdefault(t, []).append(paired([q['old_ok'] for q in sel], [q['new_ok'] for q in sel]))
        print(f'seed {seed} done')
    for t, runs in out['text_path'].items():
        out['text_path'][t] = {'seeds': runs,
                               'before_mean': sum(r['before'] for r in runs) / len(runs),
                               'after_mean': sum(r['after'] for r in runs) / len(runs),
                               'only_after_total': sum(r['only_a'] for r in runs),
                               'only_before_total': sum(r['only_b'] for r in runs)}

    # summary probe: each song's own summary as a text query
    songs = [i for i, m in enumerate(old.song_metadata) if m.get('summary')]
    texts = [old.song_metadata[i]['summary'] for i in songs]
    hits = old.search(old.encode(texts))
    out['summary_probe'] = paired([old.identify_text(h) == s for h, s in zip(hits, songs)],
                                  [(lambda g: g is not None and g['song'] == s)(new.identify_text(t))
                                   for t, s in zip(texts, songs)])

    # negatives: does the text path still say "found" for out-of-DB sentences?
    neg = [t for v in NEGATIVES.values() for t in v]
    out['negatives_false_accept'] = {
        'n': len(neg),
        'before': sum(old.identify_text(h) is not None for h in old.search(old.encode(neg))) / len(neg),
        'after': sum(new.identify_text(t) is not None for t in neg) / len(neg)}

    # voice path on cached local-Whisper transcripts
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'songfinder_eval', 'audio_local', 'transcripts.jsonl')
    if os.path.exists(cache):
        trans = {}
        with open(cache, encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                trans[r['key']] = r
        with open(os.path.join(RESULTS, 'audio_local.json'), encoding='utf-8') as f:
            rows = [r for r in json.load(f)['rows'] if not r['unsplit_line'] and r['lang_mode'] == 'auto']
        out['voice_path'] = {}
        for cond in 'ABCDS':
            for ch in ('clean', 'phone_reverb_noise'):
                sel = [r for r in rows if r['condition'] == cond and r['channel'] == ch]
                new_ok = []
                for r in sel:
                    key = r['id'].replace('|auto', '|ja') if r['detected_language'] == 'ko' else r['id']
                    new_ok.append(new.identify_transcript(trans[key]['text'] or ' ')['song'] == r['song'])
                out['voice_path'][f'{cond}|{ch}'] = paired([r['correct'] for r in sel], new_ok)
        out['voice_path_note'] = ('local Whisper large-v3 transcripts stand in for whisper-1; Korean -> Japanese '
                                  'retry emulated with the cached language=ja transcript')

    with open(os.path.join(RESULTS, 'service_before_after.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    for t, v in out['text_path'].items():
        print(f"text {t}: {v['before_mean'] * 100:.1f} -> {v['after_mean'] * 100:.1f} "
              f"(+{v['only_after_total']} / -{v['only_before_total']})")
    p = out['summary_probe']
    print(f"summary probe: {p['before'] * 100:.1f} -> {p['after'] * 100:.1f}")
    n = out['negatives_false_accept']
    print(f"negatives false accept: {n['before'] * 100:.1f} -> {n['after'] * 100:.1f}")
    for k, v in out.get('voice_path', {}).items():
        print(f"voice {k}: {v['before'] * 100:.1f} -> {v['after'] * 100:.1f} (+{v['only_a']} / -{v['only_b']})")


if __name__ == '__main__':
    main()
