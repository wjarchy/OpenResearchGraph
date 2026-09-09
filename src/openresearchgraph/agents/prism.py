from __future__ import annotations

from collections import defaultdict
from statistics import mean

from ..analytics import AnalyticsPlan, DimensionQueryPlanner, period_label
from ..state import AgentRole, AnalysisResult, ResearchState
from ..tools import ToolContext
from .base import BaseAgent


class PrismAgent(BaseAgent):
    role = AgentRole.PRISM

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.planner = DimensionQueryPlanner()

    @staticmethod
    def _statistics(columns: list[str], rows: list[list]) -> dict[str, float]:
        if "value" not in columns:
            return {}
        value_index = columns.index("value")
        all_values = [float(row[value_index]) for row in rows]
        output = {"mean": round(mean(all_values), 4)} if all_values else {}
        if not {"sector", "year"}.issubset(columns):
            return output
        sector_index = columns.index("sector")
        year_index = columns.index("year")
        series: dict[str, list[tuple[int, float]]] = defaultdict(list)
        for row in rows:
            series[str(row[sector_index])].append((int(row[year_index]), float(row[value_index])))
        for sector, values in series.items():
            annual: dict[int, float] = defaultdict(float)
            for year, value in values:
                annual[year] += value
            ordered = sorted(annual.items())
            first, last = ordered[0], ordered[-1]
            years = last[0] - first[0]
            if years > 0 and first[1] > 0:
                output[f"{sector}_cagr"] = round((last[1] / first[1]) ** (1 / years) - 1, 4)
        return output

    async def _text_to_sql(self, question: str) -> tuple[str, AnalyticsPlan]:
        plan = self.planner.from_question(question)
        if self.provider.is_remote:
            schema = (
                "industry_observations(sector TEXT, region TEXT, year INTEGER, month INTEGER, "
                "metric TEXT, value REAL, unit TEXT, effort_low INTEGER, effort_high INTEGER)"
            )
            generated = await self.provider.complete(
                (
                    "Generate one SQLite SELECT query. Use only the supplied schema and requested "
                    "dimensions. Return dimensions first, then aggregated value and unit. Return "
                    "effort as a string such as 5-30人/月. Do not use comments, DDL, or markdown."
                ),
                (
                    f"Schema: {schema}\nQuestion: {question}\n"
                    f"Dimensions: {', '.join(plan.dimensions)}\nPeriod: {plan.period_mode}"
                ),
            )
            sql = generated.strip().removeprefix("```sql").removesuffix("```").strip()
            return sql, plan
        return self.planner.build_sql(plan), plan

    @staticmethod
    def _chart_spec(plan: AnalyticsPlan, columns: list[str], rows: list[list]) -> dict[str, object]:
        records = [dict(zip(columns, row, strict=False)) for row in rows]
        series_field = next(
            (item for item in ("sector", "region") if item in plan.dimensions),
            plan.dimensions[0],
        )
        data = []
        for record in records:
            year = int(record["year"]) if "year" in record else None
            month = int(record["month"]) if "month" in record else None
            x_value = (
                period_label(year, month, plan.period_mode)
                if year is not None
                else str(record.get(plan.dimensions[-1], "全部"))
            )
            data.append(
                {
                    "series": str(record.get(series_field, "全部")),
                    "x": x_value,
                    "y": float(record.get("value", 0)),
                }
            )
        return {
            "type": "line" if "year" in plan.dimensions else "bar",
            "x": "period" if "year" in plan.dimensions else plan.dimensions[-1],
            "y": "value",
            "series": series_field,
            "unit": "GWh",
            "title": "装机容量分析（合成演示数据）",
            "data": data,
        }

    async def run(self, state: ResearchState) -> ResearchState:
        sql, plan = await self._text_to_sql(state["query"])
        context = ToolContext(run_id=state["run_id"], role=self.role, emit=self.emit)
        result = await self.tools.invoke("query_industry_data", {"sql": sql}, context)
        columns = result.data["columns"]
        rows = result.data["rows"]
        chart_input = self._chart_spec(plan, columns, rows)
        value_index = columns.index("value") if "value" in columns else 0
        generated_code = "\n".join(
            [
                "values = [float(row[data['value_index']]) for row in data['rows']]",
                "result = {'mean': round(sum(values) / len(values), 4) if values else 0.0}",
                "chart = data['chart']",
            ]
        )
        python_result = await self.tools.invoke(
            "run_python_analysis",
            {
                "code": generated_code,
                "data": {"rows": rows, "value_index": value_index, "chart": chart_input},
            },
            context,
        )
        statistics = self._statistics(columns, rows)
        statistics.update(python_result.data["result"] or {})
        analysis = AnalysisResult(
            title="合成样例中的多维装机分析",
            summary=(
                "自然语言问题已转换为维度计划和只读 SQL，并完成分组统计、期间显示、"
                "人月格式与图表规范生成；结果仅用于演示分析链路。"
            ),
            sql=result.data["sql"],
            columns=columns,
            rows=rows,
            statistics=statistics,
            dimensions=list(plan.dimensions),
            drilldown_path=plan.drilldown_path,
            display_formats={
                "period": "YYYY年 / YYYY年MM月 + 累计或当期",
                "effort": "5-30人/月",
            },
            chart_spec=python_result.data["chart"],
            sources=["local://database/industry_observations"],
        )
        state["analyses"] = [analysis.model_dump(mode="json")]
        return self.completed(state)
