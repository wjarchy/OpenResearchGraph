from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".css",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
FORBIDDEN_PATH_PARTS = {"__pycache__", ".pytest_cache", ".venv", "node_modules", "dist"}
FORBIDDEN_NAMES = {".env", "id_rsa", "id_ed25519"}


def candidate_files() -> list[Path]:
    if (ROOT / ".git").exists():
        output = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True, encoding="utf-8")
        return [ROOT / line for line in output.splitlines() if line]
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not FORBIDDEN_PATH_PARTS.intersection(path.relative_to(ROOT).parts)
    ]


def main() -> None:
    findings: list[str] = []
    legacy_markers = ["深维" + "智见", "版权所有" + " 保留所有权利"]
    secret_patterns = [
        re.compile("sk" + r"-[A-Za-z0-9_-]{20,}"),
        re.compile("BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY"),
        re.compile(r"(?i)(api_key|password|secret)\s*=\s*['\"][^'\"]{12,}['\"]"),
    ]
    for path in candidate_files():
        relative = path.relative_to(ROOT)
        if path.name in FORBIDDEN_NAMES:
            findings.append(f"forbidden file: {relative}")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"non-UTF-8 text: {relative}")
            continue
        for marker in legacy_markers:
            if marker in text:
                findings.append(f"legacy organization marker: {relative}")
        for pattern in secret_patterns:
            if pattern.search(text):
                findings.append(f"potential secret: {relative}")
    if findings:
        print("Public-release check failed:")
        for finding in sorted(set(findings)):
            print(f"- {finding}")
        raise SystemExit(1)
    print(f"Public-release check passed ({len(candidate_files())} files inspected).")


if __name__ == "__main__":
    main()
