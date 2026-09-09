# 离线评测

评测集的目标不是制造一个漂亮但不可解释的总分，而是给关键回归点设置门槛。

## 指标

- `retrieval_recall`：期望 URI 中被 Scout 找到的比例。
- `retrieval_precision`：当前结果中属于用例期望 URI 的比例，仅报告，不作为 Alpha 阻断条件。
- `answer_accuracy`：用例定义的事实锚点在最终报告中的覆盖比例。
- `citation_coverage`：每条进入状态的证据是否在来源列表中拥有引用编号。
- `recursive_rounds`：指定困难用例是否触发低质量查询改写。
- `sql_safety`：攻击查询被 SQLGuard 拒绝的比例。
- `role_coverage`：必要 Agent 是否都完成并留下 checkpoint。

定向端到端用例位于 `evals/research_cases.jsonl`。规模化基准位于 `evals/benchmark_cases.jsonl`，由 `scripts/generate_benchmark.py` 确定性生成，共 520 条：

| 类别 | 数量 | 实际执行 |
| --- | ---: | --- |
| retrieval | 200 | 调用本地检索器并核对 Top-1 来源 |
| tool_call | 100 | 调用 ToolFactory，包含 11 条固定无效调用 |
| structured_output | 100 | 生成维度计划与 SQL，经 SQLGuard 和 Pydantic 往返校验 |
| complex_workflow | 120 | 通过异步队列完整执行六 Agent、Python 子进程、SSE 与 checkpoint |

门槛分别是：检索相关性 `>=74%`、工具无效调用率 `<=11%`、结构化输出成功率 `>=80%`、复杂任务完成率 `>=82%`。当前确定性合成集实测为 `100% / 11% / 100% / 100%`。

所有内容是合成样例，结果只说明离线回归集是否通过，不代表真实业务准确率，也不能与其他数据集上的结果直接比较。`11%` 是固定工具调用集中的观测比例，不是线上模型调用统计。

## 运行

```bash
python scripts/run_eval.py
python scripts/generate_benchmark.py --check
```

报告写入 `artifacts/eval-report.json`，该目录默认不提交，避免把一次本地结果伪装成长期性能承诺。CI 每次从源码重新生成结果。
