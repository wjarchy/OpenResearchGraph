from __future__ import annotations

from ..state import AgentRole, RepairAction, ResearchState
from ..tools import ToolContext
from .base import BaseAgent


class WizardAgent(BaseAgent):
    role = AgentRole.WIZARD

    async def run(self, state: ResearchState) -> ResearchState:
        critique = state.get("critique") or {}
        repairs = list(state.get("repairs", []))
        if not critique.get("passed"):
            context = ToolContext(
                run_id=state["run_id"],
                role=self.role,
                emit=self.emit,
            )
            result = await self.tools.invoke(
                "search_corpus",
                {"query": f"{state['query']} 研究证据质量 反例 口径", "limit": 6},
                context,
            )
            existing = {item["source"]["source_id"] for item in state.get("evidence", [])}
            source_lookup = {source.source_id: source for source in result.sources}
            added = 0
            for item in result.data:
                if item["source_id"] in existing:
                    continue
                source = source_lookup[item["source_id"]]
                state.setdefault("evidence", []).append(
                    {
                        "evidence_id": f"repair-{item['source_id']}",
                        "excerpt": item["excerpt"],
                        "source": source.model_dump(mode="json"),
                        "query": result.metadata["query"],
                        "relevance": source.score,
                    }
                )
                added += 1
            repairs.append(
                RepairAction(
                    reason="；".join(critique.get("findings", [])),
                    action="执行补充检索并强制保留数据边界说明",
                    outcome=f"新增 {added} 条去重证据；报告将披露合成数据限制",
                ).model_dump(mode="json")
            )
        state["repairs"] = repairs
        return self.completed(state)
