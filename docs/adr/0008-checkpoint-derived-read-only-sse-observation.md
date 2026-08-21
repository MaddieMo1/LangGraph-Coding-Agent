# ADR 0008：基于 Checkpoint 派生只读 SSE 观察流

- 状态：Accepted
- 日期：2026-08-20

## 背景

Day17 已建立本地启动身份、最小权限审批和防篡改审计链，但团队成员仍无法在不接触本地控制台的情况下观察长时间运行的任务。Day18 需要提供多观察者、断线续传、presence 和有界事件导出，同时必须保留单活动任务锁、人工审批、Git worktree 所有权及本地 checkpoint 的权威性。

项目当前是单进程 Gradio + `WorkflowRuntime` + SQLite LangGraph checkpointer。为只读观察引入第二个执行服务、消息队列或可写远程 API 会扩大运维与安全面，也可能造成重复执行。

## 决策

在同一个 FastAPI/Gradio ASGI 进程内增加独立的只读观察页面、会话入口和 SSE 路由。LangGraph checkpoint 仍是唯一权威状态；确定性的 `ObservationProjector` 在 checkpoint 持久化后生成字段白名单化的任务快照和有序事件，并写入同一个 SQLite 文件中的独立表。

SSE 使用持久化整数 cursor 和 `Last-Event-ID` 实现续传。过期或未来 cursor 返回权威脱敏快照并重置位置，不调用或恢复工作流。投影写入使用幂等键，多个客户端只读取同一事件，不会产生第二次执行。

观察入口使用共享只读令牌建立 HttpOnly Cookie 会话，服务端签发匿名 observer ID，并以有界心跳维护 presence。远程端没有审批、重试、取消、Git 或文件写入 API。非 loopback 监听默认关闭；无强令牌或未显式接受明文 HTTP 风险时失败关闭。

## 结果

### 正面

- 复用现有进程和 SQLite，部署与维护成本低。
- checkpoint 权威性和单任务所有权不变。
- 持久化 cursor 支持多观察者和断线续传。
- SSE 是单向协议，天然缩小远程命令面。
- 观察投影可重建，失败不会阻断本地工作流。
- 字段白名单避免默认暴露 Prompt、模型响应、代码和 Diff。

### 负面

- SQLite 轮询不适合大规模公网 fan-out。
- 共享令牌不能提供真正的个人身份或精细审计。
- Gradio 与自定义 ASGI 路由需要统一生命周期和路径测试。
- 投影存在短暂滞后，需要启动和按需 reconciliation。

### 中性

- observer ID 只代表一次服务端会话，不是可授权账号。
- presence 是短期协作信息，不进入 LangGraph 状态或 Day17 审计链。
- 后续若规模或身份要求提高，可以替换读取/分发层，但不能改变 checkpoint 权威边界。

## 考虑过的替代方案

### 客户端轮询 checkpoint 快照

实现最少，但无法提供严格游标、可靠补发和有界事件历史；频繁读取完整 checkpoint 也扩大敏感字段暴露风险。

### 独立观察服务直接读取 SQLite

进程隔离更强，但需要协调数据库生命周期、认证配置和投影版本，Day18 的运维复杂度过高。

### Redis Streams 或消息队列

具备成熟 fan-out 和 consumer cursor，但引入额外服务与失败模式。当前局域网小团队规模没有证据支持该成本。

### WebSocket 双向通道

能实现实时双向协作，但会自然形成命令入口并扩大远程变更风险。Day18 仅需要服务器到浏览器的只读流。

### 直接流式转发 LangGraph 执行

无法可靠支持重启和断线续传，也可能让每个客户端绑定或触发一次执行，违反唯一执行要求。

## 安全与运行边界

- SSE、快照和导出只读取字段白名单化投影。
- 不持久化或返回查询正文、Prompt、模型响应、代码、Diff、环境值、密钥和绝对路径。
- 共享令牌不进入 URL、日志、事件或导出。
- 远程接口不持有 `WorkflowRuntime`、ApprovalTool、GitAgent 或文件工具引用。
- checkpoint 与观察投影不一致时，以 checkpoint 为准。
- push、merge、remote approve/reject/cancel/retry/continue 均不在 Day18 权限面。

## 参考

- `docs/plans/2026-08-20-day18-team-observation-design.md`
- `docs/plans/2026-08-20-day18-team-observation.md`
- `docs/adr/0005-langgraph-human-approval.md`
- `docs/adr/0006-safe-local-git-agent.md`
- `C:/Users/admin/memory/projects/ai-coding-agent.md`
