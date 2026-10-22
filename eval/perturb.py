"""Word-level corruption of queries, simulating a half-remembered lyric.

Unit = bunsetsu-like chunk built from UniDic tokens (fugashi + unidic-lite):
one content word (with prefixes/suffixes) plus the particles and auxiliaries
that follow it. Latin words are one unit each. A noise level r changes
max(1, round(r * n)) of the n units, always leaving one unit intact.

Types (each targets a kind of memory error; caveats in docs/EVALUATION.md):
- meaning_sub    content word -> Japanese WordNet synonym that fits the context
                 (synonyms of every sense that also occur in the lyric DB and differ in
                 reading, ranked by masked-LM likelihood in place)
- sound_sub      content word -> another word from the lyric DB whose kana reading
                 differs by one mora (same length, same part of speech): mondegreen
- function_change particle swapped within a confusable set of the same class (は/が, を/が, に/へ/で ...)
                 or dropped; auxiliaries are kept so the line stays grammatical
- drop           whole unit removed
- context_sub    ELECTRA-style: content word masked and refilled by XLM-R with a
                 same-script, same-POS, same-inflection word (Latin: a word used in the DB);
                 plausible, not a synonym
- homophone      kanji content word -> another spelling with the same reading seen in
                 the DB, else kana (IME left unconverted / STT kanji choice)
- mixed          each chosen unit gets meaning_sub, sound_sub, function_change or drop
"""
import functools
import re
import unicodedata

from queries import script_class  # noqa: F401  (re-exported for callers)

PERTURB_TYPES = ['meaning_sub', 'sound_sub', 'function_change', 'drop', 'context_sub', 'homophone', 'mixed']
MIXED_PARTS = ['meaning_sub', 'sound_sub', 'function_change', 'drop']
NOISE_LEVELS = [0.2, 0.4, 0.6]
MLM_NAME = 'FacebookAI/xlm-roberta-base'
MLM_TOP_K = 10
WORDNET = 'omw-ja:1.4'

CONTENT_POS = {'名詞', '代名詞', '動詞', '形容詞', '形状詞', '副詞', '連体詞', '接続詞', '感動詞'}
FUNCTION_POS = {'助詞', '助動詞'}
# confusable particles as (surface, UniDic pos2); swaps stay inside one set
PARTICLE_SETS = [
    {('は', '係助詞'), ('が', '格助詞'), ('も', '係助詞')},
    {('を', '格助詞'), ('が', '格助詞')},
    {('に', '格助詞'), ('へ', '格助詞'), ('で', '格助詞')},
    {('の', '格助詞'), ('が', '格助詞')},
    {('よ', '終助詞'), ('ね', '終助詞'), ('な', '終助詞'), ('さ', '終助詞'), ('わ', '終助詞')},
    {('から', '接続助詞'), ('ので', '接続助詞')},
    {('けど', '接続助詞'), ('のに', '接続助詞'), ('が', '接続助詞')},
]
DICT_FORMS = ('終止形', '連体形')

_tagger = None


def _tag(text):
    global _tagger
    if _tagger is None:
        import fugashi
        _tagger = fugashi.Tagger()
    return _tagger(text)


def has_kanji(s):
    return any('一' <= c <= '鿿' or '㐀' <= c <= '䶿' for c in s)


def is_latin(s):
    return bool(re.search(r'[A-Za-z]', s)) and not re.search(r'[぀-ヿ一-鿿]', s)


def is_punct(s):
    return all(unicodedata.category(c)[0] in 'PSZ' for c in s)


def kata_to_hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _f(word, name):
    v = getattr(word.feature, name, None)
    return '' if v in (None, '*') else v


class Token:
    __slots__ = ('surface', 'ws', 'pos', 'pos2', 'kana', 'lemma', 'cform')

    def __init__(self, w):
        self.surface, self.ws = w.surface, w.white_space
        self.pos, self.pos2 = _f(w, 'pos1'), _f(w, 'pos2')
        self.kana, self.lemma = _f(w, 'kana'), _f(w, 'lemma') or w.surface
        self.cform = _f(w, 'cForm')


class Unit:
    """tokens[content] is the content word; tokens after it are its function tail."""

    def __init__(self, tokens, content):
        self.tokens, self.content = tokens, content

    @property
    def punct(self):
        return self.content is None

    @property
    def head(self):
        return self.tokens[self.content]


def units(text):
    out, cur, content, pending_prefix = [], [], None, []
    for w in _tag(text):
        t = Token(w)
        if is_punct(t.surface):
            if cur:
                out.append(Unit(cur, content))
            out.append(Unit(pending_prefix + [t], None))
            cur, content, pending_prefix = [], None, []
        elif t.pos == '接頭辞':
            pending_prefix.append(t)
        elif t.pos in FUNCTION_POS or t.pos == '接尾辞':
            if cur:
                cur.append(t)
            else:
                cur, content = pending_prefix + [t], len(pending_prefix)
                pending_prefix = []
        else:  # content word starts a new unit
            if cur:
                out.append(Unit(cur, content))
            cur = pending_prefix + [t]
            content = len(pending_prefix)
            pending_prefix = []
    if cur or pending_prefix:
        out.append(Unit(cur + pending_prefix, content if cur else None))
    return out


