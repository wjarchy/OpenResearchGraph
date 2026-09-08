from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from ..state import AgentRole, SourceMetadata


class ToolResult(BaseModel):
    data: Any
    sources: list[SourceMetadata] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


EventCallback = Callable[[str, AgentRole | None, str, dict[str, Any]], Awaitable[None]]
ToolHandler = Callable[[dict[str, Any], "ToolContext"], Awaitable[ToolResult]]


@dataclass(slots=True)
class ToolContext:
    run_id: str
    role: AgentRole
    emit: EventCallback | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    name: str
    description: str
    handler: ToolHandler
    required_arguments: frozenset[str]


class ToolFactory:
    """Central registry enforcing tool naming, input shape, and provenance output."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        handler: ToolHandler,
        required_arguments: set[str] | None = None,
    ) -> None:
        normalized = name.strip().lower()
        if not normalized or " " in normalized:
            raise ValueError("Tool names must be non-empty snake_case identifiers")
        if normalized in self._tools:
            raise ValueError(f"Tool already registered: {normalized}")
        self._tools[normalized] = RegisteredTool(
            name=normalized,
            description=description.strip(),
            handler=handler,
            required_arguments=frozenset(required_arguments or set()),
        )

    def names(self) -> list[str]:
        return sorted(self._tools)

    async def invoke(
        self, name: str, arguments: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        normalized = name.strip().lower()
        tool = self._tools.get(normalized)
        if tool is None:
            raise KeyError(f"Unknown tool: {normalized}")
        missing = tool.required_arguments.difference(arguments)
        if missing:
            raise ValueError(f"Missing tool arguments: {', '.join(sorted(missing))}")
        if context.emit:
            await context.emit(
                "tool.started",
                context.role,
                f"调用工具 {normalized}",
                {"tool": normalized, "run_id": context.run_id},
            )
        result = await tool.handler(arguments, context)
        if not isinstance(result, ToolResult):
            raise TypeError(f"Tool {normalized} must return ToolResult")
        if context.emit:
            await context.emit(
                "tool.completed",
                context.role,
                f"工具 {normalized} 返回 {len(result.sources)} 个来源",
                {
                    "tool": normalized,
                    "source_count": len(result.sources),
                    "run_id": context.run_id,
                },
            )
        return result
