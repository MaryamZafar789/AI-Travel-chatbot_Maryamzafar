"""
Local Retrieval-Augmented Generation layer.

PROTOTYPE NOTE: uses scikit-learn TF-IDF + cosine similarity as a stand-in
for a real local multilingual embedding model + vector database. See
README.md for the production upgrade path.

CHANGES from the technical assessment (destination leakage, section 2.1 /
P0; limited retrieval controls, section 2.4):
  - retrieve() now takes an explicit `destination` argument. When a
    destination is known, only chunks whose `country` field matches
    EXACTLY are considered -- category-only filtering (the old behavior)
    is what let a UAE visa question return Turkey/UK results.
  - Default result count dropped from 3 to 1 (top_k default), per the
    assessment's "top-1 selection by default" requirement. Callers can
    still request more when deliberately comparing multiple chunks.
  - Expired records (older than FRESHNESS_DAYS) are excluded from the
    index entirely, addressing "outdated records are not automatically
    excluded".
  - Chunk exposes source_url/last_checked so the caller can surface them
    to the user (assessment: "Source URLs and verification dates are not
    displayed to users").
"""
import json
import re
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DATA_PATH = Path(__file__).parent / "data" / "knowledge_base.jsonl"

MIN_RELEVANCE_SCORE = 0.12
FRESHNESS_DAYS = 180

_WORD_RE = re.compile(r"[a-zA-Z']+")


def _stem(word: str) -> str:
    for suffix in ("ies",):
        if word.endswith(suffix) and len(word) > 4:
            return word[: -len(suffix)] + "y"
    for suffix in ("ing", "es", "s"):
        if word.endswith(suffix) and len(word) > 4 and not word.endswith("ss"):
            return word[: -len(suffix)]
    return word


def _stem_tokenizer(text: str) -> list:
    return [_stem(w) for w in _WORD_RE.findall(text.lower())]


@dataclass
class Chunk:
    chunk_id: str
    category: str
    country: str
    service: str
    content: str
    source_url: str
    last_checked: str
    status: str

    def is_fresh(self, today: Optional[date] = None) -> bool:
        today = today or date.today()
        try:
            checked = datetime.strptime(self.last_checked, "%Y-%m-%d").date()
        except ValueError:
            return False
        return (today - checked).days <= FRESHNESS_DAYS


class LocalKnowledgeBase:
    def __init__(self, path: Path = DATA_PATH):
        self.chunks: list[Chunk] = []
        self._load(path)
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._matrix = None
        self._build_index()

    def _load(self, path: Path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                self.chunks.append(Chunk(**row))

    def _build_index(self):
        approved = [c for c in self.chunks if c.status == "approved" and c.is_fresh()]
        self._approved_chunks = approved
        corpus = [f"{c.category} {c.country} {c.service} {c.content}" for c in approved]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self._vectorizer = TfidfVectorizer(lowercase=True, tokenizer=_stem_tokenizer, ngram_range=(1, 2))
            self._matrix = self._vectorizer.fit_transform(corpus) if corpus else None

    def reindex(self):
        self._build_index()

    def retrieve(
        self,
        query: str,
        category: Optional[str] = None,
        destination: Optional[str] = None,
        top_k: int = 1,
    ):
        """
        Returns [(Chunk, score), ...] for chunks clearing MIN_RELEVANCE_SCORE.

        Filtering order (strict -> loose), per assessment P0:
          1. category (if known)
          2. destination / country (if known) -- EXACT match only. If a
             destination is known but nothing in this category matches it
             exactly, returns [] rather than falling back to a different
             country's chunk. That empty result tells the caller to say
             "information unavailable" instead of showing unrelated content.
        """
        if self._matrix is None or not self._approved_chunks:
            return []

        candidates = self._approved_chunks
        matrix = self._matrix

        if category:
            idx = [i for i, c in enumerate(candidates) if c.category == category]
            candidates = [candidates[i] for i in idx]
            matrix = matrix[idx] if idx else matrix[[]]

        if destination:
            idx = [i for i, c in enumerate(candidates) if c.country == destination]
            candidates = [candidates[i] for i in idx]
            matrix = matrix[idx] if idx else matrix[[]]
            if not candidates:
                return []

        if not candidates:
            return []

        query_vec = self._vectorizer.transform([query])
        scores = cosine_similarity(query_vec, matrix)[0]

        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        results = [(c, float(s)) for c, s in ranked if s >= MIN_RELEVANCE_SCORE]
        return results[:top_k]


kb = LocalKnowledgeBase()
