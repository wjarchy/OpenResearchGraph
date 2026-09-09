from __future__ import annotations

import ast
import asyncio
import json
import os
import subprocess
import sys
from typing import Any

from .base import ToolContext, ToolResult


class SandboxError(RuntimeError):
    """Raised when generated analysis code violates the sandbox contract."""


_FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Lambda,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Global,
    ast.Nonlocal,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Raise,
    ast.Delete,
)
_FORBIDDEN_NAMES = {
    "__builtins__",
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "globals",
    "help",
    "input",
    "locals",
    "memoryview",
    "open",
    "os",
    "pathlib",
    "shutil",
    "socket",
    "subprocess",
    "sys",
    "vars",
}
_ALLOWED_CALLS = {
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "float",
    "int",
    "len",
    "list",
    "max",
    "min",
    "range",
    "round",
    "sorted",
    "str",
    "sum",
    "tuple",
    "zip",
}


def validate_python(code: str) -> ast.Module:
    if len(code.encode("utf-8")) > 8_000:
        raise SandboxError("Python snippet exceeds the 8 KB limit")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise SandboxError(f"Invalid Python syntax: {exc.msg}") from exc
    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_NODES):
            raise SandboxError(f"Forbidden syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise SandboxError(f"Forbidden name: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise SandboxError("Private and dunder attributes are forbidden")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_CALLS:
                raise SandboxError("Only allowlisted pure functions may be called")
    return tree


def repair_python(code: str) -> tuple[str, list[str]]:
    """Apply bounded, explainable repairs before the second validation attempt."""

    repaired = code.strip()
    actions: list[str] = []
    if repaired.startswith("```"):
        lines = repaired.splitlines()
        repaired = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        actions.append("removed_markdown_fence")
    try:
        tree = ast.parse(repaired, mode="exec")
    except SyntaxError:
        return repaired, actions
    has_result = any(
        isinstance(node, ast.Name) and node.id == "result" and isinstance(node.ctx, ast.Store)
        for node in ast.walk(tree)
    )
    if not has_result and tree.body and isinstance(tree.body[-1], ast.Expr):
        tree.body[-1] = ast.Assign(
            targets=[ast.Name(id="result", ctx=ast.Store())],
            value=tree.body[-1].value,
        )
        ast.fix_missing_locations(tree)
        repaired = ast.unparse(tree)
        actions.append("captured_final_expression")
    return repaired, actions


class PythonSandboxTool:
    """Run pure-Python snippets in an isolated child process with bounded self-repair."""

    def __init__(self, timeout_seconds: float = 2.0) -> None:
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _run(code: str, data: Any, timeout_seconds: float) -> dict[str, Any]:
        payload = json.dumps(data, ensure_ascii=False)
        wrapper = f"""
import json
safe_builtins = {{
    'abs': abs, 'all': all, 'any': any, 'bool': bool, 'dict': dict,
    'enumerate': enumerate, 'float': float, 'int': int, 'len': len,
    'list': list, 'max': max, 'min': min, 'range': range, 'round': round,
    'sorted': sorted, 'str': str, 'sum': sum, 'tuple': tuple, 'zip': zip,
}}
scope = {{'__builtins__': safe_builtins, 'data': json.loads({payload!r})}}
exec(compile({code!r}, '<analysis>', 'exec'), scope, scope)
output = {{'result': scope.get('result'), 'chart': scope.get('chart')}}
print('__ORG_RESULT__' + json.dumps(output, ensure_ascii=False))
"""
        child_env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
        }
        child_env["PYTHONIOENCODING"] = "utf-8"
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-S", "-c", wrapper],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=child_env,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxError("Python analysis timed out") from exc
        if completed.returncode:
            detail = completed.stderr.strip().splitlines()[-1] if completed.stderr else "unknown"
            raise SandboxError(f"Python analysis failed: {detail[:240]}")
        marker = next(
            (
                line
                for line in reversed(completed.stdout.splitlines())
                if line.startswith("__ORG_RESULT__")
            ),
            None,
        )
        if marker is None:
            raise SandboxError("Sandbox returned no structured result")
        return json.loads(marker.removeprefix("__ORG_RESULT__"))

    async def __call__(self, arguments: dict, context: ToolContext) -> ToolResult:
        original = str(arguments["code"])
        data = arguments.get("data", {})
        candidates = [(original, [])]
        repaired, actions = repair_python(original)
        if repaired != original or actions:
            candidates.append((repaired, actions))
        errors: list[str] = []
        for attempt, (code, repairs) in enumerate(candidates, start=1):
            try:
                validate_python(code)
                output = await asyncio.to_thread(self._run, code, data, self.timeout_seconds)
                return ToolResult(
                    data={**output, "code": code},
                    metadata={"attempts": attempt, "repaired": bool(repairs), "repairs": repairs},
                )
            except (SandboxError, json.JSONDecodeError, TypeError) as exc:
                errors.append(str(exc))
        raise SandboxError("; ".join(errors))
