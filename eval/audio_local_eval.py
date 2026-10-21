"""Audio-path evaluation with local TTS/STT (LocalTTS server), app-length queries.

    venv/Scripts/python eval/audio_local_eval.py            # needs the LocalTTS server
    venv/Scripts/python eval/audio_local_eval.py --score    # re-score from the local cache only

One query per song: consecutive lines (>= 55 non-space chars, at most 6) starting
at the song's first seed-0 base line, so the speech lasts roughly 6-15 s like a
real /stt request. Clips shorter than the app's 5 s minimum get trailing
silence, as a recording would; speech length is reported separately.
Four conditions, paired per song:
    A  exact lyric    x native Japanese TTS (18 voices: Kokoro x5, Supertonic x10, Windows x3)
    B  exact lyric    x Korean-speaker reading (Hangul transliteration, 11 Korean voices:
                        Supertonic x10, Windows Heami)
    C  blurred lyric  x native Japanese TTS
    D  blurred lyric  x Korean-speaker reading
plus S: only the single base line, native TTS at normal speed (padded the
same way; a user who remembers one line).
'blurred' = perturb.py 'mixed' at 40% of word units. Each song keeps one
native voice for A/C/S and one Korean voice and reading style for B/D.
Each clip is transcribed clean and through a channel model (reverb, pink
noise, phone band), with Whisper large-v3 detecting the language (as app.py)
and with language='ja'.

Audio and transcripts stay in CACHE_DIR (outside the repo, they contain
lyrics). eval/results/audio_local.json keeps ids, settings and scores only.
"""
import argparse
import io
import json
import os
import random
import statistics
import sys
import urllib.error
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO_ROOT, SongDB, normalize  # noqa: E402
import perturb as P  # noqa: E402
import queries as Q  # noqa: E402
from stats import cluster_bootstrap_ci, mcnemar_exact  # noqa: E402

SERVER = os.getenv('LOCALTTS_URL', 'http://127.0.0.1:8880')
CACHE_DIR = os.path.join(os.path.expanduser('~'), '.cache', 'songfinder_eval', 'audio_local')
RESULT = os.path.join(REPO_ROOT, 'eval', 'results', 'audio_local.json')

ST_VOICES = [f'st_{g}{i}' for g in 'MF' for i in range(1, 6)]
JP_VOICES = ['jf_alpha', 'jf_gongitsune', 'jf_nezumi', 'jf_tebukuro', 'jm_kumo',
             'win_ayumi', 'win_haruka', 'win_ichiro'] + ST_VOICES
KO_VOICES = ST_VOICES + ['win_heami']
CONDITIONS = {'A': ('exact', 'native'), 'B': ('exact', 'korean'), 'C': ('blurred', 'native'),
              'D': ('blurred', 'korean'), 'S': ('single', 'native')}
BLUR = ('mixed', 0.4)
UNSPLIT_CHARS = 100  # same cut as data_quality.py
MIN_CHARS, MAX_LINES = 55, 6  # Japanese TTS reads ~8 chars/s -> roughly 6-15 s of speech
CHANNELS = ['clean', 'phone_reverb_noise']
LANG_MODES = {'auto': None, 'ja': 'ja'}
SR = 16000
APP_MIN_SECONDS = 5.0


# ---------- query construction ----------

def window(db, song, start_line):
    lines = db.lines_by_song[song]
    i = lines.index(start_line)
    chosen = [start_line]
    j, k = i + 1, i - 1
    while sum(Q.nonspace_len(db.line_text(x)) for x in chosen) < MIN_CHARS and len(chosen) < MAX_LINES:
        if j < len(lines):
            chosen.append(lines[j])
            j += 1
        elif k >= 0:
            chosen.insert(0, lines[k])
            k -= 1
        else:
            break
    return chosen


