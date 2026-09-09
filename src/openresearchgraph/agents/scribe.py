from __future__ import annotations

from ..state import AgentRole, ResearchState
from .base import BaseAgent


class ScribeAgent(BaseAgent):
    role = AgentRole.SCRIBE

    async def run(self, state: ResearchState) -> ResearchState:
        evidence = state.get("evidence", [])
        analyses = state.get("analyses", [])
        critique = state.get("critique") or {}
        source_labels = {
            item["source"]["source_id"]: f"S{index + 1}" for index, item in enumerate(evidence)
        }
        evidence_lines = [
            f"- {item['excerpt']} [{source_labels[item['source']['source_id']]}]"
            for item in evidence
        ] or ["- 尚无足够证据。"]
        analysis_lines: list[str] = []
        for analysis in analyses:
            stats = "、".join(f"{key}={value}" for key, value in analysis["statistics"].items())
            analysis_lines.append(f"- {analysis['summary']} 计算结果：{stats or '无'}。")
        source_lines = [
            (
                f"- [{label}] {item['source']['title']} — {item['source']['uri']} "
                f"(sha256: `{item['source']['content_hash'][:12]}…`)"
            )
            for item in evidence
            for label in [source_labels[item["source"]["source_id"]]]
        ]
        findings = "；".join(critique.get("findings", [])) or "未记录"
        deterministic_report = "\n".join(
            [
                f"# 研究报告：{state['query']}",
                "",
                "## 结论摘要",
                "",
                "当前结果展示了可追踪研究流程。关键判断仍需接入真实来源后由研究者复核。",
                "",
                "## 证据观察",
                "",
                *evidence_lines,
                "",
                "## 数据分析",
                "",
                *(analysis_lines or ["- 当前问题未形成可复算分析。"]),
                "",
                "## 质量审查",
                "",
                f"- Sentinel 得分：{critique.get('score', 0):.2f}",
                f"- 审查意见：{findings}",
                "",
                "## 限制",
                "",
                "- 当前内置来源和指标均为合成演示数据，不代表任何企业或真实市场。",
                "- 结论是研究起点，不是投资、法律或其他专业建议。",
                "",
                "## 来源",
                "",
                *(source_lines or ["- 无"]),
            ]
        )
        if self.provider.is_remote:
            synthesized = await self.provider.complete(
                (
                    "Write a concise Chinese research brief using only the supplied material. "
                    "Cite claims with [S1] style labels and state uncertainty."
                ),
                deterministic_report,
            )
            state["report"] = "\n".join(
                [synthesized.strip(), "", "## 可追溯来源", "", *source_lines]
            )
        else:
            state["report"] = deterministic_report
        return self.completed(state)