def join_units(us):
    return re.sub(r'\s+', ' ', ''.join(t.ws + t.surface for u in us for t in u.tokens)).strip()


class Resources:
    """Lazily loaded models and lexicons shared across queries."""

    def __init__(self, db_texts):
        self.db_texts = list(db_texts)

    @functools.cached_property
    def mlm(self):
        return MaskedLM()

    @functools.cached_property
    def lexicon(self):
        """kana reading -> {surface: (lemma, pos)} for Japanese content words in the DB."""
        lex = {}
        for text in self.db_texts:
            for u in units(text):
                if u.punct:
                    continue
                t = u.head
                if t.kana and t.pos in CONTENT_POS and not is_latin(t.surface):
                    lex.setdefault(t.kana, {})[t.surface] = (t.lemma, t.pos)
        return lex

    @functools.cached_property
    def vocab(self):
        """Japanese content-word surfaces and lemmas, and lowercase Latin words, used in the DB."""
        ja, latin = set(), set()
        for text in self.db_texts:
            latin.update(w.lower() for w in re.findall(r"[A-Za-z']+", text))
            for u in units(text):
                if not u.punct and u.head.pos in CONTENT_POS:
                    ja.update((u.head.surface, u.head.lemma))
        return ja, latin

    @functools.cached_property
    def one_mora_index(self):
        """pattern with one wildcard position -> readings (for one-substitution neighbours)."""
        idx = {}
        for r in self.lexicon:
            for i in range(len(r)):
                idx.setdefault((r[:i], r[i + 1:]), set()).add(r)
        return idx

    @functools.cached_property
    def wordnet(self):
        import wn
        return wn.Wordnet(lexicon=WORDNET)

    @functools.lru_cache(maxsize=None)
    def synonyms(self, lemma, kana):
        """WordNet synonyms (any sense) that also occur in the lyric DB and are not just
        another spelling of the same reading."""
        ja_vocab = self.vocab[0]
        out = set()
        for w in self.wordnet.words(lemma):
            for s in w.synsets():
                for l in s.lemmas():
                    if l == lemma or l not in ja_vocab or '+' in l or ' ' in l:
                        continue
                    parsed = list(_tag(l))
                    if kana and ''.join(_f(p, 'kana') for p in parsed) == kana:
                        continue
                    out.add(l)
        return sorted(out)

    def sound_neighbours(self, reading, pos, lemma):
        cands = set()
        for i in range(len(reading)):
            cands |= self.one_mora_index.get((reading[:i], reading[i + 1:]), set())
        out = []
        for r in sorted(cands - {reading}):
            for surface, (lem, p) in sorted(self.lexicon[r].items()):
                if p == pos and lem != lemma:
                    out.append(surface)
        return out


class MaskedLM:
    def __init__(self, name=MLM_NAME):
        import torch
        from transformers import AutoModelForMaskedLM, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(name)
        self.model = AutoModelForMaskedLM.from_pretrained(name).eval()

    def fill(self, prefix, suffix, n=MLM_TOP_K * 4):
        """Top predicted single-piece fillers for prefix<mask>suffix, as (text, prob)."""
        enc = self.tok(prefix + self.tok.mask_token + suffix, return_tensors='pt', truncation=True)
        with self.torch.no_grad():
            logits = self.model(**enc).logits[0]
        pos = (enc['input_ids'][0] == self.tok.mask_token_id).nonzero()[0, 0]
        top = logits[pos].softmax(-1).topk(n)
        out = []
        for p, i in zip(top.values.tolist(), top.indices.tolist()):
            piece = self.tok.convert_ids_to_tokens(i).replace('▁', '').strip()
            if piece and not is_punct(piece) and i not in self.tok.all_special_ids:
                out.append((piece, p))
        return out

    def score(self, prefix, suffix, candidates):
        """Mean log-prob of each candidate's pieces when its span is masked (batched)."""
        if not candidates:
            return []
        texts, spans = [], []
        for c in candidates:
            ids = self.tok(c, add_special_tokens=False)['input_ids']
            ids = [i for i in ids if self.tok.convert_ids_to_tokens(i) != '▁'] or ids
            texts.append(prefix + self.tok.mask_token * len(ids) + suffix)
            spans.append(ids)
        enc = self.tok(texts, return_tensors='pt', padding=True, truncation=True)
        with self.torch.no_grad():
            logp = self.model(**enc).logits.log_softmax(-1)
        scores = []
        for b, ids in enumerate(spans):
            pos = (enc['input_ids'][b] == self.tok.mask_token_id).nonzero().flatten().tolist()
            if len(pos) != len(ids):
                scores.append(float('-inf'))
                continue
            scores.append(sum(logp[b, p, i].item() for p, i in zip(pos, ids)) / len(ids))
        return scores


