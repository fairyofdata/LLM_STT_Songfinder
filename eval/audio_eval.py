"""Audio-path check: TTS -> whisper-1 -> lyric top-1 song.

    venv/Scripts/python eval/audio_eval.py            # cost estimate only
    venv/Scripts/python eval/audio_eval.py --run      # calls the OpenAI API

Takes one unambiguous seed-0 base line per song and, for each spoken query
type (typos are not meaningful when read aloud), reads the query with OpenAI
TTS, transcribes it with whisper-1 and runs the audio path on the transcript.
The key comes from the environment or .env (`openai`, as app.py reads it, or
OPENAI_API_KEY) and is never printed. Writes eval/results/audio.json with ids,
correctness, character error rate and clip length only; audio and transcripts
are not kept.
"""
import argparse
import datetime
import io
import json
import math
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO_ROOT, SongDB, normalize  # noqa: E402
import queries as Q  # noqa: E402

SPOKEN_TYPES = ['exact', 'half', 'word_drop']
TTS_MODEL, TTS_VOICE = 'tts-1', 'alloy'
TTS_USD_PER_1M_CHARS = 15.0
WHISPER_USD_PER_MIN = 0.006
SECONDS_PER_CHAR = 0.18   # rough speaking rate for estimating clip length
APP_MIN_SECONDS = 5.0     # app.py /stt rejects shorter recordings
MAX_USD = 1.0


def load_key():
    for name in ('openai', 'OPENAI_API_KEY'):
        if os.getenv(name):
            return os.getenv(name)
    path = os.path.join(REPO_ROOT, '.env')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                k, _, v = line.strip().partition('=')
                if k.strip() in ('openai', 'OPENAI_API_KEY') and v.strip():
                    return v.strip().strip('"').strip("'")
    return None


def cer(ref, hyp):
    ref, hyp = normalize(ref).replace(' ', ''), normalize(hyp).replace(' ', '')
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i]
        for j, hc in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / max(1, len(ref))