def build_queries(db, res):
    bases = {q['song']: q for q in Q.generate(db, 0) if q['type'] == 'exact' and q['id'].endswith('-b0-exact')}
    out = []
    for song in sorted(bases):
        lines = window(db, song, bases[song]['src_lines'][0])
        exact = ' '.join(db.line_text(x).strip() for x in lines)
        rng = random.Random(f'audio|{song}')
        blurred = P.perturb(exact, *BLUR, random.Random(f'blur|{song}'), res)
        style = {'tsu': rng.choice(['ㅊ', 'ㅅ', 'ㅉ']), 'initial': rng.choice(['aspirated', 'plain']),
                 'long_vowel': rng.choice(['drop', 'keep']), 'n_assim': rng.random() < 0.5}
        out.append({
            'song': song, 'lines': lines,
            'shared_line': any(db.text_in_other_song(db.line_text(x), song) for x in lines),
            # a "line" this long is unsplit lyrics (data defect); the clip would exceed Whisper's 30 s
            'unsplit_line': any(Q.nonspace_len(db.line_text(x)) > UNSPLIT_CHARS for x in lines),
            'script': Q.script_class(exact),
            'text': {'exact': exact, 'blurred': blurred[0] if blurred else None,
                     'single': db.line_text(bases[song]['src_lines'][0]).strip()},
            'blur_changed': round(blurred[1], 4) if blurred else None,
            'jp_voice': rng.choice(JP_VOICES),
            'ko': {'voice': rng.choice(KO_VOICES), 'style': style, 'pitch': rng.choice([0.85, 1.0, 1.15]),
                   'speed': rng.choice([0.9, 1.0, 1.1])},
        })
    return out


# ---------- LocalTTS client ----------

def _post_json(path, payload):
    req = urllib.request.Request(SERVER + path, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=900) as r:
        return r.read()


def tts(q, cond):
    memory, speaker = CONDITIONS[cond]
    text = q['text'][memory]
    payload = {'input': text, 'response_format': 'wav'}
    if speaker == 'native':
        payload.update(voice=q['jp_voice'], lang='ja')
    else:
        payload.update(voice=q['ko']['voice'], translit='ja_to_hangul', translit_style=q['ko']['style'],
                       pitch=q['ko']['pitch'], speed=q['ko']['speed'])
    return _post_json('/v1/audio/speech', payload)


# ---------- audio ----------

def read_wav(data):
    import soundfile as sf
    from scipy.signal import resample_poly
    audio, sr = sf.read(io.BytesIO(data), dtype='float32')
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SR:
        g = np.gcd(sr, SR)
        audio = resample_poly(audio, SR // g, sr // g).astype('float32')
    return audio


def wav_bytes(audio):
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, np.clip(audio, -1, 1).astype('float32'), SR, format='WAV', subtype='PCM_16')
    return buf.getvalue()


def degrade(audio, rng):
    """Room reverb (synthetic exponential RIR) + pink noise + telephone band (300-3400 Hz, 8 kHz)."""
    from scipy.signal import butter, fftconvolve, resample_poly, sosfiltfilt
    rt60 = rng.uniform(0.2, 0.6)
    n = int(rt60 * SR)
    t = np.arange(n) / SR
    nrng = np.random.default_rng(rng.randrange(2 ** 32))
    rir = nrng.standard_normal(n) * np.exp(-6.9 * t / rt60)
    rir[0] = 1.0
    wet = fftconvolve(audio, rir)[:len(audio)]
    wet *= np.max(np.abs(audio)) / (np.max(np.abs(wet)) + 1e-9)
    snr = rng.uniform(10, 20)
    white = nrng.standard_normal(len(wet))
    spec = np.fft.rfft(white)
    spec /= np.sqrt(np.arange(1, len(spec) + 1))
    pink = np.fft.irfft(spec, len(wet))
    pink *= np.sqrt(np.mean(wet ** 2) / (np.mean(pink ** 2) + 1e-12) / 10 ** (snr / 10))
    noisy = wet + pink
    sos = butter(4, [300, 3400], btype='bandpass', fs=SR, output='sos')
    phone = resample_poly(resample_poly(sosfiltfilt(sos, noisy), 1, 2), 2, 1)[:len(noisy)]
    phone *= 0.9 / (np.max(np.abs(phone)) + 1e-9)
    return phone.astype('float32'), {'rt60': round(rt60, 3), 'snr_db': round(snr, 1)}


# ---------- scoring helpers ----------

