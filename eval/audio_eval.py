"""Optional small audio-path check: TTS -> whisper-1 -> lyric top-1 song.

    venv/Scripts/python eval/audio_eval.py            # cost estimate only
    venv/Scripts/python eval/audio_eval.py --run      # calls the OpenAI API

Reads 50 unambiguous 'exact' seed-0 queries aloud with OpenAI TTS, transcribes
them with whisper-1 and runs the audio path on the transcript. The key comes
from the environment or .env (`openai`, as app.py reads it, or OPENAI_API_KEY)
and is never printed. Writes eval/results/audio.json with ids, correctness and
character error rate only; audio and transcripts are not kept.
"""
import argparse
import io
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO_ROOT, SongDB, normalize  # noqa: E402
import queries as Q  # noqa: E402

N_QUERIES = 50
TTS_MODEL, TTS_VOICE = 'tts-1', 'alloy'
TTS_USD_PER_1M_CHARS = 15.0
WHISPER_USD_PER_MIN = 0.006
SECONDS_PER_CHAR = 0.18   # rough speaking rate for estimating clip length
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', action='store_true')
    args = ap.parse_args()

    db = SongDB()
    qs = [q for q in Q.generate(db, 0) if q['type'] == 'exact' and not q['ambiguous']]
    by_song = {}
    for q in qs:
        by_song.setdefault(q['song'], q)
    sample = random.Random(2024).sample(sorted(by_song.values(), key=lambda q: q['song']), N_QUERIES)

    chars = sum(len(q['text']) for q in sample)
    minutes = sum(0.5 + SECONDS_PER_CHAR * len(q['text']) for q in sample) / 60
    usd = chars / 1e6 * TTS_USD_PER_1M_CHARS + minutes * WHISPER_USD_PER_MIN
    print(f'{N_QUERIES} clips, {chars} characters, ~{minutes:.1f} min audio -> estimated ${usd:.3f}')
    if not args.run:
        return
    if usd > MAX_USD:
        sys.exit(f'estimate above ${MAX_USD:.2f}; not running')
    key = load_key()
    if not key:
        sys.exit('no OpenAI key in environment or .env; not running')

    import openai
    client = openai.OpenAI(api_key=key)
    rows = []
    for q in sample:
        speech = client.audio.speech.create(model=TTS_MODEL, voice=TTS_VOICE, input=q['text'])
        transcript = client.audio.transcriptions.create(
            model='whisper-1', file=('query.mp3', io.BytesIO(speech.content), 'audio/mpeg')).text
        hit = db.search(db.encode([transcript]))[0]
        rows.append({'id': q['id'], 'song': q['song'], 'src_lines': q['src_lines'],
                     'correct': db.identify_audio(hit) == q['song'],
                     'cer': round(cer(q['text'], transcript), 4)})
    acc = sum(r['correct'] for r in rows) / len(rows)
    cers = sorted(r['cer'] for r in rows)
    out = {'n': len(rows), 'tts_model': TTS_MODEL, 'tts_voice': TTS_VOICE, 'stt_model': 'whisper-1',
           'audio_path_accuracy': acc, 'median_cer': cers[len(cers) // 2],
           'estimated_usd': round(usd, 4), 'queries': rows}
    with open(os.path.join(REPO_ROOT, 'eval', 'results', 'audio.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    print(f"audio path accuracy {acc:.3f} (n={len(rows)}), median CER {out['median_cer']:.3f}")


if __name__ == '__main__':
    main()
