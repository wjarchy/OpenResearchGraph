from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_cases() -> list[dict]:
    cases: list[dict] = []
    retrieval_templates = (
        (
            "电化学储能 电芯安全 循环寿命 高频调节 样例{index}",
            "local://demo/storage-route-overview",
        ),
        (
            "长时储能 项目选址 热管理 容量补偿 样例{index}",
            "local://demo/long-duration-storage",
        ),
        (
            "产业研究 证据质量 来源多样性 反例检查 样例{index}",
            "local://method/evidence-quality",
        ),
        (
            "installed_capacity GWh Text-to-SQL 同比增速 样例{index}",
            "local://demo/metric-definitions",
        ),
    )
    for index in range(200):
        template, uri = retrieval_templates[index % len(retrieval_templates)]
        cases.append(
            {
                "case_id": f"retrieval-{index:03d}",
                "category": "retrieval",
                "query": template.format(index=index),
                "expected_uri": uri,
            }
        )

    for index in range(100):
        valid = index < 89
        cases.append(
            {
                "case_id": f"tool-{index:03d}",
                "category": "tool_call",
                "tool": "benchmark_echo" if valid else "unregistered_tool",
                "arguments": {"value": index},
                "expected_valid": valid,
            }
        )

    structured_queries = (
        "按行业和年份分析装机趋势",
        "按区域和月份查看当期装机",
        "按行业区域对比累计装机",
        "按年份统计 installed_capacity",
    )
    for index in range(100):
        cases.append(
            {
                "case_id": f"structured-{index:03d}",
                "category": "structured_output",
                "query": structured_queries[index % len(structured_queries)],
            }
        )

    complex_queries = (
        "比较新能源储能路线的产业化条件、增长趋势与主要风险",
        "分析储能装机数据的年度趋势并说明证据限制",
        "如何评价产业研究的证据质量与数据口径",
        "按区域和月份分析装机变化并生成图表",
    )
    for index in range(120):
        cases.append(
            {
                "case_id": f"complex-{index:03d}",
                "category": "complex_workflow",
                "query": f"{complex_queries[index % len(complex_queries)]}（回归样例{index}）",
            }
        )
    return cases


def render(cases: list[dict]) -> str:
    return "".join(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n" for case in cases)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the deterministic 520-case benchmark")
    parser.add_argument("--output", type=Path, default=Path("evals/benchmark_cases.jsonl"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render(build_cases())
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        raise SystemExit(0 if current == expected else 1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8")
    print(f"Generated {len(build_cases())} cases at {args.output}")


if __name__ == "__main__":
    main()
