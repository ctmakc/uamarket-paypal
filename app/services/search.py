"""Shop search in two languages and two alphabets.

A shopper types "вишиванки", "vyshyvanka", "blouse" or "Opishnia" and means the same shelf.
Three things make that work, and all three run on the query and on the product text alike:

* folding: case, accents and apostrophes are removed (ї and й stay distinct letters of the
  word, then transliteration maps them the same way on both sides);
* transliteration: Ukrainian is also written in Latin by the national 2010 table, so
  "рушник" and "rushnyk" become the same token;
* a synonym table: words that name the same kind of thing across the two languages
  ("blouse", "сорочка", "embroidered shirt" all reach the vyshyvanka shelf).

Matching is by word prefix after a light stem (plural and case endings removed), so
"вишиванк", "вишиванки" and "vyshyvanky" all match "Жіночі вишиванки". Every word of the
query has to match something (AND); a word matches when it or any of its synonyms does (OR).
Category and collection names are part of what is searched.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

# Ukrainian national transliteration (Cabinet of Ministers resolution 55, 2010), simplified:
# the word-initial forms of є, ї, й, ю, я are used everywhere, which matches how the shop's
# own Latin names are spelled (Opishnia, Reshetylivka).
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ie", "ж": "zh", "з": "z",
    "и": "y", "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ь": "", "ю": "iu", "я": "ia",
    # Russian letters a shopper may type out of habit
    "ы": "y", "э": "e", "ё": "io", "ъ": "",
}

# Groups of words that name one thing. The first word is only a label for the group.
SYNONYMS: list[list[str]] = [
    ["vyshyvanka", "вишиванка", "вишиванки", "vyshyvanky", "вышиванка", "vishivanka",
     "blouse", "блуза", "блузка", "shirt", "сорочка", "сорочки", "рубашка", "kosovorotka"],
    ["embroidery", "вишивка", "embroidered", "вишитий", "вишита", "вишиті", "cross-stitch", "хрестик"],
    ["rushnyk", "рушник", "рушники", "rushnyky", "ручник", "towel", "embroidered towel", "wedding towel"],
    ["motanka", "мотанка", "мотанки", "motanky", "doll", "dolls", "лялька", "ляльки", "кукла", "rag doll"],
    ["ceramics", "кераміка", "ceramic", "pottery", "гончарство", "глина", "clay", "опішня", "opishnia", "opishnya",
     "mug", "чашка", "cup", "bowl", "миска", "lion"],
    ["dress", "сукня", "плаття", "сукні"],
    ["runner", "доріжка", "table runner", "tablecloth", "скатертина", "обрус"],
    ["kids", "дитяче", "дитячий", "дитяча", "діти", "дітям", "children", "child", "kid", "baby", "дитина"],
    ["women", "жіночі", "жіноча", "жіночий", "woman", "womens", "ladies", "жінки"],
    ["men", "чоловічі", "чоловіча", "чоловічий", "mens", "чоловіки"],
    ["gift", "gifts", "подарунок", "подарунки", "present", "сувенір", "souvenir"],
    ["pin", "pins", "значок", "значки", "badge", "enamel", "емаль"],
    ["tote", "торба", "сумка", "bag", "шопер", "shopper"],
    ["card", "cards", "листівка", "листівки", "postcard", "greeting"],
    ["linen", "льон", "лляна", "лляний", "лляні", "flax"],
    ["keychain", "брелок", "keyring"],
    ["home", "дім", "дому", "домашній", "table", "стіл", "interior"],
    ["whitework", "біле по білому", "білим по білому", "white on white", "решетилівка", "reshetylivka"],
    ["nyzynka", "низинка", "косів", "kosiv", "hutsul", "гуцульська"],
    ["borshchiv", "борщів", "борщівська", "black embroidery", "чорна вишивка"],
]

_UK_ENDINGS = ("ами", "ями", "ові", "еві", "ого", "ому", "ими", "ій", "ів", "ей", "ою", "ею", "ах", "ях", "ом", "ем",
               "ий", "ій", "а", "я", "и", "і", "у", "ю", "о", "е", "ь", "й")
_EN_ENDINGS = ("ies", "es", "s", "'s")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def fold(text: str | None) -> str:
    """Lower case, accents off, apostrophes and hyphens joined, whitespace collapsed."""
    value = (text or "").casefold()
    value = value.replace("’", "").replace("'", "").replace("ʼ", "").replace("`", "")
    value = unicodedata.normalize("NFKD", value)
    # й and ї decompose into и/і plus a mark; keep them whole before dropping marks.
    value = value.replace("й", "й").replace("ї", "ї")
    value = "".join(ch for ch in value if not unicodedata.combining(ch) or ch in "̆̈")
    value = unicodedata.normalize("NFKC", value)
    return value


def translit(word: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in word)


def stem(word: str) -> str:
    """A light stem: one inflection ending off, never shorter than four letters."""
    if re.search(r"[а-яіїєґ]", word):
        for end in _UK_ENDINGS:
            if word.endswith(end) and len(word) - len(end) >= 4:
                return word[: -len(end)]
        return word
    for end in _EN_ENDINGS:
        if word.endswith(end) and len(word) - len(end) >= 3:
            return word[: -len(end)]
    return word


def _latin_stem(word: str) -> str:
    """Stem after transliteration, so -y/-a/-i endings of transliterated Ukrainian fold too."""
    latin = translit(word)
    for end in ("iamy", "amy", "iakh", "akh", "ov", "iv", "oiu", "eiu", "om", "em", "yi", "ii", "y", "a", "i", "ia", "u", "iu", "o", "e", "s"):
        if latin.endswith(end) and len(latin) - len(end) >= 4:
            return latin[: -len(end)]
    return latin


def words(text: str | None) -> list[str]:
    return _WORD.findall(fold(text))


def keys(word: str) -> set[str]:
    """Every form a word can be matched in: native stem, Latin stem."""
    return {stem(word), _latin_stem(word)}


def _synonym_index() -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for group in SYNONYMS:
        # One-word entries only: the words of "wedding towel" on their own would pull every
        # "wedding" and every "towel" into the group.
        single = [ws[0] for ws in (words(phrase) for phrase in group) if len(ws) == 1]
        forms: set[str] = set()
        for w in single:
            forms |= keys(w)
        for w in single:
            for k in keys(w):
                index.setdefault(k, set()).update(forms)
    return index


_SYN = _synonym_index()


def expand(word: str) -> set[str]:
    """The keys one query word may match: its own forms and those of its synonyms."""
    own = keys(word)
    out = set(own)
    for k in own:
        out |= _SYN.get(k, set())
        # A query word that is the start of a synonym ("вишиван") reaches that group too.
        if len(k) >= 4:
            for syn_key, forms in _SYN.items():
                if syn_key.startswith(k):
                    out |= forms
    return {k for k in out if len(k) >= 2}


def haystack_keys(*texts: str | None) -> set[str]:
    out: set[str] = set()
    for text in texts:
        for w in words(text):
            out |= keys(w)
            out.add(w)
            out.add(translit(w))
    return out


def query_terms(q: str | None) -> list[set[str]]:
    """One set of acceptable keys per query word. Words of one letter are ignored."""
    return [expand(w) for w in words(q) if len(w) >= 2]


def matches(terms: list[set[str]], hay: set[str]) -> bool:
    if not terms:
        return True
    for options in terms:
        if not any(h.startswith(opt) for opt in options for h in hay):
            return False
    return True


def closest(query: str | None, candidates: list[tuple[str, list[str]]]) -> str | None:
    """The candidate key whose names look most like the query (difflib ratio, Latin-folded).

    Always returns something while there are candidates: an empty search result offers the
    nearest shelf rather than nothing.
    """
    if not candidates:
        return None
    q = " ".join(_latin_stem(w) for w in words(query)) or ""
    best, best_score = candidates[0][0], -1.0
    for key, names in candidates:
        for name in names:
            latin = " ".join(_latin_stem(w) for w in words(name))
            score = difflib.SequenceMatcher(None, q, latin).ratio()
            for w in words(query):
                for nw in words(name):
                    score = max(score, difflib.SequenceMatcher(None, _latin_stem(w), _latin_stem(nw)).ratio())
            if score > best_score:
                best, best_score = key, score
    return best