def letter_shares(text):
    hangul = sum(1 for c in text if '가' <= c <= '힣')
    ja = sum(1 for c in text if '぀' <= c <= 'ヿ' or '一' <= c <= '鿿')
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    total = max(1, hangul + ja + latin)
    return {'hangul': round(hangul / total, 3), 'japanese': round(ja / total, 3), 'latin': round(latin / total, 3)}


def cer(ref, hyp):
    ref, hyp = normalize(ref).replace(' ', ''), normalize(hyp).replace(' ', '')
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i]
        for j, hc in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / max(1, len(ref))


# ---------- main ----------

def _clip(cid, cond, ch):
    with open(os.path.join(CACHE_DIR, 'wav', cid + '.wav'), 'rb') as f:
        audio = read_wav(f.read())
    seconds = round(len(audio) / SR, 2)  # speech length, before padding
    if len(audio) < APP_MIN_SECONDS * SR:
        audio = np.concatenate([audio, np.zeros(int(APP_MIN_SECONDS * SR) - len(audio), 'float32')])
    aug = {}
    if ch != 'clean':
        audio, aug = degrade(audio, random.Random(f'aug|{cid}'))
    return audio, seconds, aug


def run(db, qs, batch=32):
    import base64
    os.makedirs(os.path.join(CACHE_DIR, 'wav'), exist_ok=True)
    clips = []
    for qi, q in enumerate(qs):
        for cond, (memory, _) in CONDITIONS.items():
            if q['text'][memory] is None:
                continue
            cid = f"song{q['song']}-{cond}"
            wav_path = os.path.join(CACHE_DIR, 'wav', cid + '.wav')
            if not os.path.exists(wav_path):
                try:
                    data = tts(q, cond)
                except urllib.error.HTTPError as e:  # the body may quote lyrics: log the id only
                    print(f'tts failed for {cid}: HTTP {e.code}', flush=True)
                    continue
                with open(wav_path, 'wb') as f:
                    f.write(data)
            clips.append((cid, cond))
        if qi % 50 == 0:
            print(f'tts {qi + 1}/{len(qs)} songs', flush=True)

    log_path = os.path.join(CACHE_DIR, 'transcripts.jsonl')
    done = set()
    if os.path.exists(log_path):
        with open(log_path, encoding='utf-8') as f:
            done = {json.loads(l)['key'] for l in f}
    with open(log_path, 'a', encoding='utf-8') as log:
        for ch in CHANNELS:
            for lang_name, lang in LANG_MODES.items():
                todo = [(cid, cond) for cid, cond in clips if f'{cid}|{ch}|{lang_name}' not in done]
                for i in range(0, len(todo), batch):
                    part = todo[i:i + batch]
                    prepared = [_clip(cid, cond, ch) for cid, cond in part]
                    payload = {'files_b64': [base64.b64encode(wav_bytes(a)).decode() for a, _, _ in prepared],
                               'language': lang, 'batch_size': 8}
                    results = json.loads(_post_json('/v1/batch/transcriptions', payload))['results']
                    for (cid, _), (_, seconds, aug), out in zip(part, prepared, results):
                        log.write(json.dumps({'key': f'{cid}|{ch}|{lang_name}', 'text': out['text'],
                                              'language': out['language'], 'seconds': seconds, 'aug': aug},
                                             ensure_ascii=False) + '\n')
                    log.flush()
                    print(f'stt {ch}/{lang_name} {min(i + batch, len(todo))}/{len(todo)}', flush=True)


