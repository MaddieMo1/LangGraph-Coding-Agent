# Day18：团队只读任务观察

Day18 在现有 Gradio 应用外层组合一个 FastAPI 服务：根路径继续承载本地控制面，`/observe` 提供只读 JSON/SSE 接口，`/observe/ui` 提供局域网浏览器观察页。没有增加第二个工作流进程，也没有改变 checkpoint、人工审批或本地 Git 的所有权。

## 架构与一致性

- LangGraph SQLite checkpoint 是任务状态的唯一权威来源。
- 每次 checkpoint 成功持久化后，确定性投影器才生成脱敏快照和事件；投影异常只记录警告，不改变工作流结果。
- 派生数据与 checkpoint 位于同一 SQLite 文件的独立表中，访问时使用独立、短生命周期连接，避免共享连接所有权。
- 服务启动或按需读取时可以从 checkpoint 只读重建缺失投影，不会恢复、推进或重新执行工作流。
- 事件使用全局单调游标。SSE 优先读取 `Last-Event-ID`，页面重载可使用 `after_cursor`；游标过旧或快照代际变化时发送重置信号。

## 只读安全边界

启用观察面需要 32～256 字符的共享读取令牌。令牌只提交给 `POST /observe/session`，验证成功后换取不透明、`HttpOnly`、`SameSite=Strict` Cookie；令牌不会进入 URL、浏览器持久存储或应用日志。非回环 HTTP 默认拒绝启动，推荐配置 TLS；`OBSERVATION_ALLOW_INSECURE_HTTP=true` 只是显式风险确认，不提供加密。

远程契约采用字段白名单，只允许任务 ID、有限标题、阶段、状态、质量门结果、有限错误摘要、模型路由元数据、提交哈希和产物文件名。它会清理密钥样式文本、绝对路径和敏感错误细节，并排除源码、完整 Diff、Prompt、模型响应、环境变量与凭据。

观察应用没有批准、拒绝、继续、重试、取消、归档、Git 或文件写入路由。共享令牌不是账号系统，也不提供每人独立授权；需要撤销访问时必须轮换令牌并重启服务。

即使服务为观察面绑定 `0.0.0.0`，非回环来源也只能进入 `/observe`。控制面根路径、API 文档和 Gradio 控制路由由 ASGI 中间件统一拒绝，HTTP 返回 403，WebSocket 以策略违规关闭；该判断不信任客户端可伪造的转发头。

## 运行配置

```env
OBSERVATION_ENABLED=true
OBSERVATION_READ_TOKEN=replace-with-a-random-token-at-least-32-characters
OBSERVATION_SERVER_NAME=0.0.0.0
OBSERVATION_SERVER_PORT=7860
OBSERVATION_TLS_CERTFILE=D:\path\to\tls\certificate.pem
OBSERVATION_TLS_KEYFILE=D:\path\to\tls\private-key.pem
OBSERVATION_ALLOW_INSECURE_HTTP=false
```

运行 `python app.py` 后，本地操作者使用根路径，团队观察者使用 `/observe/ui`。观察者名称可选，身份由服务端生成；20 秒心跳维持在线状态，60 秒无心跳标记离线。事件默认保留 7 天，并限制每个项目最多 5000 条。

## 验证证据

- Day18 专项覆盖契约、脱敏、SQLite 存储、确定性投影、Runtime 接入、会话、只读 API、SSE 续传、游标重置、在线状态与多观察者隔离。
- 端到端测试验证两个观察者同时读取同一任务，其中一个断线后从原游标续传，不重复也不漏掉事件。
- `day18/Day18.ipynb` 已离线执行 5 个代码单元，0 个错误。
- Microsoft Edge 通过本机 LAN 地址完成页面登录：令牌输入被清空，任务状态、门禁、所有者、观察者和 SSE 游标正确显示，页面无变更按钮或错误覆盖层；同一地址访问控制面根路径返回 403。
- 2026-08-21 使用同一局域网内的手机完成真实第二设备验收：观察页成功连接并显示“已连接 · 只读”、任务列表与任务状态；访问控制面根路径被拒绝并提示仅限 localhost。
- 完整回归：`python -m unittest discover -s tests -q`，489 项测试通过，耗时 22.628 秒。
- `python -m compileall -q .` 与 `git diff --check` 通过。

## 已知限制

- 共享令牌适合受信任的小型局域网团队，不等同于账号、SSO、细粒度权限或完整审计身份。
- SQLite 派生事件存储适合单机服务与小规模观察者，不面向多节点水平扩展。
- 自动化测试覆盖多观察者和断线续传；浏览器探针只验证本机/LAN 地址的只读页面，不替代真实第二台设备、反向代理或证书链验收。
- 未配置 TLS 时，局域网 HTTP 会暴露会话和观察内容给同网段窃听风险，只能在明确接受风险的临时环境使用。
