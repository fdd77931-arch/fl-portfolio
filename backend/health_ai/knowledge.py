"""Structured source catalog, BM25, and a version-bound SQLite vector index."""
import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from collections import Counter
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

from .models import ModelUnavailable

SEED = Path(__file__).resolve().parents[2] / "demos" / "xunji" / "evidence.json"
Collection = Literal["disease_knowledge", "clinical_guidelines", "medical_literature",
                     "laboratory_reference", "medication_information", "health_management"]
Domain = Literal["cardiovascular", "metabolic", "respiratory", "digestive", "renal", "neurology",
                 "oncology", "infection", "sleep_mental", "musculoskeletal", "maternal_child", "geriatrics"]


class Source(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")
    document_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")
    title: str = Field(min_length=2, max_length=320)
    publisher: str = Field(min_length=2, max_length=180)
    url: HttpUrl
    year: int | None = Field(default=None, ge=1800, le=2100)
    version: str = Field(min_length=1, max_length=120)
    section: str = Field(min_length=1, max_length=220)
    page_number: int | None = Field(default=None, ge=1)
    doi: str | None = Field(default=None, pattern=r"^10\.\d{4,9}/[^\s]+$", max_length=180)
    pmid: str | None = Field(default=None, pattern=r"^[1-9]\d{0,11}$")
    license: str = Field(min_length=2, max_length=240)
    verified_at: date
    status: Literal["verified", "superseded", "unverified"]
    collection: Collection
    domain: Domain
    disease: str | None = Field(default=None, max_length=120)
    terms: list[str] = Field(min_length=1, max_length=32)
    text: str = Field(min_length=20, max_length=2400)
    excerpt_kind: Literal["summary", "original"] = "summary"

    @field_validator("url")
    @classmethod
    def validate_https(cls, url):
        if url.scheme != "https" or url.username or url.password:
            raise ValueError("Sources require public HTTPS links")
        return url

    @field_validator("terms")
    @classmethod
    def validate_terms(cls, terms):
        if any(not 2 <= len(term.strip()) <= 80 for term in terms):
            raise ValueError("Terms must contain 2–80 characters")
        return terms

    def passage(self):
        return f"{self.title}\n{self.section}\n{'；'.join(self.terms)}\n{self.text}"


def tokens(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    for word in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", normalized):
        if "\u3400" <= word[0] <= "\u9fff":
            yield from (word[i:i + 2] for i in range(len(word) - 1))
        else:
            yield word


def matching_terms(question, sources):
    normalized = unicodedata.normalize("NFKC", question).casefold()
    return [source for source in sources if any(
        (term.casefold() in normalized if re.search(r"[\u3400-\u9fff]", term)
         else re.search(r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", normalized))
        for term in source.terms
    )]


def bm25(query, sources):
    query_terms = set(tokens(query))
    if not sources or not query_terms:
        return []
    counts = {source.id: Counter(tokens(source.passage())) for source in sources}
    lengths = {key: sum(words.values()) for key, words in counts.items()}
    average = sum(lengths.values()) / len(lengths)
    frequencies = Counter(term for words in counts.values() for term in words.keys() & query_terms)
    scores = {}
    for key, words in counts.items():
        normalization = 1.2 * (0.25 + 0.75 * lengths[key] / average)
        scores[key] = sum(
            math.log1p((len(sources) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            * words[term] * 2.2 / (words[term] + normalization)
            for term in query_terms & words.keys()
        )
    return sorted((key for key, score in scores.items() if score > 0), key=scores.get, reverse=True)


def unit_vector(vector):
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm or not math.isfinite(norm):
        raise ModelUnavailable("invalid_vector")
    return [value / norm for value in vector]


class Catalog:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.seed = [Source.model_validate(row) for row in json.loads(SEED.read_text(encoding="utf-8"))]
        with self.connect() as sql:
            sql.execute("CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, source TEXT NOT NULL)")
            sql.execute("CREATE TABLE IF NOT EXISTS vectors (id TEXT PRIMARY KEY, identity TEXT NOT NULL, vector TEXT NOT NULL)")
            sql.execute("CREATE TABLE IF NOT EXISTS import_assets (id TEXT PRIMARY KEY, media_type TEXT, original BLOB)")

    @contextmanager
    def connect(self):
        sql = sqlite3.connect(self.db_path, timeout=10)
        try:
            with sql:
                yield sql
        finally:
            sql.close()

    def rows(self, sql):
        sources = {source.id: source for source in self.seed}
        sources.update({key: Source.model_validate_json(value) for key, value in sql.execute("SELECT id, source FROM entries")})
        return list(sources.values())

    def sources(self):
        with self.connect() as sql:
            return self.rows(sql)

    @staticmethod
    def signature(source, models):
        return hashlib.sha256((models.identity + "\0" + source.passage()).encode()).hexdigest()

    def state(self, models):
        with self.connect() as sql:
            sql.execute("BEGIN")
            sources = [source for source in self.rows(sql) if source.status == "verified"]
            stored = {key: (identity, vector) for key, identity, vector in
                      sql.execute("SELECT id, identity, vector FROM vectors")}
        vectors = {
            source.id: json.loads(stored[source.id][1]) for source in sources
            if source.id in stored and stored[source.id][0] == self.signature(source, models)
        }
        return sources, vectors

    def reindex(self, models):
        sources, existing = self.state(models)
        pending = [source for source in sources if source.id not in existing]
        for offset in range(0, len(pending), 8):
            batch = pending[offset:offset + 8]
            vectors = models.embedding_service([source.passage() for source in batch])
            with self.connect() as sql:
                sql.execute("BEGIN IMMEDIATE")
                current = {source.id: source for source in self.rows(sql)}
                for source, vector in zip(batch, vectors, strict=True):
                    if source == current.get(source.id):
                        self.write_vector(sql, source, models, vector)
        return len(pending)

    def write_vector(self, sql, source, models, vector):
        sql.execute("INSERT OR REPLACE INTO vectors VALUES (?, ?, ?)",
                    (source.id, self.signature(source, models), json.dumps(unit_vector(vector))))

    def import_sources(self, sources, models, original=None):
        if len({source.id for source in sources}) != len(sources):
            raise ValueError("duplicate_chunk_id")
        verified = [source for source in sources if source.status == "verified"]
        embeddings = {}
        for offset in range(0, len(verified), 8):
            batch = verified[offset:offset + 8]
            vectors = models.embedding_service([source.passage() for source in batch])
            embeddings.update((source.id, vector) for source, vector in zip(batch, vectors, strict=True))
        with self.connect() as sql:
            sql.execute("BEGIN IMMEDIATE")
            for source in sources:
                sql.execute("INSERT OR REPLACE INTO entries VALUES (?, ?)", (source.id, source.model_dump_json()))
                sql.execute("DELETE FROM vectors WHERE id = ?", (source.id,))
                if source.id in embeddings:
                    self.write_vector(sql, source, models, embeddings[source.id])
                if original:
                    sql.execute("INSERT OR REPLACE INTO import_assets VALUES (?, ?, ?)", (source.id, *original))

    def retrieve(self, question, models, min_score):
        sources, vectors = self.state(models)
        if not sources or len(vectors) != len(sources):
            raise ModelUnavailable("index_missing_or_stale")
        by_id = {source.id: source for source in sources}
        matched = matching_terms(question, sources)
        lexical = bm25(question, sources)[:20]
        query_vector, = models.embedding_service([question])
        query_vector = unit_vector(query_vector)
        if any(len(vector) != len(query_vector) for vector in vectors.values()):
            raise ModelUnavailable("index_dimension_mismatch")

        def similarity(key):
            return sum(x * y for x, y in zip(query_vector, vectors[key], strict=True))

        semantic = sorted(vectors, key=similarity, reverse=True)[:20]
        fused = Counter()
        for ranked in (lexical, semantic):
            for index, key in enumerate(ranked):
                fused[key] += 1 / (60 + index + 1)
        candidates = [by_id[key] for key, _ in fused.most_common()]
        ranked = models.rerank_service(question, [source.passage() for source in candidates], min(8, len(candidates)))
        # A purely semantic match needs stronger agreement across both models.
        evidence = [
            candidates[i] for i, score in ranked
            if score >= min_score and (
                matched or (score >= max(min_score, 0.8) and similarity(candidates[i].id) >= 0.42)
            )
        ]
        return evidence, {
            "domains": sorted({source.domain for source in matched or evidence}),
            "bm25": lexical, "vector": semantic, "fused": [source.id for source in candidates],
            "documents": {source.id: source.document_id for source in candidates}
        }
