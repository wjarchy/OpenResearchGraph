from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..analytics import AnalyticsPlan, DimensionQueryPlanner
from ..config import Settings, get_settings
from ..runtime import ResearchRuntime
from ..state import AgentRole
from ..tools import ToolContext


class ResearchRequest(BaseModel):
    query: str = Field(min_length=4, max_length=8_000)
    session_id: str = Field(default="default", pattern=r"^[a-zA-Z0-9_-]{1,80}$")


class AnalyticsRequest(BaseModel):
    dimensions: list[Literal["sector", "region", "year", "month"]] = Field(
        min_length=1, max_length=4
    )
    period_mode: Literal["current", "cumulative"] = "current"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    runtime = ResearchRuntime(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime
        await runtime.start()
        yield
        await runtime.stop()

    app = FastAPI(
        title="OpenResearchGraph API",
        version="0.1.0",
        description="Traceable six-agent research workflow",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "provider": "remote" if config.use_remote_llm else "deterministic-demo",
            "queue_size": runtime.queue.qsize(),
        }

    @app.get("/api/research")
    async def list_runs(limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:
        return runtime.repository.list_runs(limit)

    @app.post("/api/data/query")
    async def query_dimensions(payload: AnalyticsRequest) -> dict:
        dimensions = tuple(dict.fromkeys(payload.dimensions))
        plan = AnalyticsPlan(dimensions=dimensions, period_mode=payload.period_mode)
        sql = DimensionQueryPlanner().build_sql(plan)
        result = await runtime.tools.invoke(
            "query_industry_data",
            {"sql": sql},
            ToolContext(run_id="interactive-data-query", role=AgentRole.PRISM),
        )
        return {
            "dimensions": list(dimensions),
            "period_mode": payload.period_mode,
            **result.data,
        }

    @app.post("/api/research", status_code=202)
    async def create_research(payload: ResearchRequest) -> dict:
        state = await runtime.submit(payload.query, payload.session_id)
        return {"run_id": state["run_id"], "status": state["status"]}

    @app.post("/api/research/stream")
    async def create_research_stream(payload: ResearchRequest) -> StreamingResponse:
        state = await runtime.submit(payload.query, payload.session_id)

        async def generate():
            yield _sse("run.accepted", {"run_id": state["run_id"]})
            async for event in runtime.events(state["run_id"]):
                yield _sse(event.kind, event.model_dump(mode="json"))

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/research/{run_id}")
    async def get_research(run_id: str) -> dict:
        state = runtime.repository.get_run(run_id)
        if not state:
            raise HTTPException(status_code=404, detail="Research run not found")
        return state

    @app.get("/api/research/{run_id}/events")
    async def stream_events(
        run_id: str, request: Request, after: int = Query(default=0, ge=0)
    ) -> StreamingResponse:
        if not runtime.repository.get_run(run_id):
            raise HTTPException(status_code=404, detail="Research run not found")

        async def generate():
            async for event in runtime.events(run_id, after):
                if await request.is_disconnected():
                    return
                yield _sse(event.kind, event.model_dump(mode="json"))

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/research/{run_id}/resume", status_code=202)
    async def resume_research(run_id: str) -> dict:
        try:
            state = await runtime.resume(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Research run not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"run_id": run_id, "status": state["status"]}

    web_dir = Path.cwd() / "web"
    if not web_dir.exists():
        web_dir = Path(__file__).resolve().parents[3] / "web"
    if web_dir.exists():
        app.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(web_dir / "index.html")

    return app
