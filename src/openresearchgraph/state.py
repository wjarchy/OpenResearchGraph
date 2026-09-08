from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, TypedDict
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    ARCHITECT = "architect"
    SCOUT = "scout"
    DATA_ANALYST = "data_analyst"
    CRITIC = "critic"
    WIZARD = "wizard"
    WRITER = "writer"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceMetadata(BaseModel):
    source_id: str
    title: str
    uri: str
    provider: str
    published_at: str | None = None
    retrieved_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    content_hash: str
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    attributes: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"ev-{uuid4().hex[:10]}")
    excerpt: str
    source: SourceMetadata
    query: str
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)


class PlanTask(BaseModel):
    task_id: str
    question: str
    owner: AgentRole
    success_criteria: list[str] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    objective: str
    tasks: list[PlanTask]
    assumptions: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    title: str
    summary: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    statistics: dict[str, float] = Field(default_factory=dict)
    dimensions: list[str] = Field(default_factory=list)
    drilldown_path: list[str] = Field(default_factory=list)
    display_formats: dict[str, str] = Field(default_factory=dict)
    chart_spec: dict[str, Any] | None = None
    sources: list[str] = Field(default_factory=list)


class Critique(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    findings: list[str] = Field(default_factory=list)
    missing_questions: list[str] = Field(default_factory=list)


class RepairAction(BaseModel):
    reason: str
    action: str
    outcome: str


class ResearchState(TypedDict, total=False):
    """Single JSON-compatible state contract shared by every graph node."""

    run_id: str
    session_id: str
    query: str
    status: str
    created_at: str
    updated_at: str
    plan: dict[str, Any] | None
    evidence: list[dict[str, Any]]
    analyses: list[dict[str, Any]]
    critique: dict[str, Any] | None
    repairs: list[dict[str, Any]]
    report: str
    memory_context: list[str]
    search_rounds: list[dict[str, Any]]
    completed_nodes: list[str]
    error: str | None


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_research_state(
    query: str, run_id: str | None = None, session_id: str = "default"
) -> ResearchState:
    now = utc_now()
    return ResearchState(
        run_id=run_id or uuid4().hex,
        session_id=session_id,
        query=query.strip(),
        status=RunStatus.QUEUED,
        created_at=now,
        updated_at=now,
        plan=None,
        evidence=[],
        analyses=[],
        critique=None,
        repairs=[],
        report="",
        memory_context=[],
        search_rounds=[],
        completed_nodes=[],
        error=None,
    )


class ResearchEvent(BaseModel):
    sequence: int = 0
    run_id: str
    kind: Literal[
        "run.queued",
        "run.started",
        "agent.started",
        "agent.completed",
        "tool.started",
        "tool.completed",
        "checkpoint.saved",
        "run.completed",
        "run.failed",
    ]
    role: AgentRole | None = None
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
