from __future__ import annotations

from abc import ABC, abstractmethod

from ..providers import LanguageProvider
from ..state import AgentRole, ResearchState, utc_now
from ..tools import ToolFactory
from ..tools.base import EventCallback


class BaseAgent(ABC):
    role: AgentRole

    def __init__(
        self,
        provider: LanguageProvider,
        tools: ToolFactory,
        emit: EventCallback | None = None,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.emit = emit

    @abstractmethod
    async def run(self, state: ResearchState) -> ResearchState:
        pass

    def completed(self, state: ResearchState) -> ResearchState:
        completed_nodes = list(state.get("completed_nodes", []))
        if self.role.value not in completed_nodes:
            completed_nodes.append(self.role.value)
        state["completed_nodes"] = completed_nodes
        state["updated_at"] = utc_now()
        return state
