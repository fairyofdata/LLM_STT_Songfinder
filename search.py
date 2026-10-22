"""Song identification and recommendation over the lyric-line, song and summary indexes.

Used by app.py (the API) and eval/ (measurements), so both run the same code.

Identification
- Lyric search is per lyric line, but queries are often several lines (the app
  asks for 5-15 s of speech). When the whole query matches no single line closely
  (cosine < EXACT_LINE_SCORE) and spans MIN_VOTE_WINDOWS or more line-sized pieces, it is split into
  line-sized windows; each window and the whole query vote for the song of their
  top-1 line (the whole query weighted by sqrt(number of windows)). Otherwise it
  is a plain top-1 search, as before. Thresholds always use the whole-query cosine.
- Text queries also compare against song summaries; the summary hit is a song
  index (the old code looked it up in line_metadata by mistake).
"""
import ast
import json
import math
import os
import re
from collections import defaultdict
from logging import getLogger

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

logger = getLogger(__name__)

MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'
TEXT_THRESHOLD = float(os.getenv('SONGFINDER_TEXT_THRESHOLD', '0.4'))
WINDOW_CHARS, STRIDE_CHARS = 14, 7   # the median indexed line has 12 non-space characters
EXACT_LINE_SCORE = 0.9   # whole query this close to one line: trust it, skip window voting
MIN_VOTE_WINDOWS = 3     # 2-window queries are mostly single long lines; voting there flips a few


def parse_tags(tags_str):
    if not isinstance(tags_str, str) or not tags_str.startswith('['):
        return []
    try:
        return ast.literal_eval(tags_str)
    except (ValueError, SyntaxError):
        return []


