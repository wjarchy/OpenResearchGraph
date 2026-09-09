from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

from .config import Settings
from .graph import ResearchGraph
from .memory import build_memory
from .providers import build_provider
from .state import AgentRole, ResearchEvent, ResearchState, RunStatus, new_research_state
from .storage import Repository
from .tools import (
    LocalCorpusSearchTool,
    LocalKnowledgeSearchTool,
    PythonSandboxTool,
    SafeSQLExecutor,
    ToolFactory,
    WebSearchTool,
)

TERMINAL_EVENTS = {"run.completed", "run.failed"}


class ResearchRuntime:
    """Owns the background queue and persists all events before broadcasting them."""

    def __init__(self, settings: Settings, worker_count: int = 2) -> None:
        self.settings = settings
        self.repository = Repository(settings.database_path)
        self.memory = build_memory(settings, self.repository)
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.worker_count = worker_count
        self._workers: list[asyncio.Task] = []
        self._conditions: dict[str, asyncio.Condition] = {}

        tools = ToolFactory()
        corpus_search = LocalCorpusSearchTool()
        web_search = WebSearchTool(
            base_url=settings.web_search_base_url,
            api_key=settings.web_search_api_key,
            fallback=corpus_search,
        )
        safe_sql = SafeSQLExecutor(
            database_path=settings.database_path,
            allowed_tables={"industry_metrics", "industry_observations"},
            max_rows=settings.max_sql_rows,
            timeout_seconds=settings.sql_timeout_seconds,
        )
        tools.register(
            "web_search",
            "Search the web through an environment-configured adapter or offline fallback",
            web_search,
            {"query"},
        )
        tools.register(
            "search_knowledge_base",
            "Search local user-provided UTF-8 knowledge files",
            LocalKnowledgeSearchTool(settings.knowledge_path),
            {"query"},
        )
        tools.register(
            "query_industry_data",
            "Execute a bounded read-only query against whitelisted industry data",
            safe_sql,
            {"sql"},
        )
        tools.register(
            "recall_memory",
            "Fuse short-term session context with long-term semantic knowledge",
            self.memory.recall_tool,
            {"session_id", "query"},
        )
        tools.register(
            "run_python_analysis",
            "Validate and execute bounded pure-Python analysis and return a chart specification",
            PythonSandboxTool(settings.python_timeout_seconds),
            {"code", "data"},
        )
        self.tools = tools
        self.graph = ResearchGraph(
            provider=build_provider(settings),
            tools=tools,
            repository=self.repository,
            emit=self._graph_event,
            max_search_rounds=settings.max_search_rounds,
        )

    async def start(self) -> None:
        if not self._workers:
            self._workers = [
                asyncio.create_task(self._worker(index), name=f"research-worker-{index}")
                for index in range(self.worker_count)
            ]

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        self._workers.clear()

    async def submit(self, query: str, session_id: str = "default") -> ResearchState:
        state = new_research_state(query=query, session_id=session_id)
        self.repository.create_run(state)
        await self.emit(
            ResearchEvent(
                run_id=state["run_id"],
                kind="run.queued",
                message="研究任务已进入队列",
                data={"queue_size": self.queue.qsize() + 1},
            )
        )
        await self.queue.put(state["run_id"])
        return state

    async def resume(self, run_id: str) -> ResearchState:
        state = self.repository.latest_checkpoint(run_id)
        if not state:
            raise KeyError(run_id)
        if state.get("status") != RunStatus.FAILED:
            raise ValueError("Only failed runs can be resumed")
        state["status"] = RunStatus.QUEUED
        state["error"] = None
        self.repository.update_run(state)
        await self.emit(
            ResearchEvent(
                run_id=run_id,
                kind="run.queued",
                message="任务将从最近的节点 checkpoint 继续",
                data={"completed_nodes": state.get("completed_nodes", [])},
            )
        )
        await self.queue.put(run_id)
        return state

    async def _worker(self, worker_index: int) -> None:
        while True:
            run_id = await self.queue.get()
            try:
                await self._execute(run_id, worker_index)
            finally:
                self.queue.task_done()

    async def _execute(self, run_id: str, worker_index: int) -> None:
        state = self.repository.latest_checkpoint(run_id)
        if not state:
            return
        state["status"] = RunStatus.RUNNING
        self.repository.update_run(state)
        await self.emit(
            ResearchEvent(
                run_id=run_id,
                kind="run.started",
                message="研究工作流开始执行",
                data={"worker": worker_index},
            )
        )
        try:
            result = await self.graph.run(state)
            result["status"] = RunStatus.COMPLETED
            result["error"] = None
            self.repository.update_run(result)
            summary = result.get("report", "").replace("\n", " ")[:360]
            self.memory.remember_session(
                result.get("session_id", "default"),
                summary=summary,
                preferences={"citation_style": "source_id", "language": "zh-CN"},
            )
            if summary:
                self.memory.remember_knowledge(
                    summary,
                    metadata={"run_id": run_id, "kind": "research_summary"},
                    memory_id=f"run-{run_id}",
                )
            await self.emit(
                ResearchEvent(
                    run_id=run_id,
                    kind="run.completed",
                    message="研究任务已完成",
                    data={"report": result.get("report", "")},
                )
            )
        except Exception as exc:
            failed = self.repository.latest_checkpoint(run_id) or state
            error = f"{type(exc).__name__}: {exc}"
            self.repository.mark_failed(failed, error)
            await self.emit(
                ResearchEvent(
                    run_id=run_id,
                    kind="run.failed",
                    message="研究任务执行失败，可从最近 checkpoint 继续",
                    data={"error": error},
                )
            )

    async def _graph_event(
        self,
        kind: str,
        role: AgentRole | None,
        message: str,
        data: dict[str, Any],
    ) -> None:
        run_id = str(data.get("run_id", ""))
        if not run_id:
            raise RuntimeError("Graph event is missing run_id")
        await self.emit(
            ResearchEvent(run_id=run_id, kind=kind, role=role, message=message, data=data)
        )

    async def emit(self, event: ResearchEvent) -> ResearchEvent:
        persisted = self.repository.append_event(event)
        condition = self._conditions.setdefault(event.run_id, asyncio.Condition())
        async with condition:
            condition.notify_all()
        return persisted

    async def events(self, run_id: str, after: int = 0) -> AsyncIterator[ResearchEvent]:
        if not self.repository.get_run(run_id):
            raise KeyError(run_id)
        cursor = after
        condition = self._conditions.setdefault(run_id, asyncio.Condition())
        while True:
            batch = self.repository.events_after(run_id, cursor)
            if batch:
                for event in batch:
                    cursor = event.sequence
                    yield event
                current = self.repository.get_run(run_id)
                if (
                    batch[-1].kind in TERMINAL_EVENTS
                    and current
                    and current.get("status") in {RunStatus.COMPLETED, RunStatus.FAILED}
                ):
                    return
                continue
            state = self.repository.get_run(run_id)
            if state and state.get("status") in {RunStatus.COMPLETED, RunStatus.FAILED}:
                return
            async with condition:
                try:
                    await asyncio.wait_for(condition.wait(), timeout=5)
                except TimeoutError:
                    continue