def score(db, qs):
    log_path = os.path.join(CACHE_DIR, 'transcripts.jsonl')
    with open(log_path, encoding='utf-8') as f:
        trans = {}
        for l in f:
            r = json.loads(l)
            trans[r['key']] = r
    by_song = {q['song']: q for q in qs}

    # typed baseline: the condition's Japanese text typed into the search box
    typed_keys = [(q['song'], m) for q in qs for m in ('exact', 'blurred', 'single') if q['text'][m]]
    typed_hits = db.search(db.encode([by_song[s]['text'][m] for s, m in typed_keys]))
    typed_ok = {(s, m): db.identify_audio(h) == s for (s, m), h in zip(typed_keys, typed_hits)}

    keys = sorted(trans)
    hits = db.search(db.encode([trans[k]['text'] or ' ' for k in keys]))
    rows = []
    for k, h in zip(keys, hits):
        cid, ch, lang_name = k.split('|')
        song, cond = int(cid.split('-')[0][4:]), cid.split('-')[1]
        q = by_song[song]
        memory, speaker = CONDITIONS[cond]
        t = trans[k]
        ranking = h['song_ranking']
        rows.append({
            'id': k, 'song': song, 'condition': cond, 'memory': memory, 'speaker': speaker,
            'channel': ch, 'lang_mode': lang_name, 'detected_language': t['language'],
            'voice': q['jp_voice'] if speaker == 'native' else q['ko']['voice'],
            'ko_style': q['ko'] if speaker == 'korean' else None, 'aug': t['aug'] or None,
            'lines': q['lines'], 'shared_line': q['shared_line'], 'unsplit_line': q['unsplit_line'],
            'script': q['script'],
            'seconds': t['seconds'],
            'correct': db.identify_audio(h) == song,
            'rank': ranking.index(song) + 1 if song in ranking else None,
            'typed_correct': typed_ok[(song, memory)],
            'cer_vs_japanese': round(cer(q['text'][memory], t['text']), 4),
            'transcript_letters': letter_shares(t['text']),
        })
    return rows


