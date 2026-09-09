# 能力证据表

这张表用于代码评审与面试演示，避免只在文档中声称某项能力。

| 能力 | 代码入口 | 自动验证 |
| --- | --- | --- |
| 六 Agent + LangGraph | `graph.py`、`agents/` | `test_runtime.py` |
| 统一 ResearchState | `state.py` | 端到端状态断言 |
| 工具工厂与来源元数据 | `tools/base.py` | `test_tools_and_memory.py` |
| Web Search + 本地知识库 | `tools/web_search.py`、`tools/knowledge.py` | `test_search_adapters.py` |
| 递归检索与质量评分 | `agents/beacon.py` | 离线研究用例 |
| Text-to-SQL 与只读沙箱 | `tools/sql.py`、`agents/prism.py` | `test_sql_guard.py`、安全攻击集 |
| Python 代码校验、执行、自愈、绘图 | `tools/python_sandbox.py`、`agents/prism.py` | `test_python_sandbox.py` |
| 短期 + 长期语义记忆 | `memory.py`、`storage.py` | `test_tools_and_memory.py` |
| PostgreSQL + Milvus 记忆后端 | `memory.py`、`.env.example` | 默认路径不加载可选依赖 |
| asyncio 队列与 SSE | `runtime.py`、`api/app.py` | 端到端事件断言 |
| 节点 checkpoint 与续跑 | `graph.py`、`storage.py` | `test_runtime.py` |
| 520 条离线质量评测 | `evaluation.py`、`evals/benchmark_cases.jsonl` | CI 的 evaluate job |

## 面试演示路径

1. 不配置 API Key 启动服务并提交示例问题。
2. 在 UI 中展示六角色的实时事件与 checkpoint。
3. 打开最终状态，定位 `search_rounds` 的评分和改写记录。
4. 展示分析 SQL 已自动添加 `LIMIT`，再运行 SQL 攻击测试。
5. 使用相同 `session_id` 再次提交任务，查看 `memory_context`。
6. 运行离线评测并解释指标边界；不要把合成评测结果表述为线上业务效果。
