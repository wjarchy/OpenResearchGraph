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

数据集位于 `evals/research_cases.jsonl`。所有内容是合成样例，结果只说明离线回归集是否通过，不代表真实业务准确率。

## 运行

```bash
python scripts/run_eval.py
```

报告写入 `artifacts/eval-report.json`，该目录默认不提交，避免把一次本地结果伪装成长期性能承诺。CI 每次从源码重新生成结果。
