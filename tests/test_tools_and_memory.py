from __future__ import annotations

from openresearchgraph.memory import TwoLayerMemory
from openresearchgraph.state import AgentRole
from openresearchgraph.storage import Repository
from openresearchgraph.tools import LocalCorpusSearchTool, ToolContext, ToolFactory


async def test_tool_factory_validates_and_returns_provenance() -> None:
    events: list[tuple[str, dict]] = []

    async def emit(kind, role, message, data):
        events.append((kind, data))

    factory = ToolFactory()
    factory.register("search_corpus", "demo search", LocalCorpusSearchTool(), {"query"})
    result = await factory.invoke(
        "search_corpus",
        {"query": "储能 产业化 数据"},
        ToolContext(run_id="test-run", role=AgentRole.SCOUT, emit=emit),
    )
    assert result.sources
    assert all(source.content_hash for source in result.sources)
    assert [kind for kind, _ in events] == ["tool.started", "tool.completed"]
    assert all(data["run_id"] == "test-run" for _, data in events)


def test_two_layer_memory_fuses_session_and_semantic_context(settings) -> None:
    repository = Repository(settings.database_path)
    memory = TwoLayerMemory(repository)
    memory.remember_session("candidate", "用户关注储能产业", {"language": "zh-CN"})
    memory.remember_knowledge("储能路线评价需要比较效率和寿命", {"kind": "note"})

    context = memory.recall("candidate", "储能效率")

    assert any(item.startswith("会话摘要") for item in context)
    assert any("效率和寿命" in item for item in context)
