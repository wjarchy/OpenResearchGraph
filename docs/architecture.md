# 架构说明

## 设计目标

OpenResearchGraph 把研究任务视为一个可恢复的状态转换过程，而不是一次不可见的模型调用。系统的边界对象是 `ResearchState`：计划、证据、分析、批评、修复与报告都必须通过该对象传递。

## 状态图

```text
START ── resume router ──► Atlas ─► Beacon ─► Prism ─► Sentinel
                                                                  │
                                                   passed ────────┤
                                                                  ▼
                                      failed ─► Forge ───► Scribe ─► END
```

START 后的路由读取 `completed_nodes`。失败任务重新入队后，从第一个未完成角色继续，而不是从头执行。Sentinel 达标时跳过 Forge；不达标时由 Forge 补充检索并记录 `RepairAction`。

## 证据链

Web Search Adapter、本地文件知识库与离线合成语料都返回统一 `ToolResult`。每个来源必须带标题、URI、Provider、抓取时间、内容哈希与相关度。Agent 只能消费这套结构，Scribe 则把来源编号写回报告，形成从结论到来源的可定位链路。

## Python 分析沙箱

Prism 将 SQL 结果与生成的分析代码交给 `PythonSandboxTool`。代码先经过 AST 白名单检查，禁止 import、文件访问、动态执行、私有属性和非白名单调用，再使用 `python -I -S` 在最小环境变量的子进程中限时执行。工具可清理 Markdown code fence、捕获末表达式后重试，并以 JSON 返回统计结果和 chart spec。此边界是本地防御纵深；恶意多租户部署仍需容器或 microVM。

## Text-to-SQL 安全边界

执行链由四层组成：

1. 语法外形检查：只接受单条 `SELECT` 或 `WITH`。
2. 关键字与表白名单：拒绝 DDL/DML、PRAGMA、ATTACH 及未知表。
3. 查询改写：强制设置最大返回行数。
4. 数据库约束：以 SQLite `mode=ro` 连接，打开 `query_only`，并通过 progress handler 限制执行时间和 VM 步数。

生产环境仍应使用专门的只读数据库账号，并把分析副本与交易库隔离。

## 记忆

- 短期层保存会话摘要和表达偏好，以 `session_id` 定位。
- 长期层保存研究摘要与向量。默认 SQLite + HashEmbedding 不上传文本，适合离线演示。
- `ORG_MEMORY_BACKEND=postgres_milvus` 时，短期层写入 PostgreSQL，长期向量与元数据写入 Milvus；依赖通过 `.[memory]` 可选安装。
- recall 将语义相似度和词项重合度加权融合，再与短期上下文一起放入 `memory_context`。

存储接口独立于 Agent，可替换成外部缓存或向量数据库，而不用改变状态图。

## 异步与一致性

API 只负责入队，Worker 执行 LangGraph。事件先写 SQLite，再通过 Condition 唤醒 SSE 消费者，因此客户端断线后可使用事件序号补读。每个 Agent 成功后先保存 checkpoint，再发出完成事件，减少 UI 已显示成功但状态尚未落盘的窗口。
