from __future__ import annotations

import pytest

from openresearchgraph.state import AgentRole
from openresearchgraph.tools import PythonSandboxTool, SandboxError, ToolContext


@pytest.mark.asyncio
async def test_python_sandbox_returns_result_and_chart() -> None:
    tool = PythonSandboxTool(timeout_seconds=2)
    result = await tool(
        {
            "code": "values = data['values']\nresult = sum(values)\nchart = {'data': values}",
            "data": {"values": [1, 2, 3]},
        },
        ToolContext(run_id="sandbox", role=AgentRole.DATA_ANALYST),
    )
    assert result.data["result"] == 6
    assert result.data["chart"] == {"data": [1, 2, 3]}
    assert result.metadata["attempts"] == 1


@pytest.mark.asyncio
async def test_python_sandbox_repairs_markdown_and_final_expression() -> None:
    tool = PythonSandboxTool(timeout_seconds=2)
    result = await tool(
        {"code": "```python\nsum(data)\n```", "data": [2, 4]},
        ToolContext(run_id="sandbox-repair", role=AgentRole.DATA_ANALYST),
    )
    assert result.data["result"] == 6
    assert result.metadata["repaired"] is True
    assert result.metadata["attempts"] == 2


@pytest.mark.asyncio
async def test_python_sandbox_rejects_import_and_file_access() -> None:
    tool = PythonSandboxTool(timeout_seconds=2)
    for code in ("import os\nresult = 1", "result = open('secret.txt').read()"):
        with pytest.raises(SandboxError):
            await tool(
                {"code": code, "data": {}},
                ToolContext(run_id="sandbox-deny", role=AgentRole.DATA_ANALYST),
            )
