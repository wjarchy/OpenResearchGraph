from __future__ import annotations

from dataclasses import dataclass

ALLOWED_DIMENSIONS = ("sector", "region", "year", "month")
DIMENSION_LABELS = {
    "sector": "技术路线",
    "region": "区域",
    "year": "年度",
    "month": "月份",
}


@dataclass(frozen=True, slots=True)
class AnalyticsPlan:
    dimensions: tuple[str, ...]
    period_mode: str
    metric: str = "installed_capacity"

    @property
    def drilldown_path(self) -> list[str]:
        path: list[str] = []
        if "sector" in self.dimensions:
            path.extend(["sector", "region"])
        if "year" in self.dimensions:
            path.extend(["year", "month"])
        return list(dict.fromkeys(path))


class DimensionQueryPlanner:
    """Maps a natural-language analysis request to a bounded dimensional SQL plan."""

    def from_question(self, question: str) -> AnalyticsPlan:
        dimensions: list[str] = []
        if any(term in question for term in ("路线", "技术", "行业", "sector")):
            dimensions.append("sector")
        if any(term in question for term in ("区域", "地区", "region")):
            dimensions.append("region")
        if any(term in question for term in ("年", "趋势", "同比", "year")):
            dimensions.append("year")
        if any(term in question for term in ("月", "环比", "month")):
            if "year" not in dimensions:
                dimensions.append("year")
            dimensions.append("month")
        if not dimensions:
            dimensions = ["sector", "year"]
        period_mode = "cumulative" if "累计" in question else "current"
        return AnalyticsPlan(tuple(dimensions), period_mode)

    def build_sql(self, plan: AnalyticsPlan) -> str:
        if not plan.dimensions or not set(plan.dimensions).issubset(ALLOWED_DIMENSIONS):
            raise ValueError("Unsupported analytics dimension")
        dimensions = ", ".join(plan.dimensions)
        group_by = dimensions
        order_by = dimensions
        where = f"metric = '{plan.metric}'"
        effort = "printf('%d-%d人/月', MIN(effort_low), MAX(effort_high)) AS effort"
        if plan.period_mode == "current":
            return (
                f"SELECT {dimensions}, SUM(value) AS value, unit, {effort} "
                f"FROM industry_observations WHERE {where} "
                f"GROUP BY {group_by}, unit ORDER BY {order_by}"
            )

        time_dimensions = [item for item in plan.dimensions if item in {"year", "month"}]
        partition_dimensions = [item for item in plan.dimensions if item not in {"year", "month"}]
        if not time_dimensions:
            time_dimensions = ["year"]
        window_parts = []
        if partition_dimensions:
            window_parts.append(f"PARTITION BY {', '.join(partition_dimensions)}")
        window_parts.append(f"ORDER BY {', '.join(time_dimensions)}")
        window_parts.append("ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW")
        window = " ".join(window_parts)
        return (
            f"WITH period_values AS (SELECT {dimensions}, SUM(value) AS period_value, unit, "
            f"MIN(effort_low) AS effort_low, MAX(effort_high) AS effort_high "
            f"FROM industry_observations WHERE {where} GROUP BY {group_by}, unit) "
            f"SELECT {dimensions}, SUM(period_value) OVER ({window}) AS value, unit, "
            "printf('%d-%d人/月', effort_low, effort_high) AS effort "
            f"FROM period_values ORDER BY {order_by}"
        )


def period_label(year: int | None, month: int | None, mode: str) -> str:
    if year is None:
        return "全部期间"
    period = f"{year}年" if month is None else f"{year}年{month:02d}月"
    suffix = "累计" if mode == "cumulative" else "当期"
    return f"{period}{suffix}"
