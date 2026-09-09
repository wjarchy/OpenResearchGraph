from __future__ import annotations

import pytest

from openresearchgraph.state import AgentRole
from openresearchgraph.tools import LocalKnowledgeSearchTool, ToolContext, WebSearchTool


@pytest.mark.asyncio
async def test_local_knowledge_search_tracks_file_source(tmp_path) -> None:
    (tmp_path / "notes.md").write_text("产业研究需要检查来源多样性。", encoding="utf-8")
    tool = LocalKnowledgeSearchTool(tmp_path)
    result = await tool(
        {"query": "产业研究 来源", "limit": 3},
        ToolContext(run_id="kb", role=AgentRole.SCOUT),
    )
    assert result.sources[0].uri == "knowledge://notes.md"
    assert result.sources[0].attributes["local"] is True


@pytest.mark.asyncio
async def test_web_search_has_explicit_offline_fallback() -> None:
    tool = WebSearchTool()
    result = await tool(
        {"query": "储能 电芯安全", "limit": 2},
        ToolContext(run_id="web", role=AgentRole.SCOUT),
    )
    assert result.sources
    assert result.metadata == {
        "query": "储能 电芯安全",
        "mode": "offline-fallback",
        "network_used": False,
    }
