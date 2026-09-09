from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from langgraph.graph import END, START, StateGraph

from .agents import (
    AtlasAgent,
    BeaconAgent,
    ForgeAgent,
    PrismAgent,
    ScribeAgent,
    SentinelAgent,
)
from .providers import LanguageProvider
from .state import AgentRole, ResearchState, RunStatus
from .storage import Repository
from .tools import ToolFactory

GraphEventCallback = Callable[[str, AgentRole | None, str, dict[str, Any]], Awaitable[None]]


class ResearchGraph:
    """LangGraph workflow with role checkpoints and checkpoint-aware resume routing."""

    ORDER = (
        AgentRole.ATLAS,
        AgentRole.BEACON,
        AgentRole.PRISM,
        AgentRole.SENTINEL,
        AgentRole.FORGE,
        AgentRole.SCRIBE,
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
            AgentRole.ATLAS: AtlasAgent(provider, tools),
            AgentRole.BEACON: BeaconAgent(provider, tools, max_rounds=max_search_rounds),
            AgentRole.PRISM: PrismAgent(provider, tools),
            AgentRole.SENTINEL: SentinelAgent(provider, tools),
            AgentRole.FORGE: ForgeAgent(provider, tools),
            AgentRole.SCRIBE: ScribeAgent(provider, tools),
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
                AgentRole.ATLAS.value: AgentRole.ATLAS.value,
                AgentRole.BEACON.value: AgentRole.BEACON.value,
                AgentRole.PRISM.value: AgentRole.PRISM.value,
                AgentRole.SENTINEL.value: AgentRole.SENTINEL.value,
                AgentRole.FORGE.value: AgentRole.FORGE.value,
                AgentRole.SCRIBE.value: AgentRole.SCRIBE.value,
                "done": END,
            },
        )
        builder.add_edge(AgentRole.ATLAS.value, AgentRole.BEACON.value)
        builder.add_edge(AgentRole.BEACON.value, AgentRole.PRISM.value)
        builder.add_edge(AgentRole.PRISM.value, AgentRole.SENTINEL.value)
        builder.add_conditional_edges(
            AgentRole.SENTINEL.value,
            self._after_sentinel,
            {
                AgentRole.FORGE.value: AgentRole.FORGE.value,
                AgentRole.SCRIBE.value: AgentRole.SCRIBE.value,
            },
        )
        builder.add_edge(AgentRole.FORGE.value, AgentRole.SCRIBE.value)
        builder.add_edge(AgentRole.SCRIBE.value, END)
        return builder.compile()

    @staticmethod
    def _after_sentinel(state: ResearchState) -> str:
        critique = state.get("critique") or {}
        return AgentRole.SCRIBE.value if critique.get("passed") else AgentRole.FORGE.value

    @classmethod
    def _resume_route(cls, state: ResearchState) -> str:
        completed = set(state.get("completed_nodes", []))
        if AgentRole.ATLAS.value not in completed:
            return AgentRole.ATLAS.value
        if AgentRole.BEACON.value not in completed:
            return AgentRole.BEACON.value
        if AgentRole.PRISM.value not in completed:
            return AgentRole.PRISM.value
        if AgentRole.SENTINEL.value not in completed:
            return AgentRole.SENTINEL.value
        critique = state.get("critique") or {}
        if not critique.get("passed") and AgentRole.FORGE.value not in completed:
            return AgentRole.FORGE.value
        if AgentRole.SCRIBE.value not in completed:
            return AgentRole.SCRIBE.value
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
