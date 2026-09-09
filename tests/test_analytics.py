from __future__ import annotations

from openresearchgraph.analytics import DimensionQueryPlanner, period_label
from openresearchgraph.state import AgentRole
from openresearchgraph.storage import Repository
from openresearchgraph.tools import SafeSQLExecutor, ToolContext


def test_arbitrary_dimensions_and_drilldown_plan() -> None:
    plan = DimensionQueryPlanner().from_question("按技术路线、地区和月份查看累计装机")

    assert plan.dimensions == ("sector", "region", "year", "month")
    assert plan.period_mode == "cumulative"
    assert plan.drilldown_path == ["sector", "region", "year", "month"]


def test_period_display_supports_current_and_cumulative() -> None:
    assert period_label(2024, None, "current") == "2024年当期"
    assert period_label(2024, 3, "cumulative") == "2024年03月累计"


async def test_cumulative_sql_and_effort_format(settings) -> None:
    Repository(settings.database_path)
    planner = DimensionQueryPlanner()
    plan = planner.from_question("按技术路线和月份查看累计装机")
    executor = SafeSQLExecutor(
        settings.database_path,
        {"industry_observations"},
        max_rows=100,
        timeout_seconds=1,
    )
    result = await executor(
        {"sql": planner.build_sql(plan)},
        ToolContext(run_id="analytics-test", role=AgentRole.PRISM),
    )

    assert "effort" in result.data["columns"]
    effort_index = result.data["columns"].index("effort")
    assert all(str(row[effort_index]).endswith("人/月") for row in result.data["rows"])
    value_index = result.data["columns"].index("value")
    battery_values = [
        row[value_index] for row in result.data["rows"] if row[0] == "battery_storage"
    ]
    assert battery_values == sorted(battery_values[:4]) + sorted(battery_values[4:])
