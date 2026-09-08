from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from langgraph.graph import END, START, StateGraph

from .agents import (
    ArchitectAgent,
    CriticAgent,
    DataAnalystAgent,
    ScoutAgent,
    WizardAgent,
    WriterAgent,
)
from .providers import LanguageProvider
from .state import AgentRole, ResearchState, RunStatus
from .storage import Repository
from .tools import ToolFactory

GraphEventCallback = Callable[[str, AgentRole | None, str, dict[str, Any]], Awaitable[None]]


class ResearchGraph:
    """LangGraph workflow with role checkpoints and checkpoint-aware resume routing."""

    ORDER = (
        AgentRole.ARCHITECT,
        AgentRole.SCOUT,
        AgentRole.DATA_ANALYST,
        AgentRole.CRITIC,
        AgentRole.WIZARD,
        AgentRole.WRITER,
    )

    def __init__(
        self,
        provider: LanguageProvider,
        tools: ToolFactory,
        repository: Repository,
        emit: GraphEventCallback,
        max_search_rounds: int = 3,
    ) -> None:
        self.repository = repository
        self.emit = emit
        self.agents = {
            AgentRole.ARCHITECT: ArchitectAgent(provider, tools),
            AgentRole.SCOUT: ScoutAgent(provider, tools, max_rounds=max_search_rounds),
            AgentRole.DATA_ANALYST: DataAnalystAgent(provider, tools),
            AgentRole.CRITIC: CriticAgent(provider, tools),
            AgentRole.WIZARD: WizardAgent(provider, tools),
            AgentRole.WRITER: WriterAgent(provider, tools),
        }
        for agent in self.agents.values():
            agent.tools = tools
            agent.provider = provider
            agent_emit = self.emit
            agent.__dict__["emit"] = agent_emit
        self.compiled = self._build()

    def _build(self):
        builder = StateGraph(ResearchState)
        for role in self.ORDER:
            builder.add_node(role.value, self._node(role))
        builder.add_conditional_edges(
            START,
            self._resume_route,
            {
                AgentRole.ARCHITECT.value: AgentRole.ARCHITECT.value,
                AgentRole.SCOUT.value: AgentRole.SCOUT.value,
                AgentRole.DATA_ANALYST.value: AgentRole.DATA_ANALYST.value,
                AgentRole.CRITIC.value: AgentRole.CRITIC.value,
                AgentRole.WIZARD.value: AgentRole.WIZARD.value,
                AgentRole.WRITER.value: AgentRole.WRITER.value,
                "done": END,
            },
        )
        builder.add_edge(AgentRole.ARCHITECT.value, AgentRole.SCOUT.value)
        builder.add_edge(AgentRole.SCOUT.value, AgentRole.DATA_ANALYST.value)
        builder.add_edge(AgentRole.DATA_ANALYST.value, AgentRole.CRITIC.value)
        builder.add_conditional_edges(
            AgentRole.CRITIC.value,
            self._after_critic,
            {
                AgentRole.WIZARD.value: AgentRole.WIZARD.value,
                AgentRole.WRITER.value: AgentRole.WRITER.value,
            },
        )
        builder.add_edge(AgentRole.WIZARD.value, AgentRole.WRITER.value)
        builder.add_edge(AgentRole.WRITER.value, END)
        return builder.compile()

    @staticmethod
    def _after_critic(state: ResearchState) -> str:
        critique = state.get("critique") or {}
        return AgentRole.WRITER.value if critique.get("passed") else AgentRole.WIZARD.value

    @classmethod
    def _resume_route(cls, state: ResearchState) -> str:
        completed = set(state.get("completed_nodes", []))
        if AgentRole.ARCHITECT.value not in completed:
            return AgentRole.ARCHITECT.value
        if AgentRole.SCOUT.value not in completed:
            return AgentRole.SCOUT.value
        if AgentRole.DATA_ANALYST.value not in completed:
            return AgentRole.DATA_ANALYST.value
        if AgentRole.CRITIC.value not in completed:
            return AgentRole.CRITIC.value
        critique = state.get("critique") or {}
        if not critique.get("passed") and AgentRole.WIZARD.value not in completed:
            return AgentRole.WIZARD.value
        if AgentRole.WRITER.value not in completed:
            return AgentRole.WRITER.value
        return "done"

    def _node(self, role: AgentRole):
        async def execute(state: ResearchState) -> ResearchState:
            await self.emit(
                "agent.started",
                role,
                f"{role.value} 开始执行",
                {"run_id": state["run_id"]},
            )
            updated = await self.agents[role].run(deepcopy(state))
            updated["status"] = RunStatus.RUNNING
            checkpoint_id = self.repository.save_checkpoint(updated, role.value)
            await self.emit(
                "checkpoint.saved",
                role,
                f"已保存 {role.value} checkpoint",
                {"checkpoint_id": checkpoint_id, "run_id": state["run_id"]},
            )
            await self.emit(
                "agent.completed",
                role,
                f"{role.value} 执行完成",
                {
                    "completed_nodes": updated.get("completed_nodes", []),
                    "run_id": state["run_id"],
                },
            )
            return updated

        return execute

    async def run(self, state: ResearchState) -> ResearchState:
        return await self.compiled.ainvoke(state)
