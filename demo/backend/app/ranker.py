"""Lexical overlap, with fastembed when the model is available."""

from __future__ import annotations

import os
import re

_WORD = re.compile(r"[a-z0-9]+(?:[.][0-9]+)?")


def _words(text: str) -> list[str]:
    words = []
    for word in _WORD.findall(text.lower()):
        if len(word) >= 4 or any(ch.isdigit() for ch in word):
            words.append(word)
    return words


def _same_token(word: str, other: str) -> bool:
    if word == other:
        return True
    if min(len(word), len(other)) < 4:
        return False
    if word.startswith(other) or other.startswith(word):
        return abs(len(word) - len(other)) <= 3
    return False


def lexical_score(query: str, text: str, df: dict[str, int] | None = None) -> float:
    """Overlap of the question and a graph string.

    When ``df`` is provided, a token that labels many graph strings does not
    count. That keeps the word "account" from grounding every account.
    A single rare token raises the score only for a short string or a number.
    """
    q = re.sub(r"(\d+)\s+and a half", r"\1.5", query.lower().replace("-", " "))
    t = text.lower().strip()
    if len(t) >= 4 and t in q:
        return 1.0
    q_words = set(_words(q))
    t_words = _words(t)
    if not t_words or not q_words:
        return 0.0
    hit = []
    for word in set(t_words):
        matched = any(_same_token(word, other) for other in q_words)
        if not matched:
            continue
        if df is not None and df.get(word, 0) > 8:
            continue
        hit.append(word)
    if not hit:
        return 0.0
    ratio = len(hit) / len(set(t_words))
    exact = [
        word for word in hit
        if word in q_words and (df is None or df.get(word, 0) <= 8)
    ]
    numbered = any(any(ch.isdigit() for ch in word) for word in exact)
    if exact and (len(set(t_words)) <= 2 or numbered):
        return max(ratio, 0.85)
    return ratio


class Ranker:
    def __init__(self) -> None:
        self.mode = "lexical"
        self._model = None
        self._cache: dict[str, list[float]] = {}
        choice = os.environ.get("RANKER", "auto")
        if choice == "lexical":
            return
        try:
            from fastembed import TextEmbedding

            self._model = TextEmbedding("BAAI/bge-small-en-v1.5")
            self.mode = "embed"
        except Exception:
            self.mode = "lexical"

    def _vector(self, text: str) -> list[float] | None:
        if self._model is None:
            return None
        if text not in self._cache:
            vec = next(self._model.embed([text]))
            self._cache[text] = [float(x) for x in vec]
        return self._cache[text]

    def score(self, query: str, text: str, df: dict[str, int] | None = None) -> float:
        lexical = lexical_score(query, text, df)
        left = self._vector(query)
        right = self._vector(text)
        if not left or not right:
            return lexical
        dot = sum(a * b for a, b in zip(left, right))
        na = sum(a * a for a in left) ** 0.5
        nb = sum(b * b for b in right) ** 0.5
        cosine = dot / (na * nb) if na and nb else 0.0
        return max(lexical, cosine)