def select(db, types):
    """One base line per song (the first unambiguous one in seed 0), all requested types."""
    qs = Q.generate(db, 0)
    by_base = {}
    for q in qs:
        by_base.setdefault(q['id'].rsplit('-', 1)[0], {})[q['type']] = q
    chosen, seen_songs = [], set()
    for base_id in sorted(by_base, key=lambda b: (by_base[b]['exact']['song'], b)):
        group = by_base[base_id]
        song = group['exact']['song']
        if song in seen_songs or any(group[t]['ambiguous'] for t in types):
            continue
        seen_songs.add(song)
        chosen += [group[t] for t in types]
    return chosen


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def add_paired_comparison(path):
    """Join audio.json with seed_0.json by query id: typed vs spoken on the same queries."""
    with open(path, encoding='utf-8') as f:
        audio = json.load(f)
    with open(os.path.join(REPO_ROOT, 'eval', 'results', 'seed_0.json'), encoding='utf-8') as f:
        typed = {r['id']: r for r in json.load(f)['queries']}
    paired = {}
    for t in list(audio['by_type']) + ['pooled']:
        rs = [r for r in audio['queries'] if t == 'pooled' or r['type'] == t]
        text_ok = [typed[r['id']]['audio_path_pred'] == r['song'] for r in rs]
        paired[t] = {'n': len(rs),
                     'typed_accuracy': sum(text_ok) / len(rs),
                     'spoken_accuracy': sum(r['correct'] for r in rs) / len(rs),
                     'lost_by_speech': sum(ok and not r['correct'] for ok, r in zip(text_ok, rs)),
                     'gained_by_speech': sum(r['correct'] and not ok for ok, r in zip(text_ok, rs))}
    audio['paired_with_typed'] = paired
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(audio, f, indent=1)
    for t, p in paired.items():
        print(f"{t}: typed {p['typed_accuracy']:.3f} -> spoken {p['spoken_accuracy']:.3f} "
              f"(lost {p['lost_by_speech']}, gained {p['gained_by_speech']}, n={p['n']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', action='store_true')
    ap.add_argument('--paired', action='store_true', help='only add the typed-vs-spoken comparison to audio.json')
    ap.add_argument('--types', nargs='+', default=SPOKEN_TYPES, choices=Q.QUERY_TYPES)
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()
    out_path = os.path.join(REPO_ROOT, 'eval', 'results', 'audio.json')
    if args.paired:
        add_paired_comparison(out_path)
        return

    db = SongDB()
    sample = select(db, args.types)
    chars = sum(len(q['text']) for q in sample)
    minutes = sum(0.5 + SECONDS_PER_CHAR * len(q['text']) for q in sample) / 60
    usd = chars / 1e6 * TTS_USD_PER_1M_CHARS + minutes * WHISPER_USD_PER_MIN
    print(f'{len(sample)} clips ({len(sample) // len(args.types)} songs x {len(args.types)} types), '
          f'{chars} characters, ~{minutes:.1f} min audio -> estimated ${usd:.3f}')
    if not args.run:
        return
    if usd > MAX_USD:
        sys.exit(f'estimate above ${MAX_USD:.2f}; not running')
    key = load_key()
    if not key:
        sys.exit('no OpenAI key in environment or .env; not running')

    import openai
    client = openai.OpenAI(api_key=key, max_retries=5)

    def transcribe(q):
        speech = client.audio.speech.create(model=TTS_MODEL, voice=TTS_VOICE, input=q['text'])
        tr = client.audio.transcriptions.create(
            model='whisper-1', response_format='verbose_json',
            file=('query.mp3', io.BytesIO(speech.content), 'audio/mpeg'))
        return tr.text, float(tr.duration)

    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(transcribe, sample))

    hits = db.search(db.encode([text for text, _ in results]))
    rows = []
    for q, (text, seconds), hit in zip(sample, results, hits):
        ranking = hit['song_ranking']
        rows.append({'id': q['id'], 'type': q['type'], 'song': q['song'], 'src_lines': q['src_lines'],
                     'correct': db.identify_audio(hit) == q['song'],
                     'rank': ranking.index(q['song']) + 1 if q['song'] in ranking else None,
                     'cer': round(cer(q['text'], text), 4), 'seconds': round(seconds, 2)})

    def stats(rs):
        k = sum(r['correct'] for r in rs)
        return {'n': len(rs), 'audio_path_accuracy': k / len(rs), 'accuracy_95ci_wilson': wilson(k, len(rs)),
                'recall@10': sum(1 for r in rs if r['rank'] and r['rank'] <= 10) / len(rs),
                'median_cer': statistics.median(r['cer'] for r in rs),
                'median_seconds': statistics.median(r['seconds'] for r in rs),
                'share_shorter_than_app_minimum': sum(r['seconds'] < APP_MIN_SECONDS for r in rs) / len(rs)}

    total_seconds = sum(r['seconds'] for r in rows)
    out = {
        'generated': datetime.date.today().isoformat(),
        'tts_model': TTS_MODEL, 'tts_voice': TTS_VOICE, 'stt_model': 'whisper-1',
        'note': 'TTS reading of synthetic lyric queries, not human speech or singing; '
                f'app.py /stt rejects clips under {APP_MIN_SECONDS:.0f}s, this check does not',
        'cost_usd': {'estimated': round(usd, 4),
                     'actual': round(chars / 1e6 * TTS_USD_PER_1M_CHARS + total_seconds / 60 * WHISPER_USD_PER_MIN, 4)},
        'by_type': {t: stats([r for r in rows if r['type'] == t]) for t in args.types},
        'pooled': stats(rows),
        'queries': rows,
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    for t, s in list(out['by_type'].items()) + [('pooled', out['pooled'])]:
        print(f"{t}: accuracy {s['audio_path_accuracy']:.3f} {s['accuracy_95ci_wilson']} "
              f"R@10 {s['recall@10']:.3f} median CER {s['median_cer']:.3f} (n={s['n']})")
    print(f"cost ~${out['cost_usd']['actual']:.3f}")
    add_paired_comparison(out_path)


if __name__ == '__main__':
    main()
