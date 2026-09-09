# OpenResearchGraph

一个面向产业研究与数据问答的、可追踪的六智能体深度研究系统。项目强调三件事：研究过程可恢复、引用来源可追溯、数据查询默认安全。

项目地址：[github.com/wjarchy/OpenResearchGraph](https://github.com/wjarchy/OpenResearchGraph)

> 当前版本是可运行的 Alpha。默认使用本地确定性 Provider，首次启动不需要 API Key；配置 OpenAI-compatible 模型后可切换为真实大模型推理。

## 为什么做它

普通聊天接口很难回答“结论从哪里来”“中途失败后如何续跑”“模型生成的 SQL 会不会越权”。OpenResearchGraph 将一项研究拆成六个职责明确的角色，并把每次状态变化、工具调用和来源元数据都记录为事件。

| 角色 | 职责 | 主要产物 |
| --- | --- | --- |
| Atlas | 拆解目标并规划研究路线 | `ResearchPlan` |
| Beacon | 递归检索、质量评分、查询改写 | `Evidence[]` |
| Prism | Text-to-SQL、统计计算、图表规范 | `AnalysisResult[]` |
| Sentinel | 证据覆盖与矛盾审查 | `Critique` |
| Forge | 诊断并修复低质量步骤 | `RepairAction[]` |
| Scribe | 融合证据、分析和审查意见 | 带引用的 Markdown 报告 |

## 核心能力

- LangGraph 状态图：所有 Agent 读写同一个 `ResearchState`，按 `Atlas → Beacon → Prism → Sentinel → Forge → Scribe` 协同。
- 工具工厂：统一注册 Web Search、本地文件知识库、Text-to-SQL、Python 沙箱和记忆召回，并集中完成参数校验、事件记录与 `SourceMetadata` 回传。
- 递归检索：Beacon 并行消费网络搜索与本地知识，按覆盖度、来源多样性和相关性评分；低质量时改写查询并继续检索。
- 安全 Text-to-SQL：只允许单条 `SELECT/WITH`，限制表白名单、行数、执行时间和 SQLite VM 步数。
- 代码分析链：生成纯 Python 分析代码，经 AST 白名单校验后在 `-I -S` 隔离子进程中限时执行；支持 Markdown 围栏清理、末表达式捕获等有界自愈，并将统计值和图表规范回传。
- 双层记忆：默认使用 SQLite + 本地 HashEmbedding；配置后切换到 PostgreSQL 会话记忆 + Milvus 长期语义召回，Agent 接口无需变化。
- 异步执行：后台任务队列与 SSE 事件流解耦；每个节点自动 checkpoint，可按 `run_id` 查看和恢复。
- 离线评测：提交 520 条确定性任务（200 检索、100 工具、100 结构化输出、120 复杂工作流），并在 CI 中完整复跑。

当前合成回归集结果：检索相关性 `100%`（门槛 `74%`）、工具无效调用率 `11%`（上限 `11%`）、结构化输出成功率 `100%`（门槛 `80%`）、复杂任务完成率 `100%`（门槛 `82%`）。这些数字用于代码回归，不代表线上或真实行业研究准确率。

## 快速开始

需要 Python 3.11+。

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
openresearchgraph
```

打开 <http://localhost:8000>。API 文档位于 <http://localhost:8000/docs>。

发起研究：

```bash
curl -N -X POST http://localhost:8000/api/research/stream \
  -H "Content-Type: application/json" \
  -d '{"query":"比较两种新能源储能路线的产业化条件"}'
```

运行测试与离线评测：

```bash
pytest
python scripts/run_eval.py
python scripts/generate_benchmark.py --check
python scripts/check_public_release.py
```

也可使用 Docker：

```bash
docker compose up --build
```

## 配置真实模型

复制 `.env.example` 为 `.env`，填写 OpenAI-compatible 服务地址、模型名与 API Key：

```env
ORG_LLM_BASE_URL=https://your-provider.example/v1
ORG_LLM_API_KEY=replace-me
ORG_LLM_MODEL=your-model
```

密钥只从环境变量读取，不会进入 checkpoint 或事件流。未配置时系统保留完整流程，使用确定性 Provider 便于演示和测试。

Web Search 通过 `ORG_WEB_SEARCH_BASE_URL` 接入通用 GET Adapter；私有 Key 只放在 `ORG_WEB_SEARCH_API_KEY`。本地资料放入 `ORG_KNOWLEDGE_DIR`（支持 `.md/.txt/.json/.csv`）即可参与检索；默认 `data/knowledge/` 中除公开示例外均被 Git 忽略，避免误传个人文件。生产式记忆可安装 `.[memory]` 并配置：

```env
ORG_MEMORY_BACKEND=postgres_milvus
ORG_POSTGRES_DSN=postgresql://user:password@localhost:5432/research
ORG_MILVUS_URI=http://localhost:19530
ORG_MILVUS_TOKEN=replace-me
```

## 架构

```text
Web UI / API Client
        │ POST + SSE
        ▼
 FastAPI ── ResearchQueue ── LangGraph Orchestrator
                                  │
       ┌────────────── shared ResearchState ──────────────┐
       ▼          ▼          ▼        ▼        ▼         ▼
    Atlas      Beacon      Prism   Sentinel   Forge    Scribe
                   │          │
                   └── ToolRegistry ── web / knowledge / SQL / Python
                                  │
                      Checkpoints + Two-layer Memory
```

详细设计见 [架构说明](docs/architecture.md)，评测口径见 [离线评测](docs/evaluation.md)，简历描述与代码证据的逐项映射见 [能力证据表](docs/capability-map.md) 和 [项目经历口径](docs/resume-notes.md)。

## 项目边界

- 未配置网络搜索时，Web Search 明确降级到项目自带的合成语料；不会伪装成真实联网结果。
- SQL 沙箱减少误操作风险，但不能代替数据库最小权限、只读账号和网络隔离。
- Python 子进程沙箱适合本地演示与可信代码，不是面向恶意租户的强隔离；生产环境仍应放入无网络容器或 microVM。
- 自动生成的研究报告必须由人复核，不应用作医疗、法律或投资建议。

## 贡献与安全

欢迎通过 Issue 或 Pull Request 提交改进。提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [SECURITY.md](SECURITY.md)。

## License

[MIT](LICENSE)
