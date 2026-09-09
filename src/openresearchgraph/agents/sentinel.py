from __future__ import annotations

from ..state import AgentRole, Critique, ResearchState
from .base import BaseAgent


class SentinelAgent(BaseAgent):
    role = AgentRole.SENTINEL

    async def run(self, state: ResearchState) -> ResearchState:
        evidence = state.get("evidence", [])
        analyses = state.get("analyses", [])
        plan_tasks = (state.get("plan") or {}).get("tasks", [])
        source_count = len({item["source"]["source_id"] for item in evidence})
        coverage = min(1.0, source_count / max(2, len(plan_tasks) - 1))
        analysis_score = 1.0 if analyses and analyses[0].get("sql") else 0.0
        provenance_score = (
            1.0
            if evidence and all(item.get("source", {}).get("content_hash") for item in evidence)
            else 0.0
        )
        score = round(coverage * 0.45 + analysis_score * 0.30 + provenance_score * 0.25, 3)
        findings: list[str] = []
        missing: list[str] = []
        if coverage < 0.75:
            findings.append("证据覆盖不足，需要补充不同角度的来源。")
            missing.append("补充约束条件或反例来源")
        if not analyses:
            findings.append("缺少可复算的数据分析。")
            missing.append("增加带口径说明的数据查询")
        if evidence and all(item["source"]["attributes"].get("synthetic") for item in evidence):
            findings.append("当前全部来源为合成演示语料，报告必须显著披露该限制。")
        critique = Critique(
            passed=score >= 0.68,
            score=score,
            findings=findings or ["证据链、分析产物与来源元数据结构完整。"],
            missing_questions=missing,
        )
        state["critique"] = critique.model_dump(mode="json")
        return self.completed(state)
