from __future__ import annotations

import hashlib
import math
import re
from typing import Any
from uuid import uuid4

from .storage import Repository
from .tools.base import ToolContext, ToolResult


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
