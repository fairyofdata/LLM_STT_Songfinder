"""Check that eval/common.py identifies the same song as app.py.

    venv/Scripts/python eval/check_against_app.py

Imports app.py (needs its web dependencies; Spotify credentials get dummy
values if unset, and no network call is made), runs a sample of seed-0
queries and all negatives through app.search_pipeline_from_text /
search_pipeline_from_audio one at a time, and compares with the batched
re-implementation. Writes eval/results/app_consistency.json (ids only).
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO_ROOT, SongDB  # noqa: E402
from negatives import NEGATIVES  # noqa: E402
import queries as Q  # noqa: E402

PER_TYPE = 10


def song_key(song):
    return (song.get('spotify_id'), song.get('title'), song.get('artist'))


def app_key(identified):
    if identified is None:
        return None
    return (identified['songId'], identified['songTitle'], identified['artist'])


def main():
    for var in ('SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET'):
        os.environ.setdefault(var, 'dummy-for-eval')
    os.chdir(REPO_ROOT)
    sys.path.insert(0, REPO_ROOT)
    import app  # noqa: E402

    db = SongDB()
    rng = random.Random(12345)
    qs = Q.generate(db, 0)
    sample = []
    for t in Q.QUERY_TYPES:
        sample += rng.sample([q for q in qs if q['type'] == t], PER_TYPE)
    sample += [{'id': f'neg-{lang}-{i}', 'text': text}
               for lang, sents in NEGATIVES.items() for i, text in enumerate(sents)]

    hits = db.search(db.encode([q['text'] for q in sample]))
    checks = []
    for q, hit in zip(sample, hits):
        ours_text = db.identify_text(hit)
        ours_audio = db.identify_audio(hit)
        app_text, _, _ = app.search_pipeline_from_text(q['text'])
        app_audio, _, _ = app.search_pipeline_from_audio(q['text'])
        text_ok = app_key(app_text) == (None if ours_text is None else song_key(db.song_metadata[ours_text]))
        audio_ok = app_key(app_audio) == song_key(db.song_metadata[ours_audio])
        checks.append({'id': q['id'], 'text_path_match': text_ok, 'audio_path_match': audio_ok})

    n = len(checks)
    text_match = sum(c['text_path_match'] for c in checks)
    audio_match = sum(c['audio_path_match'] for c in checks)
    out = {'n': n, 'text_path_matches': text_match, 'audio_path_matches': audio_match,
           'mismatched_ids': [c['id'] for c in checks if not (c['text_path_match'] and c['audio_path_match'])]}
    with open(os.path.join(REPO_ROOT, 'eval', 'results', 'app_consistency.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    print(f'text path: {text_match}/{n} match app.py, audio path: {audio_match}/{n} match app.py')
    if out['mismatched_ids']:
        print('mismatched ids:', ', '.join(out['mismatched_ids']))
        sys.exit(1)


if __name__ == '__main__':
    main()
