from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .base import ToolContext, ToolResult


class SQLValidationError(ValueError):
    pass


class SQLGuard:
    FORBIDDEN = frozenset(
        {
            "alter",
            "attach",
            "create",
            "delete",
            "detach",
            "drop",
            "insert",
            "load_extension",
            "pragma",
            "randomblob",
            "readfile",
            "reindex",
            "replace",
            "truncate",
            "update",
            "vacuum",
            "writefile",
            "zeroblob",
        }
    )

    def __init__(self, allowed_tables: set[str], max_rows: int = 500) -> None:
        self.allowed_tables = {name.lower() for name in allowed_tables}
        self.max_rows = max_rows

    def validate_and_rewrite(self, sql: str) -> str:
        statement = sql.strip()
        if not statement:
            raise SQLValidationError("SQL cannot be empty")
        if "--" in statement or "/*" in statement or "*/" in statement:
            raise SQLValidationError("SQL comments are not allowed")
        if ";" in statement.rstrip(";"):
            raise SQLValidationError("Only one SQL statement is allowed")
        statement = statement.rstrip(";").strip()
        first = re.match(r"(?is)^\s*([a-z]+)", statement)
        if not first or first.group(1).lower() not in {"select", "with"}:
            raise SQLValidationError("Only SELECT or WITH queries are allowed")
        words = {word.lower() for word in re.findall(r"\b[a-zA-Z_]+\b", statement)}
        forbidden = words & self.FORBIDDEN
        if forbidden:
            raise SQLValidationError(f"Forbidden SQL keyword: {sorted(forbidden)[0]}")
        tables = {
            match.lower()
            for match in re.findall(r"(?is)\b(?:from|join)\s+[\"`\[]?([a-zA-Z_][\w]*)", statement)
        }
        cte_names = {
            match.lower()
            for match in re.findall(r"(?is)(?:\bwith|,)\s*([a-zA-Z_]\w*)\s+as\s*\(", statement)
        }
        unknown = tables.difference(self.allowed_tables | cte_names)
        if not tables:
            raise SQLValidationError("Query must reference an allowed table")
        if unknown:
            raise SQLValidationError(f"Table is not allowed: {sorted(unknown)[0]}")
        limit_match = re.search(r"(?is)\blimit\s+(\d+)\s*$", statement)
        if limit_match:
            requested = int(limit_match.group(1))
            if requested > self.max_rows:
                statement = statement[: limit_match.start(1)] + str(self.max_rows)
        else:
            statement = f"{statement} LIMIT {self.max_rows}"
        return statement


class SafeSQLExecutor:
    def __init__(
        self,
        database_path: Path,
        allowed_tables: set[str],
        max_rows: int = 500,
        timeout_seconds: float = 2.0,
        max_vm_steps: int = 100_000,
    ) -> None:
        self.database_path = database_path
        self.guard = SQLGuard(allowed_tables=allowed_tables, max_rows=max_rows)
        self.timeout_seconds = timeout_seconds
        self.max_vm_steps = max_vm_steps

    async def __call__(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        guarded_sql = self.guard.validate_and_rewrite(str(arguments["sql"]))
        deadline = time.monotonic() + self.timeout_seconds
        calls = 0

        def progress() -> int:
            nonlocal calls
            calls += 1_000
            return int(calls > self.max_vm_steps or time.monotonic() > deadline)

        uri = f"file:{self.database_path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=self.timeout_seconds)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.set_progress_handler(progress, 1_000)
            cursor = connection.execute(guarded_sql)
            columns = [item[0] for item in cursor.description or []]
            rows = [list(row) for row in cursor.fetchall()]
        except sqlite3.DatabaseError as exc:
            raise SQLValidationError(f"Read-only query failed: {exc}") from exc
        finally:
            connection.close()
        return ToolResult(
            data={"sql": guarded_sql, "columns": columns, "rows": rows},
            metadata={"row_count": len(rows), "read_only": True},
        )
