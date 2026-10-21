"""Shared loading and search logic for the Songfinder evaluation.

Re-implements the song-identification part of app.py's two search paths so the
evaluation does not need to import app.py (which also sets up OpenAI, Spotify
and the FastAPI app). eval/check_against_app.py confirms the two agree.

Nothing in this package writes lyric text to disk or stdout: queries are
recorded only by id, song index and source line index.
"""
import json
import os
import unicodedata
from collections import defaultdict

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'
TEXT_THRESHOLD = 0.4  # app.py search_pipeline_from_text
RANK_DEPTH = 2048     # line hits fetched before grouping into songs


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).lower().split())


class SongDB:
    def __init__(self, root=REPO_ROOT):
        with open(os.path.join(root, 'line_metadata.json'), 'r', encoding='utf-8') as f:
            self.line_metadata = json.load(f)
        with open(os.path.join(root, 'song_metadata.json'), 'r', encoding='utf-8') as f:
            self.song_metadata = json.load(f)
        line_embeddings = np.load(os.path.join(root, 'line_embeddings.npy'))
        summary_embeddings = np.load(os.path.join(root, 'summary_embeddings.npy'))

        self.line_index = faiss.IndexFlatIP(line_embeddings.shape[1])
        self.line_index.add(line_embeddings)
        self.summary_index = faiss.IndexFlatIP(summary_embeddings.shape[1])
        self.summary_index.add(summary_embeddings)

        self.line_song = np.array([m['original_song_index'] for m in self.line_metadata])
        self.lines_by_song = defaultdict(list)
        for i, m in enumerate(self.line_metadata):
            self.lines_by_song[m['original_song_index']].append(i)

        # normalized line text -> set of songs containing it (chorus / common phrases)
        self.songs_by_text = defaultdict(set)
        for m in self.line_metadata:
            self.songs_by_text[normalize(m['line_text'])].add(m['original_song_index'])

        self.embedder = SentenceTransformer(MODEL_NAME)

    def line_text(self, line_idx):
        return self.line_metadata[line_idx]['line_text']

    def text_in_other_song(self, text, song_idx):
        return bool(self.songs_by_text.get(normalize(text), set()) - {song_idx})

    def encode(self, texts, batch_size=128):
        vecs = self.embedder.encode(texts, batch_size=batch_size, show_progress_bar=False)
        vecs = np.ascontiguousarray(vecs, dtype='float32')
        faiss.normalize_L2(vecs)
        return vecs

    def search(self, query_vectors):
        """Per query: song ranking from line hits, plus the top-1 values both app paths use."""
        D_line, I_line = self.line_index.search(query_vectors, RANK_DEPTH)
        D_sum, I_sum = self.summary_index.search(query_vectors, 1)
        out = []
        for q in range(len(query_vectors)):
            songs, seen = [], set()
            for line_idx in I_line[q]:
                if line_idx < 0:
                    break
                s = int(self.line_song[line_idx])
                if s not in seen:
                    seen.add(s)
                    songs.append(s)
            out.append({
                'song_ranking': songs,
                'lyric_score': float(D_line[q][0]),
                'lyric_line_idx': int(I_line[q][0]),
                'summary_score': float(D_sum[q][0]),
                'summary_idx': int(I_sum[q][0]),
            })
        return out

    # --- song identification, mirroring app.py ---

    def identify_text(self, hit, threshold=TEXT_THRESHOLD, fixed=False):
        """search_pipeline_from_text. Returns song index, or None for 'not found'.

        fixed=False reproduces app.py as written: when the summary hit wins it
        looks up line_metadata[summary_idx], although summary_idx is a song index.
        fixed=True uses summary_idx directly.
        """
        s, l = hit['summary_score'], hit['lyric_score']
        if not (s > threshold or l > threshold):
            return None
        if s > l:
            if fixed:
                return hit['summary_idx']
            return int(self.line_metadata[hit['summary_idx']]['original_song_index'])
        return int(self.line_song[hit['lyric_line_idx']])

    def identify_audio(self, hit):
        """search_pipeline_from_audio (after transcription): top-1 line's song, no threshold."""
        return int(self.line_song[hit['lyric_line_idx']])
