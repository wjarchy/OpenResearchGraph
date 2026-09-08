# 架构说明

## 设计目标

OpenResearchGraph 把研究任务视为一个可恢复的状态转换过程，而不是一次不可见的模型调用。系统的边界对象是 `ResearchState`：计划、证据、分析、批评、修复与报告都必须通过该对象传递。

## 状态图

```text
START ── resume router ──► Architect ─► Scout ─► Data Analyst ─► Critic
                                                                  │
                                                   passed ────────┤
                                                                  ▼
                                          failed ─► Wizard ───► Writer ─► END
```

START 后的路由读取 `completed_nodes`。失败任务重新入队后，从第一个未完成角色继续，而不是从头执行。Critic 达标时跳过 Wizard；不达标时由 Wizard 补充检索并记录 `RepairAction`。

## 证据链

所有检索工具返回统一 `ToolResult`。每个来源都必须带标题、URI、Provider、抓取时间、内容哈希与相关度。Agent 只能消费这套结构，Writer 则把来源编号写回报告，形成从结论到来源的可定位链路。

## Text-to-SQL 安全边界

执行链由四层组成：

1. 语法外形检查：只接受单条 `SELECT` 或 `WITH`。
2. 关键字与表白名单：拒绝 DDL/DML、PRAGMA、ATTACH 及未知表。
3. 查询改写：强制设置最大返回行数。
4. 数据库约束：以 SQLite `mode=ro` 连接，打开 `query_only`，并通过 progress handler 限制执行时间和 VM 步数。

生产环境仍应使用专门的只读数据库账号，并把分析副本与交易库隔离。

## 记忆

- 短期层保存会话摘要和表达偏好，以 `session_id` 定位。
- 长期层保存研究摘要与向量。默认 HashEmbedding 不上传文本，适合离线演示。
- recall 将语义相似度和词项重合度加权融合，再与短期上下文一起放入 `memory_context`。

存储接口独立于 Agent，可替换成外部缓存或向量数据库，而不用改变状态图。

## 异步与一致性

API 只负责入队，Worker 执行 LangGraph。事件先写 SQLite，再通过 Condition 唤醒 SSE 消费者，因此客户端断线后可使用事件序号补读。每个 Agent 成功后先保存 checkpoint，再发出完成事件，减少 UI 已显示成功但状态尚未落盘的窗口。
