"""Search terms for code: identifiers split into words, stemmed, without noise.

`parseHTTPResponse` and `parse_http_response` both become `parse http respons`, so a
question in plain words ("where do we parse the HTTP response?") meets the code it is
about. The same function prepares index terms and query terms, which is what makes the
keyword ranking consistent. `concepts()` maps words to a small lexicon of programming
concepts ("remove" and "delete" share one), used by the local embedder.
"""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*|\d+")
_PIECE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+\d*|[A-Z]+\d*|\d+")
_SEPARATORS = re.compile(r"[_$]+")

_ENGLISH = """a about above after again against all am an and any are as at be because been before
being below between both but by can could did do does doing down during each few for from
further had has have having he her here hers him his how i if in into is it its itself just
me more most my no nor not now of off on once only or other our out over own same she should
so some such than that the their them then there these they this those through to too under
until up very was we were what when where which while who whom why will with would you your
please much many tell show give list does know need want get got use used using like make say
see look find take come go must may might shall code repo repository file files"""
# Keywords and ubiquitous names carry no meaning for search in any of the indexed languages.
_KEYWORDS = """def class return self cls import from as if else elif for while in is not and or
none true false null nil undefined function func const let var new this async await try
except finally raise throw throws catch with yield lambda pass break continue public private
protected static void int str bool float double string number boolean any type interface
export default package struct go defer chan map range switch case enum extends implements
super args kwargs fmt err"""
STOPWORDS = frozenset(_ENGLISH.split()) | frozenset(_KEYWORDS.split())

# Groups of words that name the same idea in code. Deliberately small and general: it
# helps the offline embedder connect "remove a user" with `delete_account`.
_CONCEPT_GROUPS: dict[str, str] = {
    "delete": "delete remove drop erase destroy discard purge unlink clear",
    "create": "create add insert new make build construct register spawn",
    "read": "get fetch load read retrieve find lookup query select obtain resolve",
    "write": "update set modify change edit patch put write save store persist upsert",
    "compute": "compute calculate calc calculation evaluate derive estimate",
    "money": "money price cost amount currency cent cents dollar euro payment pay fee balance",
    "tax": "tax vat gst levy duty",
    "discount": "discount rebate coupon promo promotion markdown reduction",
    "error": "error exception fail failure fault invalid bad raise",
    "validate": "check validate verify ensure assert guard sanitize",
    "convert": "convert parse format serialize deserialize encode decode render stringify",
    "auth": "auth authenticate authentication login logout signin signup session token password "
    "credential",
    "account": "user account member customer person profile",
    "collection": "list array collection items sequence entries batch chunk",
    "count": "count total sum tally aggregate",
    "round": "round rounding quantize precision decimal",
    "time": "time date datetime timestamp clock duration timeout deadline schedule",
    "config": "config configuration settings options preferences env environment",
    "log": "log logger logging trace debug",
    "cache": "cache memo memoize memoization",
    "send": "send emit publish notify dispatch post",
    "receive": "receive consume subscribe listen handle handler callback",
    "start": "start begin init initialize open launch boot setup",
    "stop": "stop end close shutdown finish terminate teardown",
    "sort": "sort order rank compare",
    "filter": "filter exclude include where match search",
    "test": "test tests spec fixture mock expect",
    "invoice": "invoice bill receipt statement",
    "item": "line item entry row record",
    "path": "file path directory folder dir",
    "http": "http request response api endpoint route url client server",
    "database": "database db sql table schema migration",
    "text": "text string slug slugify truncate name title label",
    "number": "number integer float ratio percent percentage fraction",
    "rate": "rate limit throttle quota",
    "retry": "retry backoff attempt",
}


def stem(word: str) -> str:
    """A light, consistent stemmer: hire, hires, hired and hiring all become "hir".

    Applied identically to the index and to queries, which is all ranking needs. Tokens
    with digits are left alone.
    """
    if len(word) <= 3 or not word.isalpha():
        return word
    for suffix, replacement in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)] + replacement
            break
    if len(word) > 4 and word[-1] == word[-2] and word[-1] not in "lsz":
        word = word[:-1]
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    return word


def _concept_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for concept, words in _CONCEPT_GROUPS.items():
        for word in words.split():
            index.setdefault(word, concept)
            index.setdefault(stem(word), concept)
    return index


_CONCEPTS = _concept_index()


def split_identifier(name: str) -> list[str]:
    """`parseHTTPResponse` -> parse, http, response; `calc_tax_v2` -> calc, tax, v2."""
    words: list[str] = []
    for piece in _SEPARATORS.split(name):
        words.extend(match.group(0).lower() for match in _PIECE.finditer(piece))
    return [word for word in words if word]


def words(text: str) -> list[str]:
    """Every identifier and word in `text`, split and lowercased (stop words kept)."""
    out: list[str] = []
    for token in _TOKEN.findall(text):
        out.extend(split_identifier(token))
    return out


def terms(text: str) -> list[str]:
    """Stemmed search terms in order, without stop words, keywords or single letters."""
    return [stem(w) for w in words(text) if w not in STOPWORDS and len(w) > 1 and not w.isdigit()]


def unique_terms(text: str, limit: int = 64) -> list[str]:
    return list(dict.fromkeys(terms(text)))[:limit]


def concepts(term: str) -> str | None:
    return _CONCEPTS.get(term)


def identifiers(text: str) -> list[str]:
    """Code-like names in a question: `quoted`, snake_case, camelCase or Dotted.names."""
    quoted = re.findall(r"`([^`\n]{1,120})`", text)
    names = [part for q in quoted for part in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", q)]
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", text):
        last = token.rsplit(".", 1)[-1]
        if (
            "_" in last
            or "." in token
            or re.search(r"[a-z][A-Z]", last)
            or re.match(r"[A-Z][a-z]+[A-Z]", last)
        ):
            names.append(token)
    return list(dict.fromkeys(name.strip(".") for name in names if len(name) > 1))
