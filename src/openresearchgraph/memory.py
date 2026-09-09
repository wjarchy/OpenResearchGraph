from __future__ import annotations

import hashlib
import json
import math
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .storage import Repository
from .tools.base import ToolContext, ToolResult

if TYPE_CHECKING:
    from .config import Settings


def _terms(text: str) -> list[str]:
    latin = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    chinese = [char for char in text if "\u4e00" <= char <= "\u9fff"]
    return latin + chinese


class HashEmbedding:
    """Deterministic local embedding suitable for demos, tests, and privacy-first fallback."""

    def __init__(self, dimensions: int = 96) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for term in _terms(text):
            digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


class TwoLayerMemory:
    """Short session memory plus long-term semantic knowledge with hybrid retrieval."""

    def __init__(self, repository: Repository, embedder: HashEmbedding | None = None) -> None:
        self.repository = repository
        self.embedder = embedder or HashEmbedding()
        self._short_cache: dict[str, dict[str, Any]] = {}

    def remember_session(
        self, session_id: str, summary: str, preferences: dict[str, Any] | None = None
    ) -> None:
        value = {"summary": summary, "preferences": preferences or {}}
        self._short_cache[session_id] = value
        self.repository.upsert_short_memory(session_id, summary, value["preferences"])

    def remember_knowledge(
        self, content: str, metadata: dict[str, Any] | None = None, memory_id: str | None = None
    ) -> str:
        identifier = memory_id or f"mem-{uuid4().hex[:12]}"
        self.repository.put_long_memory(
            identifier,
            content,
            self.embedder.embed(content),
            metadata or {},
        )
        return identifier

    def recall(self, session_id: str, query: str, limit: int = 4) -> list[str]:
        context: list[str] = []
        short = self._short_cache.get(session_id)
        if short is None:
            short = self.repository.get_short_memory(session_id)
            if short:
                self._short_cache[session_id] = short
        if short:
            preferences = short.get("preferences", {})
            context.append(f"会话摘要：{short['summary']}")
            if preferences:
                rendered = "、".join(f"{key}={value}" for key, value in sorted(preferences.items()))
                context.append(f"表达偏好：{rendered}")

        query_vector = self.embedder.embed(query)
        query_terms = set(_terms(query))
        ranked: list[tuple[float, str]] = []
        for memory in self.repository.all_long_memories():
            memory_terms = set(_terms(memory["content"]))
            lexical = len(query_terms & memory_terms) / (len(query_terms | memory_terms) or 1)
            semantic = max(0.0, _cosine(query_vector, memory["embedding"]))
            score = semantic * 0.75 + lexical * 0.25
            if score > 0:
                ranked.append((score, memory["content"]))
        ranked.sort(key=lambda item: item[0], reverse=True)
        context.extend(content for _, content in ranked[:limit])
        return context

    async def recall_tool(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        memories = self.recall(
            str(arguments["session_id"]),
            str(arguments["query"]),
            limit=int(arguments.get("limit", 4)),
        )
        return ToolResult(
            data={"memories": memories},
            metadata={"layers": ["short_term", "long_term"], "count": len(memories)},
        )


class PostgresMilvusMemory:
    """PostgreSQL short-term memory plus Milvus semantic long-term memory."""

    def __init__(
        self,
        postgres_dsn: str,
        milvus_uri: str,
        milvus_token: str | None = None,
        collection: str = "openresearchgraph_memory",
        embedder: HashEmbedding | None = None,
    ) -> None:
        try:
            import psycopg
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise RuntimeError(
                'PostgreSQL + Milvus memory requires: pip install -e ".[memory]"'
            ) from exc
        self._psycopg = psycopg
        self._postgres_dsn = postgres_dsn
        client_options = {"uri": milvus_uri}
        if milvus_token:
            client_options["token"] = milvus_token
        self._milvus = MilvusClient(**client_options)
        self._collection = collection
        self.embedder = embedder or HashEmbedding()
        self._short_cache: dict[str, dict[str, Any]] = {}
        self._initialize()

    def _initialize(self) -> None:
        with self._psycopg.connect(self._postgres_dsn) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS org_short_memory (
                session_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )"""
            )
        if not self._milvus.has_collection(collection_name=self._collection):
            self._milvus.create_collection(
                collection_name=self._collection,
                dimension=self.embedder.dimensions,
                metric_type="COSINE",
                id_type="string",
                max_length=64,
            )

    def remember_session(
        self, session_id: str, summary: str, preferences: dict[str, Any] | None = None
    ) -> None:
        value = {"summary": summary, "preferences": preferences or {}}
        self._short_cache[session_id] = value
        with self._psycopg.connect(self._postgres_dsn) as connection:
            connection.execute(
                """INSERT INTO org_short_memory(session_id, summary, preferences)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT(session_id) DO UPDATE SET
                summary=EXCLUDED.summary,
                preferences=EXCLUDED.preferences,
                updated_at=NOW()""",
                (session_id, summary, json.dumps(value["preferences"], ensure_ascii=False)),
            )

    def remember_knowledge(
        self, content: str, metadata: dict[str, Any] | None = None, memory_id: str | None = None
    ) -> str:
        identifier = memory_id or f"mem-{uuid4().hex[:12]}"
        self._milvus.upsert(
            collection_name=self._collection,
            data=[
                {
                    "id": identifier,
                    "vector": self.embedder.embed(content),
                    "content": content,
                    "metadata": metadata or {},
                }
            ],
        )
        return identifier

    def _short_term(self, session_id: str) -> dict[str, Any] | None:
        cached = self._short_cache.get(session_id)
        if cached:
            return cached
        with self._psycopg.connect(self._postgres_dsn) as connection:
            row = connection.execute(
                "SELECT summary, preferences FROM org_short_memory WHERE session_id=%s",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        value = {"summary": row[0], "preferences": row[1] or {}}
        self._short_cache[session_id] = value
        return value

    def recall(self, session_id: str, query: str, limit: int = 4) -> list[str]:
        context: list[str] = []
        short = self._short_term(session_id)
        if short:
            context.append(f"会话摘要：{short['summary']}")
            if short["preferences"]:
                rendered = "、".join(
                    f"{key}={value}" for key, value in sorted(short["preferences"].items())
                )
                context.append(f"表达偏好：{rendered}")
        hits = self._milvus.search(
            collection_name=self._collection,
            data=[self.embedder.embed(query)],
            limit=limit,
            output_fields=["content", "metadata"],
        )
        for hit in hits[0] if hits else []:
            entity = hit.get("entity", hit)
            content = entity.get("content")
            if content:
                context.append(str(content))
        return context

    async def recall_tool(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        memories = self.recall(
            str(arguments["session_id"]),
            str(arguments["query"]),
            limit=int(arguments.get("limit", 4)),
        )
        return ToolResult(
            data={"memories": memories},
            metadata={
                "layers": ["postgres_short_term", "milvus_long_term"],
                "count": len(memories),
            },
        )


def build_memory(
    settings: Settings, repository: Repository
) -> TwoLayerMemory | PostgresMilvusMemory:
    if settings.memory_backend == "postgres_milvus":
        if not settings.postgres_dsn or not settings.milvus_uri:
            raise ValueError(
                "ORG_POSTGRES_DSN and ORG_MILVUS_URI are required for postgres_milvus memory"
            )
        return PostgresMilvusMemory(
            postgres_dsn=settings.postgres_dsn,
            milvus_uri=settings.milvus_uri,
            milvus_token=settings.milvus_token,
            collection=settings.milvus_collection,
        )
    return TwoLayerMemory(repository)
