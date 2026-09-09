from __future__ import annotations

from openresearchgraph.runtime import ResearchRuntime
from openresearchgraph.state import AgentRole, RunStatus


async def test_end_to_end_research_stream_and_checkpoints(settings) -> None:
    runtime = ResearchRuntime(settings, worker_count=1)
    await runtime.start()
    try:
        state = await runtime.submit(
            "比较新能源储能路线的产业化条件、增长趋势与主要风险",
            session_id="test-session",
        )
        events = [event async for event in runtime.events(state["run_id"])]
        result = runtime.repository.get_run(state["run_id"])
    finally:
        await runtime.stop()

    assert result is not None
    assert result["status"] == RunStatus.COMPLETED
    assert result["report"].startswith("# 研究报告")
    required = {
        AgentRole.ATLAS.value,
        AgentRole.BEACON.value,
        AgentRole.PRISM.value,
        AgentRole.SENTINEL.value,
        AgentRole.SCRIBE.value,
    }
    assert required.issubset(set(result["completed_nodes"]))
    assert any(event.kind == "checkpoint.saved" for event in events)
    assert events[-1].kind == "run.completed"
    assert result["evidence"]
    assert result["analyses"][0]["sql"].endswith("LIMIT 4")


async def test_resume_route_skips_completed_nodes(settings) -> None:
    runtime = ResearchRuntime(settings, worker_count=1)
    state = await runtime.submit("测试一个可恢复的研究任务")
    # Do not start workers: emulate a saved checkpoint after Atlas.
    state["completed_nodes"] = [AgentRole.ATLAS.value]
    state["plan"] = {"objective": state["query"], "tasks": [], "assumptions": []}
    runtime.repository.save_checkpoint(state, AgentRole.ATLAS.value)

    assert runtime.graph._resume_route(state) == AgentRole.BEACON.value


async def test_sentinel_routes_low_quality_research_through_forge(settings) -> None:
    settings.max_search_rounds = 1
    runtime = ResearchRuntime(settings, worker_count=1)
    await runtime.start()
    try:
        state = await runtime.submit("quantum_photonics")
        _events = [event async for event in runtime.events(state["run_id"])]
        result = runtime.repository.get_run(state["run_id"])
    finally:
        await runtime.stop()

    assert result is not None
    assert AgentRole.FORGE.value in result["completed_nodes"]
    assert result["repairs"]
    assert "合成" in result["repairs"][0]["outcome"]
