"""Synthetic query generation from indexed lyric lines.

Each sampled base line yields one query per type. Query text lives only in
memory; callers record the query id, song index and source line indices.
"""
import math
import random
import re

QUERY_TYPES = ['exact', 'half', 'word_drop', 'typo', 'concat']
MIN_BASE_CHARS = 8      # non-space characters a base line needs
LINES_PER_SONG = 2
WORD_DROP_RATE = 0.3
TYPO_RATE = 0.1

HIRAGANA = [chr(c) for c in range(0x3041, 0x3097)]
KATAKANA = [chr(c) for c in range(0x30A1, 0x30FB)]
LATIN = list('abcdefghijklmnopqrstuvwxyz')
HANGUL = [chr(c) for c in range(0xAC00, 0xD7A4)]


def script_of(ch):
    o = ord(ch)
    if 0x3040 <= o <= 0x309F:
        return 'hira'
    if 0x30A0 <= o <= 0x30FF:
        return 'kata'
    if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
        return 'kanji'
    if ch.isascii() and ch.isalnum():
        return 'latin'
    if 0xAC00 <= o <= 0xD7A3:
        return 'hangul'
    if ch.isspace():
        return 'space'
    return 'other'


def script_class(text):
    """'latin', 'kana' (Japanese without kanji) or 'kanji' (Japanese with kanji); by majority of letters."""
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    ja = sum(1 for c in text if '぀' <= c <= 'ヿ' or '一' <= c <= '鿿')
    if latin > ja:
        return 'latin'
    return 'kanji' if any('一' <= c <= '鿿' for c in text) else 'kana'


def nonspace_len(text):
    return len(re.sub(r'\s', '', text))


def units(text):
    """Word-like units: whitespace tokens when there are 3+, else script runs
    (Japanese lines mostly have no spaces). Each unit is (text, space_after)."""
    tokens = text.split()
    if len(tokens) >= 3:
        return [(t, True) for t in tokens]
    out = []
    for t_i, tok in enumerate(tokens):
        runs, cur, cur_script = [], '', None
        for ch in tok:
            sc = script_of(ch)
            if cur and sc != cur_script:
                runs.append(cur)
                cur = ''
            cur += ch
            cur_script = sc
        if cur:
            runs.append(cur)
        for r_i, r in enumerate(runs):
            out.append((r, r_i == len(runs) - 1 and t_i < len(tokens) - 1))
    if len(out) >= 3:
        return out
    # still too few: two-character chunks
    flat = ''.join(tokens)
    return [(flat[i:i + 2], False) for i in range(0, len(flat), 2)]


def join_units(us):
    s = ''
    for i, (t, space) in enumerate(us):
        s += t
        if space and i < len(us) - 1:
            s += ' '
    return s


def make_half(text):
    t = text.strip()
    return t[:math.ceil(len(t) / 2)].rstrip()


def make_word_drop(text, rng):
    us = units(text.strip())
    n_drop = min(len(us) - 1, max(1, round(WORD_DROP_RATE * len(us))))
    drop = set(rng.sample(range(len(us)), n_drop))
    kept = []
    for i, (t, space) in enumerate(us):
        if i in drop:
            if space and kept:  # keep the word boundary
                kept[-1] = (kept[-1][0], True)
            continue
        kept.append((t, space))
    return join_units(kept)


class TypoMaker:
    def __init__(self, kanji_pool):
        self.pools = {'hira': HIRAGANA, 'kata': KATAKANA, 'latin': LATIN,
                      'hangul': HANGUL, 'kanji': kanji_pool}

    def _char_like(self, ch, rng, fallback):
        pool = self.pools.get(script_of(ch))
        if not pool:
            return rng.choice(fallback)
        c = rng.choice(pool)
        return c.upper() if ch.isupper() else c

    def __call__(self, text, rng):
        chars = list(text.strip())
        n_ops = max(1, round(TYPO_RATE * nonspace_len(text)))
        for _ in range(n_ops):
            positions = [i for i, c in enumerate(chars) if not c.isspace()]
            if not positions:
                break
            op = rng.choice(['insert', 'delete', 'substitute'])
            i = rng.choice(positions)
            if op == 'delete' and len(positions) > 1:
                del chars[i]
            elif op == 'insert':
                chars.insert(i + rng.randint(0, 1), self._char_like(chars[i], rng, chars))
            else:
                chars[i] = self._char_like(chars[i], rng, chars)
        return ''.join(chars)


def make_concat(first, second):
    a, b = first.strip(), second.strip()
    return (a[len(a) // 2:].lstrip() + ' ' + b[:math.ceil(len(b) / 2)].rstrip()).strip()


def generate(db, seed):
    """Positive queries for one seed: LINES_PER_SONG base lines per song, all query types."""
    rng = random.Random(seed)
    kanji_pool = sorted({c for m in db.line_metadata for c in m['line_text'] if script_of(c) == 'kanji'})
    typo = TypoMaker(kanji_pool)
    queries = []
    for song in sorted(db.lines_by_song):
        line_ids = db.lines_by_song[song]
        eligible = [i for i in line_ids if nonspace_len(db.line_text(i)) >= MIN_BASE_CHARS]
        for k, base in enumerate(rng.sample(eligible, min(LINES_PER_SONG, len(eligible)))):
            base_text = db.line_text(base)
            pos = line_ids.index(base)
            if len(line_ids) > 1:
                pair = (base, line_ids[pos + 1]) if pos + 1 < len(line_ids) else (line_ids[pos - 1], base)
            else:
                pair = None
            variants = {
                'exact': ([base], base_text.strip()),
                'half': ([base], make_half(base_text)),
                'word_drop': ([base], make_word_drop(base_text, rng)),
                'typo': ([base], typo(base_text, rng)),
            }
            if pair:
                variants['concat'] = (list(pair), make_concat(db.line_text(pair[0]), db.line_text(pair[1])))
            for qtype in QUERY_TYPES:
                if qtype not in variants:
                    continue
                src, text = variants[qtype]
                ambiguous = (any(db.text_in_other_song(db.line_text(i), song) for i in src)
                             or db.text_in_other_song(text, song))
                queries.append({
                    'id': f's{seed}-song{song}-b{k}-{qtype}',
                    'type': qtype,
                    'song': song,
                    'src_lines': src,
                    'ambiguous': ambiguous,
                    'script': script_class(base_text),
                    'text': text,  # in-memory only; stripped before saving
                })
    return queries
