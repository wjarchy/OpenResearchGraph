from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from .config import Settings
from .runtime import ResearchRuntime
from .state import AgentRole, RunStatus
from .tools.sql import SQLGuard, SQLValidationError


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


async def evaluate_research_cases(cases: list[dict[str, Any]], database_path: Path) -> list[dict]:
    settings = Settings(database_url=f"sqlite:///{database_path.as_posix()}")
    runtime = ResearchRuntime(settings, worker_count=1)
    results: list[dict] = []
    await runtime.start()
    try:
        for case in cases:
            state = await runtime.submit(case["query"], session_id="offline-eval")
            events = [event async for event in runtime.events(state["run_id"])]
            final = runtime.repository.get_run(state["run_id"]) or {}
            evidence_count = len(final.get("evidence", []))
            report = final.get("report", "")
            retrieved_uris = {item["source"]["uri"] for item in final.get("evidence", [])}
            expected_uris = set(case.get("expected_uris", []))
            matched_uris = retrieved_uris & expected_uris
            retrieval_recall = len(matched_uris) / len(expected_uris) if expected_uris else 1.0
            retrieval_precision = len(matched_uris) / len(retrieved_uris) if retrieved_uris else 0.0
            anchors = case.get("answer_anchors", [])
            answer_accuracy = (
                sum(anchor in report for anchor in anchors) / len(anchors) if anchors else 1.0
            )
            source_references = report.count("- [S")
            required_roles = {
                AgentRole.ARCHITECT.value,
                AgentRole.SCOUT.value,
                AgentRole.DATA_ANALYST.value,
                AgentRole.CRITIC.value,
                AgentRole.WRITER.value,
            }
            checks = {
                "completed": final.get("status") == RunStatus.COMPLETED,
                "source_floor": evidence_count >= case.get("minimum_sources", 2),
                "citation_coverage": source_references >= evidence_count > 0,
                "role_coverage": required_roles.issubset(set(final.get("completed_nodes", []))),
                "has_analysis": bool(final.get("analyses")),
                "terminal_event": bool(events and events[-1].kind == "run.completed"),
                "retrieval_recall": retrieval_recall >= case.get("minimum_recall", 1.0),
                "answer_accuracy": answer_accuracy >= case.get("minimum_answer_accuracy", 1.0),
                "recursive_rounds": len(final.get("search_rounds", []))
                >= case.get("minimum_rounds", 1),
            }
            results.append(
                {
                    "case_id": case["case_id"],
                    "passed": all(checks.values()),
                    "checks": checks,
                    "source_count": evidence_count,
                    "search_rounds": len(final.get("search_rounds", [])),
                    "critic_score": (final.get("critique") or {}).get("score", 0),
                    "retrieval_precision": round(retrieval_precision, 3),
                    "retrieval_recall": round(retrieval_recall, 3),
                    "answer_accuracy": round(answer_accuracy, 3),
                }
            )
    finally:
        await runtime.stop()
    return results


def evaluate_sql_safety() -> dict[str, Any]:
    guard = SQLGuard({"industry_metrics"}, max_rows=50)
    attacks = [
        "DROP TABLE industry_metrics",
        "SELECT * FROM private_users",
        "SELECT * FROM industry_metrics; DELETE FROM industry_metrics",
        "PRAGMA database_list",
        "SELECT * FROM industry_metrics -- remove limit",
        "ATTACH DATABASE 'other.db' AS other",
    ]
    rejected = 0
    for attack in attacks:
        try:
            guard.validate_and_rewrite(attack)
        except SQLValidationError:
            rejected += 1
    return {
        "passed": rejected == len(attacks),
        "rejected": rejected,
        "total": len(attacks),
        "rate": round(rejected / len(attacks), 3),
    }


async def run_evaluation(dataset: Path) -> dict[str, Any]:
    cases = load_cases(dataset)
    with tempfile.TemporaryDirectory(prefix="openresearchgraph-eval-") as temp_dir:
        research = await evaluate_research_cases(cases, Path(temp_dir) / "eval.db")
    sql_safety = evaluate_sql_safety()
    passed_cases = sum(result["passed"] for result in research)
    return {
        "suite": "openresearchgraph-offline-v1",
        "deterministic": True,
        "research": {
            "passed": passed_cases,
            "total": len(research),
            "pass_rate": round(passed_cases / len(research), 3) if research else 0,
            "cases": research,
        },
        "sql_safety": sql_safety,
        "passed": passed_cases == len(research) and sql_safety["passed"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline OpenResearchGraph evaluation")
    parser.add_argument("--dataset", type=Path, default=Path("evals/research_cases.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/eval-report.json"))
    args = parser.parse_args()
    report = asyncio.run(run_evaluation(args.dataset))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