def windows(text):
    """Line-sized pieces of a query: split at spaces/punctuation, merge pieces up to
    WINDOW_CHARS, and slide over long unbroken runs (Japanese transcripts have no spaces)."""
    pieces = [p for p in re.split(r'[\s、。,.!?！？「」]+', text) if p]
    merged, cur = [], ''
    for p in pieces:
        cur += p
        if len(cur) >= WINDOW_CHARS:
            merged.append(cur)
            cur = ''
    if cur:
        merged.append(cur)
    out = []
    for w in merged:
        if len(w) <= 2 * WINDOW_CHARS:
            out.append(w)
        else:
            out += [w[i:i + WINDOW_CHARS] for i in range(0, len(w) - WINDOW_CHARS // 2, STRIDE_CHARS)]
    return out or [text]


class SongIndex:
    def __init__(self, line_metadata, song_metadata, line_embeddings, song_embeddings, summary_embeddings,
                 embedder):
        self.line_metadata = line_metadata
        self.song_metadata = song_metadata
        self.line_embeddings = line_embeddings
        self.song_embeddings = song_embeddings
        self.summary_embeddings = summary_embeddings
        self.embedder = embedder

        self.line_index = faiss.IndexFlatIP(line_embeddings.shape[1])
        self.line_index.add(line_embeddings)
        self.song_index = faiss.IndexFlatIP(song_embeddings.shape[1])
        self.song_index.add(song_embeddings)
        self.summary_index = faiss.IndexFlatIP(summary_embeddings.shape[1])
        self.summary_index.add(summary_embeddings)

        self.line_song = np.array([m['original_song_index'] for m in line_metadata])
        self.lines_by_song = defaultdict(list)
        for i, meta in enumerate(line_metadata):
            self.lines_by_song[meta['original_song_index']].append(i)

    @classmethod
    def load(cls, data_dir='.'):
        def path(name):
            return os.path.join(data_dir, name)
        with open(path('line_metadata.json'), 'r', encoding='utf-8') as f:
            line_metadata = json.load(f)
        with open(path('song_metadata.json'), 'r', encoding='utf-8') as f:
            song_metadata = json.load(f)
        return cls(line_metadata, song_metadata, np.load(path('line_embeddings.npy')),
                   np.load(path('song_embeddings.npy')), np.load(path('summary_embeddings.npy')),
                   SentenceTransformer(MODEL_NAME))

    def encode(self, texts):
        vectors = np.ascontiguousarray(self.embedder.encode(texts), dtype='float32')
        faiss.normalize_L2(vectors)
        return vectors

    # ---------- identification ----------

    def _lyric_vote(self, query, query_vector):
        """(song, line, whole-query top-1 cosine). Window voting decides the song only when the
        whole query matches no single line closely, i.e. when it spans several lines."""
        D, I = self.line_index.search(query_vector, 1)
        whole_line, whole_score = int(I[0][0]), float(D[0][0])
        pieces = windows(query)
        if len(pieces) < MIN_VOTE_WINDOWS or whole_score >= EXACT_LINE_SCORE:
            return int(self.line_song[whole_line]), whole_line, whole_score
        vectors = np.vstack([query_vector, self.encode(pieces)])
        D, I = self.line_index.search(vectors, 1)
        weights = [math.sqrt(len(pieces)) if len(pieces) > 1 else 1.0] + [1.0] * (len(vectors) - 1)
        votes, best = defaultdict(float), {}
        for w, score, line_idx in zip(weights, D[:, 0], I[:, 0]):
            song = int(self.line_song[line_idx])
            votes[song] += w * float(score)
            if song not in best or score > best[song][1]:
                best[song] = (int(line_idx), float(score))
        song = max(votes, key=votes.get)
        return song, best[song][0], whole_score

    def identify_text(self, query, threshold=TEXT_THRESHOLD):
        """Text search: lyric vote vs top-1 summary. None when neither clears the threshold.
        Both comparisons use whole-query cosines, as before; voting only picks the song."""
        query_vector = self.encode([query])
        song, line_idx, lyric_score = self._lyric_vote(query, query_vector)
        D, I = self.summary_index.search(query_vector, 1)
        summary_score, summary_song = float(D[0][0]), int(I[0][0])
        if not (summary_score > threshold or lyric_score > threshold):
            return None
        if summary_score > lyric_score:
            return {'song': summary_song, 'via': 'summary', 'line': None, 'score': summary_score}
        return {'song': song, 'via': 'lyric', 'line': line_idx, 'score': lyric_score}

    def identify_transcript(self, text):
        """Voice search on a transcript: lyric vote, no threshold."""
        song, line_idx, score = self._lyric_vote(text, self.encode([text]))
        return {'song': song, 'via': 'lyric', 'line': line_idx, 'score': score}

    # ---------- presentation and recommendation ----------

    def song_card(self, song_idx, user_query):
        raw = self.song_metadata[song_idx]
        return {
            "songId": raw.get('spotify_id'),
            "songTitle": raw.get('title'),
            "artist": raw.get('artist'),
            "albumCoverUrl": raw.get('album_cover_url'),
            "tagName": parse_tags(raw.get('tags_normalized', '[]')),
            "songDescription": raw.get('summary', 'N/A'),
            "userQuery": user_query,
        }

    def _recommendation(self, idx, match_line, reasons):
        info = self.song_metadata[idx]
        return {
            "songId": info.get('spotify_id'),
            "songTitle": info['title'],
            "artist": info['artist'],
            "albumCoverUrl": info.get('album_cover_url'),
            "tagName": parse_tags(info.get('tags_normalized', '[]')),
            "songDescription": info.get('summary', 'N/A'),
            "matchLine": match_line,
            "recommendationReason": ", ".join(list(set(reasons))),
        }

    def recommend_for_text(self, song_idx, n=3):
        """Song + summary similarity and shared tags (text search)."""
        identified = self.song_metadata[song_idx]
        candidate_scores = defaultdict(float)
        recommendation_reasons = defaultdict(list)

        D_song, I_song = self.song_index.search(self.song_embeddings[song_idx:song_idx + 1], 10)
        for i, idx in enumerate(I_song[0]):
            candidate_scores[idx] += D_song[0][i] * 0.5
            recommendation_reasons[idx].append("분위기와 장르가 비슷해요.")

        D_summary, I_summary = self.summary_index.search(self.summary_embeddings[song_idx:song_idx + 1], 10)
        for i, idx in enumerate(I_summary[0]):
            candidate_scores[idx] += D_summary[0][i] * 0.3
            recommendation_reasons[idx].append("곡의 전반적인 감성이 비슷해요.")

        original_tags = set(parse_tags(identified.get('tags_normalized', '[]')))
        for idx in list(candidate_scores.keys()):
            shared = original_tags.intersection(parse_tags(self.song_metadata[idx].get('tags_normalized', '[]')))
            if shared:
                candidate_scores[idx] += 0.2
                recommendation_reasons[idx].append(f"비슷한 태그({', '.join(shared)})를 공유해요.")

        return self._pick(song_idx, candidate_scores, recommendation_reasons, n, match_line=lambda idx: "")

    def recommend_for_audio(self, song_idx, line_idx, query_text, n=3):
        """Song + summary + lyric-line similarity, shared tags and rank bonuses (voice search)."""
        identified = self.song_metadata[song_idx]
        num_words = len(query_text.split())
        weight_song, weight_summary, weight_lyric = (0.5, 0.1, 0.4) if num_words > 5 else (0.6, 0.2, 0.2)

        identified_lyric_vector = self.line_embeddings[line_idx:line_idx + 1]
        candidate_scores = defaultdict(float)
        recommendation_reasons = defaultdict(list)

        D_song, I_song = self.song_index.search(self.song_embeddings[song_idx:song_idx + 1], 10)
        for i, idx in enumerate(I_song[0]):
            candidate_scores[idx] += D_song[0][i] * weight_song
            recommendation_reasons[idx].append("분위기와 장르가 비슷해요.")

        D_summary, I_summary = self.summary_index.search(self.summary_embeddings[song_idx:song_idx + 1], 10)
        for i, idx in enumerate(I_summary[0]):
            candidate_scores[idx] += D_summary[0][i] * weight_summary
            recommendation_reasons[idx].append("곡의 전반적인 감성이 비슷해요.")

        D_lyric, I_lyric = self.line_index.search(identified_lyric_vector, 50)
        for i, l_idx in enumerate(I_lyric[0]):
            s_idx = self.line_metadata[l_idx]['original_song_index']
            if s_idx == song_idx:
                continue
            candidate_scores[s_idx] += D_lyric[0][i] * weight_lyric
            recommendation_reasons[s_idx].append("가사가 비슷한 느낌을 줘요.")

        original_tags = set(parse_tags(identified.get('tags_normalized', '[]')))
        for idx in list(candidate_scores.keys()):
            shared = original_tags.intersection(parse_tags(self.song_metadata[idx].get('tags_normalized', '[]')))
            if shared:
                candidate_scores[idx] += 0.1
                recommendation_reasons[idx].append(f"비슷한 태그({', '.join(shared)})를 공유해요.")

        for i, idx in enumerate(I_song[0]):
            candidate_scores[idx] += (10 - i) * 0.005
        for i, idx in enumerate(I_summary[0]):
            candidate_scores[idx] += (10 - i) * 0.003
        for i, l_idx in enumerate(I_lyric[0]):
            candidate_scores[self.line_metadata[l_idx]['original_song_index']] += (50 - i) * 0.001

        def closest_line(idx):
            candidate_line_indices = self.lines_by_song.get(idx, [])
            if not candidate_line_indices:
                return "추천 근거 가사를 찾을 수 없습니다."
            similarities = np.dot(self.line_embeddings[candidate_line_indices], identified_lyric_vector.T).flatten()
            return self.line_metadata[candidate_line_indices[similarities.argmax()]]['line_text']

        return self._pick(song_idx, candidate_scores, recommendation_reasons, n, match_line=closest_line)

    def _pick(self, song_idx, candidate_scores, recommendation_reasons, n, match_line):
        """Top candidates, skipping the identified song and repeating artists."""
        out = []
        seen_songs = {song_idx}
        seen_artists = {self.song_metadata[song_idx].get('artist')}
        for idx, _ in sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True):
            if idx in seen_songs or self.song_metadata[idx].get('artist') in seen_artists:
                continue
            if len(out) >= n:
                break
            out.append(self._recommendation(idx, match_line(idx), recommendation_reasons.get(idx, [])))
            seen_songs.add(idx)
            seen_artists.add(self.song_metadata[idx].get('artist'))
        return out
