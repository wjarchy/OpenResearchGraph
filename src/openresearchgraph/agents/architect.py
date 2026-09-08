from __future__ import annotations

import re

from ..state import AgentRole, PlanTask, ResearchPlan, ResearchState
from ..tools import ToolContext
from .base import BaseAgent


class ArchitectAgent(BaseAgent):
    role = AgentRole.ARCHITECT

    async def run(self, state: ResearchState) -> ResearchState:
        query = state["query"].strip()
        if not state.get("memory_context") and "recall_memory" in self.tools.names():
            memory_result = await self.tools.invoke(
                "recall_memory",
                {"session_id": state.get("session_id", "default"), "query": query},
                ToolContext(run_id=state["run_id"], role=self.role, emit=self.emit),
            )
            state["memory_context"] = memory_result.data["memories"]
        parts = [item.strip() for item in re.split(r"[，,；;、]|以及|并且", query) if item.strip()]
        questions = parts[:3] or [query]
        tasks = [
            PlanTask(
                task_id=f"search-{index + 1}",
                question=question,
                owner=AgentRole.SCOUT,
                success_criteria=["至少一个可定位来源", "区分事实与推断"],
            )
            for index, question in enumerate(questions)
        ]
        tasks.append(
            PlanTask(
                task_id="analysis-1",
                question=f"为“{query}”寻找可验证的数据口径并计算趋势",
                owner=AgentRole.DATA_ANALYST,
                success_criteria=["SQL 只读", "说明单位和数据边界"],
            )
        )
        plan = ResearchPlan(
            objective=query,
            tasks=tasks,
            assumptions=[
                "默认优先使用可追溯来源",
                "演示语料和演示数据不代表真实市场事实",
            ],
        )
        state["plan"] = plan.model_dump(mode="json")
        return self.completed(state)