def summarize(rows, qs):
    excluded = sorted({r['song'] for r in rows if r['unsplit_line']})
    rows = [r for r in rows if not r['unsplit_line']]
    def acc(rs):
        return sum(r['correct'] for r in rs) / len(rs) if rs else None

    out = {'cells': {}, 'comparisons': {}}
    for cond in CONDITIONS:
        for ch in CHANNELS:
            for lang in LANG_MODES:
                rs = [r for r in rows if r['condition'] == cond and r['channel'] == ch and r['lang_mode'] == lang]
                if not rs:
                    continue
                langs = {}
                for r in rs:
                    langs[r['detected_language'] or '?'] = langs.get(r['detected_language'] or '?', 0) + 1
                out['cells'][f'{cond}|{ch}|{lang}'] = {
                    'n': len(rs), 'accuracy': acc(rs),
                    'accuracy_ci': cluster_bootstrap_ci(rs, lambda r: 1.0 if r['correct'] else 0.0),
                    'recall@10': sum(1 for r in rs if r['rank'] and r['rank'] <= 10) / len(rs),
                    'typed_accuracy': sum(r['typed_correct'] for r in rs) / len(rs),
                    'spoken_vs_typed': mcnemar_exact([r['correct'] for r in rs], [r['typed_correct'] for r in rs]),
                    'median_cer_vs_japanese': statistics.median(r['cer_vs_japanese'] for r in rs),
                    'transcript_mostly_hangul': sum(r['transcript_letters']['hangul'] > 0.5 for r in rs) / len(rs),
                    'detected_language': dict(sorted(langs.items(), key=lambda kv: -kv[1])),
                }

    def paired(a_sel, b_sel):
        a = {(r['song']): r['correct'] for r in rows if a_sel(r)}
        b = {(r['song']): r['correct'] for r in rows if b_sel(r)}
        common = sorted(set(a) & set(b))
        res = mcnemar_exact([a[s] for s in common], [b[s] for s in common])
        return {'n': len(common), 'acc_a': sum(a[s] for s in common) / len(common),
                'acc_b': sum(b[s] for s in common) / len(common), **res}

    for cond in CONDITIONS:
        for ch in CHANNELS:
            out['comparisons'][f'{cond}|{ch}: ja-forced (a) vs auto (b)'] = paired(
                lambda r, c=cond, h=ch: r['condition'] == c and r['channel'] == h and r['lang_mode'] == 'ja',
                lambda r, c=cond, h=ch: r['condition'] == c and r['channel'] == h and r['lang_mode'] == 'auto')
        for lang in LANG_MODES:
            out['comparisons'][f'{cond}|{lang}: clean (a) vs degraded (b)'] = paired(
                lambda r, c=cond, l=lang: r['condition'] == c and r['channel'] == 'clean' and r['lang_mode'] == l,
                lambda r, c=cond, l=lang: r['condition'] == c and r['channel'] != 'clean' and r['lang_mode'] == l)
    for memory, (n_cond, k_cond) in {'exact': ('A', 'B'), 'blurred': ('C', 'D')}.items():
        for lang in LANG_MODES:
            out['comparisons'][f'{memory}|clean|{lang}: native (a) vs korean (b)'] = paired(
                lambda r, c=n_cond, l=lang: r['condition'] == c and r['channel'] == 'clean' and r['lang_mode'] == l,
                lambda r, c=k_cond, l=lang: r['condition'] == c and r['channel'] == 'clean' and r['lang_mode'] == l)

    for lang in LANG_MODES:
        out['comparisons'][f'native|clean|{lang}: one line S (a) vs multi-line A (b)'] = paired(
            lambda r, l=lang: r['condition'] == 'S' and r['channel'] == 'clean' and r['lang_mode'] == l,
            lambda r, l=lang: r['condition'] == 'A' and r['channel'] == 'clean' and r['lang_mode'] == l)

    secs = [r['seconds'] for r in rows if r['channel'] == 'clean' and r['lang_mode'] == 'auto'
            and r['condition'] != 'S']
    out['speech_seconds'] = {'median': statistics.median(secs), 'p5': sorted(secs)[len(secs) // 20],
                           'p95': sorted(secs)[len(secs) * 19 // 20],
                           'share_below_app_minimum': sum(s < APP_MIN_SECONDS for s in secs) / len(secs)}
    out['queries'] = {'songs': len(qs) - len(excluded), 'excluded_unsplit_songs': excluded, 'lines_per_query_median': statistics.median(len(q['lines']) for q in qs),
                      'with_shared_line': sum(q['shared_line'] for q in qs),
                      'blur_changed_median': statistics.median(q['blur_changed'] for q in qs if q['blur_changed'])}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--score', action='store_true', help='only re-score from the local cache')
    ap.add_argument('--limit', type=int, help='first N songs only (smoke test)')
    args = ap.parse_args()

    db = SongDB()
    res = P.Resources(m['line_text'] for m in db.line_metadata)
    qs = build_queries(db, res)
    if args.limit:
        qs = qs[:args.limit]
    if not args.score:
        run(db, qs)
    rows = score(db, qs)
    summary = summarize(rows, qs)
    out = {
        'design': {k: v for k, v in [
            ('query', f'consecutive lines (>= {MIN_CHARS} non-space chars, <= {MAX_LINES} lines) from each '
                      'song\'s first seed-0 base line; clips under 5 s padded with trailing silence'),
            ('conditions', {c: {'memory': m, 'speaker': s} for c, (m, s) in CONDITIONS.items()}),
            ('blurred', f'perturb.py {BLUR[0]} at {int(BLUR[1] * 100)}% of word units'),
            ('native_voices', JP_VOICES), ('korean_voices', KO_VOICES),
            ('single', 'condition S: the one base line, native voice, normal speed'),
            ('korean_reading', 'LocalTTS jp2hangul: UniDic reading -> Hangul; per-song style (tsu, word-initial '
                               'stops, long vowels, n before labials), pitch and rate varied'),
            ('channels', {'clean': 'TTS output at 16 kHz',
                          'phone_reverb_noise': 'synthetic RIR (RT60 0.2-0.6 s) + pink noise (SNR 10-20 dB) + 300-3400 Hz band, 8 kHz'}),
            ('stt', 'Whisper large-v3 (LocalTTS, transformers fp16 on GPU); language auto-detected (as app.py) or forced ja'),
            ('search', 'app.py audio path: lyric-line top-1 song'),
            ('typed_accuracy', 'same Japanese query text typed (no speech), for paired comparison'),
        ]},
        'summary': summary,
        'rows': rows,
    }
    with open(RESULT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))  # per-clip rows: keep compact
    for k, v in summary['cells'].items():
        print(f"{k}: acc {v['accuracy']:.3f} {v['accuracy_ci']} typed {v['typed_accuracy']:.3f} "
              f"hangul {v['transcript_mostly_hangul']:.2f} n={v['n']}")


if __name__ == '__main__':
    main()