def _context(us, ui, ti):
    """Text before and after token ti of unit ui."""
    before = [t for u in us[:ui] for t in u.tokens] + us[ui].tokens[:ti]
    after = us[ui].tokens[ti + 1:] + [t for u in us[ui + 1:] for t in u.tokens]
    prefix = ''.join(t.ws + t.surface for t in before) + us[ui].tokens[ti].ws
    return prefix.lstrip(), ''.join(t.ws + t.surface for t in after)


def _sample(cands, rng):
    """cands: [(text, weight)] -> one text, weighted."""
    total = sum(w for _, w in cands)
    r, acc = rng.random() * total, 0.0
    for c, w in cands:
        acc += w
        if acc >= r:
            return c
    return cands[-1][0]


def _meaning_sub(us, ui, rng, res):
    t = us[ui].head
    if is_latin(t.surface) or t.pos not in CONTENT_POS:
        return False
    if t.pos in ('動詞', '形容詞') and not t.cform.startswith(DICT_FORMS):
        return False  # synonyms come in dictionary form
    syns = res.synonyms(t.lemma, t.kana)
    if not syns:
        return False
    syns = sorted(syns, key=lambda s: (abs(len(s) - len(t.surface)), s))[:12]
    prefix, suffix = _context(us, ui, us[ui].content)
    scored = sorted(zip(res.mlm.score(prefix, suffix, syns), syns), reverse=True)[:3]
    t.surface = rng.choice([s for _, s in scored])
    return True


def _sound_sub(us, ui, rng, res):
    t = us[ui].head
    if not t.kana or is_latin(t.surface) or t.pos not in CONTENT_POS:
        return False
    cands = res.sound_neighbours(t.kana, t.pos, t.lemma)
    if not cands:
        return False
    t.surface = rng.choice(cands)
    return True


def _function_change(us, ui, rng, res):
    tail = [i for i, t in enumerate(us[ui].tokens) if i != us[ui].content and t.pos == '助詞']
    if not tail:
        return False
    i = rng.choice(tail)
    t = us[ui].tokens[i]
    key = (t.surface, t.pos2)
    swaps = sorted({p for s in PARTICLE_SETS if key in s for p, _ in s} - {t.surface})
    if swaps and rng.random() < 0.5:
        t.surface = rng.choice(swaps)
    else:
        del us[ui].tokens[i]
    return True


def _context_sub(us, ui, rng, res):
    t = us[ui].head
    if t.pos not in CONTENT_POS:
        return False
    prefix, suffix = _context(us, ui, us[ui].content)
    original = unicodedata.normalize('NFKC', t.surface).lower()
    want_latin = is_latin(t.surface)
    cands = []
    for c, p in res.mlm.fill(prefix, suffix):
        if unicodedata.normalize('NFKC', c).lower() == original or is_latin(c) != want_latin:
            continue
        if want_latin and c.lower() not in res.vocab[1]:
            continue  # XLM-R also proposes other languages' words
        if not want_latin:
            parsed = list(_tag(c))
            if len(parsed) != 1 or _f(parsed[0], 'pos1') != t.pos:
                continue
            if t.cform and _f(parsed[0], 'cForm') != t.cform:
                continue
        cands.append((c, p))
        if len(cands) == MLM_TOP_K:
            break
    if not cands:
        return False
    t.surface = _sample(cands, rng)
    return True


def _homophone(us, ui, rng, res):
    t = us[ui].head
    if not (t.kana and has_kanji(t.surface)):
        return False
    others = sorted(s for s, (lem, _) in res.lexicon.get(t.kana, {}).items() if s != t.surface and lem != t.lemma)
    t.surface = rng.choice(others) if others else kata_to_hira(t.kana)
    return True


EDITS = {'meaning_sub': _meaning_sub, 'sound_sub': _sound_sub, 'function_change': _function_change,
         'context_sub': _context_sub, 'homophone': _homophone}


def perturb(text, ptype, rate, rng, res):
    """Return (perturbed text, fraction of units changed), or None if nothing applicable."""
    us = units(text)
    word_idx = [i for i, u in enumerate(us) if not u.punct]
    n = len(word_idx)
    if n < 2:
        return None
    k = min(n - 1, max(1, round(rate * n)))
    order = rng.sample(word_idx, n)
    changed, drop = 0, set()
    for ui in order:
        if changed == k:
            break
        if ptype == 'drop':
            drop.add(ui)
            changed += 1
            continue
        if ptype == 'mixed':
            options = rng.sample(MIXED_PARTS, len(MIXED_PARTS))
            for action in options:
                if action == 'drop':
                    drop.add(ui)
                    changed += 1
                    break
                if EDITS[action](us, ui, rng, res):
                    changed += 1
                    break
            continue
        if EDITS[ptype](us, ui, rng, res):
            changed += 1
    if not changed:
        return None
    kept = [u for i, u in enumerate(us) if i not in drop]
    return join_units(kept), changed / n
