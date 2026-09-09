from __future__ import annotations

import hashlib
from pathlib import Path

from ..state import SourceMetadata
from .base import ToolContext, ToolResult
from .search import _tokens


class LocalKnowledgeSearchTool:
    """Search user-provided UTF-8 files without sending their contents over the network."""

    ALLOWED_SUFFIXES = {".csv", ".json", ".md", ".txt"}

    def __init__(self, root: Path, max_file_bytes: int = 1_000_000) -> None:
        self.root = root.resolve()
        self.max_file_bytes = max_file_bytes

    async def __call__(self, arguments: dict, context: ToolContext) -> ToolResult:
        query = str(arguments["query"]).strip()
        limit = max(1, min(int(arguments.get("limit", 5)), 10))
        query_tokens = _tokens(query)
        ranked: list[tuple[float, Path, str]] = []
        if self.root.exists():
            for path in self.root.rglob("*"):
                resolved = path.resolve()
                if (
                    not path.is_file()
                    or not resolved.is_relative_to(self.root)
                    or path.suffix.lower() not in self.ALLOWED_SUFFIXES
                    or path.stat().st_size > self.max_file_bytes
                ):
                    continue
                content = resolved.read_text(encoding="utf-8", errors="replace")
                document_tokens = _tokens(f"{path.name} {content}")
                overlap = len(query_tokens & document_tokens)
                if overlap:
                    ranked.append((overlap / (len(query_tokens) or 1), resolved, content))
        ranked.sort(key=lambda item: item[0], reverse=True)
        sources: list[SourceMetadata] = []
        items: list[dict] = []
        for score, path, content in ranked[:limit]:
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            relative = path.relative_to(self.root).as_posix()
            source = SourceMetadata(
                source_id=f"kb-{digest[:10]}",
                title=path.stem,
                uri=f"knowledge://{relative}",
                provider="local-knowledge-base",
                content_hash=digest,
                score=min(1.0, score),
                attributes={"local": True, "extension": path.suffix.lower()},
            )
            sources.append(source)
            items.append({"excerpt": content[:1_200], "source_id": source.source_id})
        return ToolResult(
            data=items,
            sources=sources,
            metadata={"query": query, "root": str(self.root), "local_only": True},
        )
