# OpenResearchGraph

一个面向产业研究与数据问答的、可追踪的六智能体深度研究系统。项目强调三件事：研究过程可恢复、引用来源可追溯、数据查询默认安全。

> 当前版本是可运行的 Alpha。默认使用本地确定性 Provider，首次启动不需要 API Key；配置 OpenAI-compatible 模型后可切换为真实大模型推理。

## 为什么做它

普通聊天接口很难回答“结论从哪里来”“中途失败后如何续跑”“模型生成的 SQL 会不会越权”。OpenResearchGraph 将一项研究拆成六个职责明确的角色，并把每次状态变化、工具调用和来源元数据都记录为事件。

| 角色 | 职责 | 主要产物 |
| --- | --- | --- |
| Architect | 拆解问题与安排执行计划 | `ResearchPlan` |
| Scout | 递归检索、质量评分、查询改写 | `Evidence[]` |
| Data Analyst | Text-to-SQL、统计计算、图表规范 | `AnalysisResult[]` |
| Critic | 证据覆盖与矛盾检查 | `Critique` |
| Wizard | 补救低质量步骤与生成补充任务 | `RepairAction[]` |
| Writer | 合并证据、分析和批评意见 | 带引用的 Markdown 报告 |

## 核心能力

- LangGraph 状态图：所有 Agent 读写同一个 `ResearchState`，按 `Architect → Scout → Data Analyst → Critic → Wizard → Writer` 协同。
- 工具工厂：工具注册、参数校验、统一调用和 `SourceMetadata` 回传集中管理。
- 递归检索：Scout 对覆盖度、来源多样性和内容长度评分，低质量时改写查询并继续检索。
- 安全 Text-to-SQL：只允许单条 `SELECT/WITH`，限制表白名单、行数、执行时间和 SQLite VM 步数。
- 双层记忆：短期会话摘要/偏好与长期语义知识分别存储，检索结果在进入 Agent 前融合。
- 异步执行：后台任务队列与 SSE 事件流解耦；每个节点自动 checkpoint，可按 `run_id` 查看和恢复。
- 离线评测：包含搜索质量、引用覆盖、SQL 安全和流程完整性用例，可在 CI 中复跑。

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

## 架构

```text
Web UI / API Client
        │ POST + SSE
        ▼
 FastAPI ── ResearchQueue ── LangGraph Orchestrator
                                  │
       ┌────────────── shared ResearchState ──────────────┐
       ▼          ▼          ▼        ▼        ▼         ▼
  Architect     Scout     Analyst   Critic   Wizard    Writer
                   │          │
                   └── ToolRegistry ── web / knowledge / safe SQL
                                  │
                      Checkpoints + Two-layer Memory
```

详细设计见 [架构说明](docs/architecture.md)，评测口径见 [离线评测](docs/evaluation.md)，简历描述与代码证据的逐项映射见 [能力证据表](docs/capability-map.md) 和 [项目经历口径](docs/resume-notes.md)。

## 项目边界

- 演示搜索工具只读取项目自带的合成语料；生产接入需自行实现或注册网络搜索 Adapter。
- SQL 沙箱减少误操作风险，但不能代替数据库最小权限、只读账号和网络隔离。
- 自动生成的研究报告必须由人复核，不应用作医疗、法律或投资建议。

## 贡献与安全

欢迎通过 Issue 或 Pull Request 提交改进。提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [SECURITY.md](SECURITY.md)。

## License

[MIT](LICENSE)
