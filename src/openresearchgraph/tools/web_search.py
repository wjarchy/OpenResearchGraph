from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import httpx

from ..state import SourceMetadata
from .base import ToolContext, ToolResult
from .search import LocalCorpusSearchTool


class WebSearchTool:
    """Open HTTP search adapter with a deterministic local fallback."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 15.0,
        fallback: LocalCorpusSearchTool | None = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.fallback = fallback or LocalCorpusSearchTool()

    async def __call__(self, arguments: dict, context: ToolContext) -> ToolResult:
        if not self.base_url:
            result = await self.fallback(arguments, context)
            result.metadata.update({"mode": "offline-fallback", "network_used": False})
            return result
        query = str(arguments["query"]).strip()
        limit = max(1, min(int(arguments.get("limit", 5)), 10))
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                self.base_url,
                params={"q": query, "limit": limit},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        rows = payload.get("results", []) if isinstance(payload, dict) else payload
        sources: list[SourceMetadata] = []
        items: list[dict] = []
        for row in rows[:limit]:
            title = str(row.get("title") or "Untitled source")
            uri = str(row.get("url") or row.get("uri") or "")
            snippet = str(row.get("snippet") or row.get("content") or "")
            if not uri or not snippet:
                continue
            digest = hashlib.sha256(snippet.encode("utf-8")).hexdigest()
            source = SourceMetadata(
                source_id=f"web-{digest[:10]}",
                title=title,
                uri=uri,
                provider="configured-web-search",
                published_at=row.get("published_at"),
                retrieved_at=datetime.now(UTC).isoformat(),
                content_hash=digest,
                score=max(0.0, min(1.0, float(row.get("score", 0.7)))),
                attributes={"network": True},
            )
            sources.append(source)
            items.append({"excerpt": snippet, "source_id": source.source_id})
        return ToolResult(
            data=items,
            sources=sources,
            metadata={"query": query, "mode": "remote", "network_used": True},
        )
