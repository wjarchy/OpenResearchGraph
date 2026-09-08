from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ..state import SourceMetadata
from .base import ToolContext, ToolResult


@dataclass(frozen=True, slots=True)
class CorpusDocument:
    title: str
    uri: str
    published_at: str
    body: str


DEFAULT_CORPUS = (
    CorpusDocument(
        title="储能路线示例数据说明",
        uri="local://demo/storage-route-overview",
        published_at="2026-01-15",
        body=(
            "合成示例语料：电化学储能建设周期较短、响应速度快，适合高频调节；"
            "其产业化约束通常包括电芯安全、循环寿命、供应链与回收体系。"
        ),
    ),
    CorpusDocument(
        title="长时储能产业化条件",
        uri="local://demo/long-duration-storage",
        published_at="2026-02-03",
        body=(
            "合成示例语料：长时储能更依赖项目选址、热管理、工程集成与稳定的容量补偿机制。"
            "评价路线时应同时比较度电成本、持续时长、效率、寿命与部署周期。"
        ),
    ),
    CorpusDocument(
        title="研究证据质量清单",
        uri="local://method/evidence-quality",
        published_at="2026-01-01",
        body=(
            "高质量产业研究应区分事实、推断和假设，至少进行来源多样性、时间一致性、"
            "口径一致性和反例检查，并为关键结论提供可定位引用。"
        ),
    ),
    CorpusDocument(
        title="产业指标口径示例",
        uri="local://demo/metric-definitions",
        published_at="2026-02-20",
        body=(
            "合成示例数据中的 installed_capacity 单位为 GWh，用于演示同比增速、"
            "路线对比、Text-to-SQL 和图表生成，不代表任何真实市场规模。"
        ),
    ),
)


def _tokens(text: str) -> set[str]:
    latin = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    chinese = [char for char in text if "\u4e00" <= char <= "\u9fff"]
    return set(latin + chinese)


class LocalCorpusSearchTool:
    def __init__(self, corpus: tuple[CorpusDocument, ...] = DEFAULT_CORPUS) -> None:
        self._corpus = corpus

    async def __call__(self, arguments: dict, context: ToolContext) -> ToolResult:
        query = str(arguments["query"]).strip()
        limit = max(1, min(int(arguments.get("limit", 5)), 10))
        query_tokens = _tokens(query)
        ranked: list[tuple[float, CorpusDocument]] = []
        for document in self._corpus:
            document_tokens = _tokens(f"{document.title} {document.body}")
            overlap = len(query_tokens & document_tokens)
            union = len(query_tokens | document_tokens) or 1
            score = overlap / union
            if score > 0:
                ranked.append((score, document))
        ranked.sort(key=lambda item: item[0], reverse=True)
        sources: list[SourceMetadata] = []
        items: list[dict] = []
        for score, document in ranked[:limit]:
            digest = hashlib.sha256(document.body.encode("utf-8")).hexdigest()
            source = SourceMetadata(
                source_id=f"src-{digest[:10]}",
                title=document.title,
                uri=document.uri,
                provider="local-demo-corpus",
                published_at=document.published_at,
                content_hash=digest,
                score=min(1.0, score * 4),
                attributes={"synthetic": True},
            )
            sources.append(source)
            items.append({"excerpt": document.body, "source_id": source.source_id})
        return ToolResult(data=items, sources=sources, metadata={"query": query})
