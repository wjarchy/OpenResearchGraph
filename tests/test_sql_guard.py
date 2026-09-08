from __future__ import annotations

import pytest

from openresearchgraph.tools.sql import SQLGuard, SQLValidationError


@pytest.fixture
def guard() -> SQLGuard:
    return SQLGuard({"industry_metrics"}, max_rows=25)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE industry_metrics",
        "SELECT * FROM users",
        "SELECT * FROM industry_metrics; DELETE FROM industry_metrics",
        "PRAGMA table_info(industry_metrics)",
        "SELECT * FROM industry_metrics -- bypass",
        "ATTACH DATABASE 'private.db' AS private",
        "SELECT load_extension('unsafe') FROM industry_metrics",
        "SELECT randomblob(1000000000) FROM industry_metrics",
    ],
)
def test_rejects_unsafe_queries(guard: SQLGuard, sql: str) -> None:
    with pytest.raises(SQLValidationError):
        guard.validate_and_rewrite(sql)


def test_adds_default_row_limit(guard: SQLGuard) -> None:
    result = guard.validate_and_rewrite("SELECT year, value FROM industry_metrics")
    assert result.endswith("LIMIT 25")


def test_caps_requested_row_limit(guard: SQLGuard) -> None:
    result = guard.validate_and_rewrite("SELECT * FROM industry_metrics LIMIT 999")
    assert result.endswith("LIMIT 25")


def test_allows_cte_over_whitelisted_table(guard: SQLGuard) -> None:
    result = guard.validate_and_rewrite(
        "WITH yearly AS (SELECT year, value FROM industry_metrics) SELECT * FROM yearly"
    )
    assert result.endswith("LIMIT 25")
