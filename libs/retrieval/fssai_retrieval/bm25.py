"""Okapi BM25 over the chunks' embedded text (heading + clause). The lexical half of hybrid retrieval.

Regulation text is full of exact terms ("source", "per 100 kcal", "Schedule I") that a small sentence
embedding blurs together; BM25 matches them exactly. Kept dependency-free: the corpus is ~400 chunks.
"""
from __future__ import annotations

import math
import re
from collections import Counter

_STOP = frozenset("""a an and are as at be by for from has have in into is it its of on or such that the
their these this to was were which with shall may any all other than""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tf = [Counter(tokenize(d)) for d in docs]
        self.len = [sum(tf.values()) for tf in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 0.0
        df: Counter = Counter()
        self.postings: dict[str, list[int]] = {}
        for i, tf in enumerate(self.tf):
            for term in tf:
                df[term] += 1
                self.postings.setdefault(term, []).append(i)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def scores(self, query: str) -> dict[int, float]:
        out: dict[int, float] = {}
        for term in set(tokenize(query)):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i in self.postings[term]:
                f = self.tf[i][term]
                norm = f + self.k1 * (1 - self.b + self.b * self.len[i] / (self.avg or 1))
                out[i] = out.get(i, 0.0) + idf * f * (self.k1 + 1) / norm
        return out

    def top(self, query: str, n: int, allowed: set[int] | None = None) -> list[tuple[int, float]]:
        scored = [(i, s) for i, s in self.scores(query).items() if allowed is None or i in allowed]
        scored.sort(key=lambda t: (-t[1], t[0]))
        return scored[:n]
