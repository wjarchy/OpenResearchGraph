from __future__ import annotations

from pathlib import Path

import pytest

from openresearchgraph.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        max_search_rounds=3,
        max_sql_rows=4,
        sql_timeout_seconds=1,
    )
