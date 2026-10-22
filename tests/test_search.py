"""Tests for search.py.

Unit tests use a tiny synthetic index and a fake embedder (no lyrics, no model).
The integration test runs only when the real data files are present; it checks
that one-line queries still pick the same song as the pre-refactor app logic
(eval/common.py), so the new window voting changes multi-line queries only.
"""
import os
import random
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from search import SongIndex, windows  # noqa: E402

DIM = 8


def unit(i):
    v = np.zeros(DIM, dtype='float32')
    v[i] = 1.0
    return v


class FakeEmbedder:
    """Maps known texts to fixed vectors; anything else to a fixed 'noise' direction."""

    def __init__(self, table):
        self.table = table

    def encode(self, texts, **_):
        return np.stack([self.table.get(t, unit(DIM - 1)) for t in texts])


def make_index(table):
    # song 0: lines on axis 0, song 1: axis 1, song 2: axis 2; summaries on axes 3-5
    line_metadata = [{'original_song_index': s, 'line_text': f'line{s}{k}'} for s in range(3) for k in range(2)]
    line_embeddings = np.stack([unit(m['original_song_index']) for m in line_metadata])
    song_metadata = [{'title': f'song{s}', 'artist': f'artist{s}', 'summary': f'summary{s}',
                      'spotify_id': f'id{s}', 'tags_normalized': "['tag']"} for s in range(3)]
    song_embeddings = np.stack([unit(s) for s in range(3)])
    summary_embeddings = np.stack([unit(3 + s) for s in range(3)])
    return SongIndex(line_metadata, song_metadata, line_embeddings, song_embeddings, summary_embeddings,
                     FakeEmbedder(table))


def test_short_query_is_one_window():
    assert windows('君の声が聞こえる') == ['君の声が聞こえる']


def test_long_unbroken_query_slides():
    text = 'あ' * 60
    pieces = windows(text)
    assert len(pieces) > 3 and all(len(p) <= 14 for p in pieces)


def test_spaced_query_merges_pieces_to_line_size():
    pieces = windows('I never wanted to say goodbye to you at all tonight')
    assert len(pieces) >= 2 and all(len(p) >= 14 for p in pieces[:-1])


def test_one_line_query_is_plain_top1():
    idx = make_index({'q': unit(1)})
    hit = idx.identify_transcript('q')
    assert hit['song'] == 1 and hit['line'] in (2, 3)


def mixed(axis, cos):
    """Unit vector with the given cosine to `axis` (rest on the noise axis)."""
    v = unit(axis) * cos + unit(DIM - 1) * np.sqrt(1 - cos ** 2)
    return v.astype('float32')


QUERY = 'aaaaaaaaaaaaaa bbbbbbbbbbbbbb cccccccccccccc dddddddddddddd'


def test_windows_outvote_a_loose_whole_query():
    # several lines: the whole query leans to song 0 (cos 0.7), most windows belong to song 2
    table = {QUERY: mixed(0, 0.7)}
    for piece in windows(QUERY):
        table[piece] = unit(2)
    idx = make_index(table)
    assert len(windows(QUERY)) == 4
    assert idx.identify_transcript(QUERY)['song'] == 2


def test_close_whole_query_skips_voting():
    # the whole query is (almost) one indexed line: trust it even if windows disagree
    table = {QUERY: mixed(0, 0.95)}
    for piece in windows(QUERY):
        table[piece] = unit(2)
    idx = make_index(table)
    assert idx.identify_transcript(QUERY)['song'] == 0


def test_summary_hit_maps_to_its_own_song():
    # regression: the old code looked the summary index up in line_metadata
    idx = make_index({'mood': unit(5)})          # matches the summary of song 2 only
    hit = idx.identify_text('mood', threshold=0.4)
    assert hit == {'song': 2, 'via': 'summary', 'line': None, 'score': pytest.approx(1.0)}


def test_threshold_returns_none():
    weak = np.full(DIM, 1 / np.sqrt(DIM), dtype='float32')   # cosine ~0.35 with every axis
    idx = make_index({'weak': weak})
    assert idx.identify_text('weak', threshold=0.4) is None
    assert idx.identify_text('weak', threshold=0.3) is not None


def test_recommendations_skip_identified_song_and_artist():
    idx = make_index({})
    recs = idx.recommend_for_text(0)
    assert recs and all(r['songTitle'] != 'song0' for r in recs)
    assert len({r['artist'] for r in recs}) == len(recs)


DATA_PRESENT = all(os.path.exists(os.path.join(ROOT, f)) for f in
                   ('line_metadata.json', 'song_metadata.json', 'line_embeddings.npy'))


@pytest.mark.skipif(not DATA_PRESENT, reason='lyric data not available')
def test_one_line_queries_match_previous_app_logic():
    sys.path.insert(0, os.path.join(ROOT, 'eval'))
    from common import SongDB
    old = SongDB(ROOT)
    new = SongIndex(old.line_metadata, old.song_metadata, np.load(os.path.join(ROOT, 'line_embeddings.npy')),
                    np.load(os.path.join(ROOT, 'song_embeddings.npy')),
                    np.load(os.path.join(ROOT, 'summary_embeddings.npy')), old.embedder)
    rng = random.Random(0)
    # lines that also occur in another song tie at cosine 1.0 and FAISS may break the tie either way
    picks = [i for i in rng.sample(range(len(old.line_metadata)), 300)
             if 8 <= len(old.line_text(i).strip()) <= 14
             and not old.text_in_other_song(old.line_text(i), old.line_metadata[i]['original_song_index'])]
    texts = [old.line_text(i).strip() for i in picks]
    hits = old.search(old.encode(texts))
    for text, hit in zip(texts, hits):
        assert new.identify_transcript(text)['song'] == old.identify_audio(hit)
