from __future__ import annotations

from urllib.parse import urlparse

from ..state import AgentRole, Evidence, ResearchState
from ..tools import ToolContext
from .base import BaseAgent


class ScoutAgent(BaseAgent):
    role = AgentRole.SCOUT

    def __init__(self, *args, max_rounds: int = 3, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.max_rounds = max_rounds

    @staticmethod
    def _quality(evidence: list[dict]) -> tuple[float, dict[str, float]]:
        source_ids = {item["source"]["source_id"] for item in evidence}
        locations = {
            urlparse(item["source"]["uri"]).netloc or item["source"]["uri"].split("/", 3)[-1]
            for item in evidence
        }
        average_relevance = (
            sum(item["relevance"] for item in evidence) / len(evidence) if evidence else 0.0
        )
        coverage = min(1.0, len(source_ids) / 3)
        diversity = min(1.0, len(locations) / 3)
        score = coverage * 0.45 + diversity * 0.25 + average_relevance * 0.30
        return round(score, 3), {
            "coverage": round(coverage, 3),
            "diversity": round(diversity, 3),
            "relevance": round(average_relevance, 3),
        }

    @staticmethod
    def _rewrite(query: str, round_number: int) -> str:
        suffixes = ("数据 口径 来源", "产业化 约束 反例", "趋势 风险 对比")
        return f"{query} {suffixes[(round_number - 1) % len(suffixes)]}"

    async def run(self, state: ResearchState) -> ResearchState:
        evidence_by_id = {item["source"]["source_id"]: item for item in state.get("evidence", [])}
        rounds = list(state.get("search_rounds", []))
        plan = state.get("plan") or {}
        planned_queries = [
            task["question"]
            for task in plan.get("tasks", [])
            if task.get("owner") == AgentRole.SCOUT.value
        ] or [state["query"]]
        query = " ".join(planned_queries)
        context = ToolContext(
            run_id=state["run_id"],
            role=self.role,
            emit=self.emit,
        )

        for round_number in range(1, self.max_rounds + 1):
            result = await self.tools.invoke("search_corpus", {"query": query, "limit": 6}, context)
            source_lookup = {source.source_id: source for source in result.sources}
            for item in result.data:
                source = source_lookup[item["source_id"]]
                evidence = Evidence(
                    excerpt=item["excerpt"],
                    source=source,
                    query=query,
                    relevance=source.score,
                )
                evidence_by_id[source.source_id] = evidence.model_dump(mode="json")
            current = list(evidence_by_id.values())
            score, dimensions = self._quality(current)
            decision = "accept" if score >= 0.60 else "rewrite"
            rounds.append(
                {
                    "round": round_number,
                    "query": query,
                    "action": "search_corpus",
                    "observation": {"unique_sources": len(current)},
                    "quality": score,
                    "dimensions": dimensions,
                    "decision": decision,
                }
            )
            if decision == "accept":
                break
            if self.provider.is_remote:
                rewritten = await self.provider.complete(
                    "Rewrite the search query only. Return no explanation.",
                    f"Original query: {state['query']}\nQuality dimensions: {dimensions}",
                )
                query = rewritten.strip().strip("`")[:300] or self._rewrite(
                    state["query"], round_number
                )
            else:
                query = self._rewrite(state["query"], round_number)

        state["evidence"] = list(evidence_by_id.values())
        state["search_rounds"] = rounds
        return self.completed(state)
