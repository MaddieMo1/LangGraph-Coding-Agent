# Day19：隔离 Unity Worker 与双模式验证

状态：实现与离线验收进行中。本文把可在仓库内复现的证据、真实本地 Unity 证据和真实远程 Worker 证据分开记录；未运行的探针必须保持 `PENDING`，不能由 fixture 或 loopback 测试替代。

## 实现范围

- 控制器构建只包含白名单输入的不可变 `.unityjob` 快照，并固定 Unity 版本、Package manifest、文件与归档 SHA-256。
- Worker 只执行固定的 `compile`、`editmode`、`playmode` 门禁，工作流顺序为 `compile → EditMode → PlayMode → Reviewer → 本地 Git`。
- 本地模式通过固定参数启动独立 Python 子进程；远程模式使用固定 HTTPS 路由，不执行任意远程命令。
- 作业有超时、过期时间、尝试号和网络策略；结果绑定 job、thread、gate、attempt 与 snapshot，并校验产物大小和产物哈希。
- 控制台和 `/observe` 只投影 Worker 模式、脱敏 ID、门禁、状态、耗时、测试计数和稳定错误码。

## 安全边界

- 非回环远程地址必须使用 HTTPS；请求使用独立 32～256 字符凭据、时间戳、nonce、请求体摘要与 HMAC 签名。
- 服务端持久化 nonce 并拒绝重放、陈旧时间戳、超大请求、非法快照、跨作业访问和非白名单产物。
- 调用方不能提交可执行文件路径、任意命令、环境变量或任意下载 URL；不确定提交不会自动回退到本地或重复提交。
- 默认网络策略为 disabled，但只有独立环境真实强制网络隔离时才可宣称该门禁通过；配置字段本身不是隔离证据。
- 凭据、含认证信息的 URL、绝对路径、源码/测试正文、快照、完整日志、命令、环境值和 HMAC 材料不会进入远程观察快照或事件。

## 运行配置

```env
UNITY_WORKER_MODE=local
UNITY_WORKER_STATE_PATH=D:\path\to\runtime-state\unity-worker
UNITY_WORKER_TIMEOUT_SECONDS=900
UNITY_WORKER_RESULT_RETENTION_DAYS=7
UNITY_WORKER_NETWORK_MODE=disabled
UNITY_WORKER_NETWORK_ISOLATION_ENFORCED=false
UNITY_REMOTE_WORKER_URL=https://unity-worker.example.com
UNITY_REMOTE_WORKER_CREDENTIAL=replace-with-a-unique-32-to-256-character-secret
UNITY_REMOTE_WORKER_DATABASE=D:\path\to\runtime-state\unity-worker\remote-worker.sqlite
```

## 验收证据

### 离线证据

- Notebook：2026-08-21 使用 `nbconvert --execute` 离线执行 7 个代码单元，检查为 0 个 error outputs；生成的 executed 副本检查后已删除。
- Day19 发布契约测试：3 项通过；完整 Day19 专项测试数与耗时留待 Task 10 统一记录。
- 完整 Python 回归：PENDING — Task 10 执行并记录精确测试数与耗时。
- Python 编译与 `git diff --check`：PENDING。
- fixture 只证明契约、拒绝路径和状态机逻辑，不证明真实 Unity、真实 HTTPS 链路或强制网络隔离。

### 本地 Unity 证据

- 状态：PENDING。
- Unity 2022.3 版本：PENDING。
- compile 结果：PENDING。
- EditMode 通过/总数：PENDING。
- PlayMode 通过/总数：PENDING。
- Reviewer 结果：PENDING。
- sandbox 清理：PENDING。
- 源工程前后指纹：PENDING。
- 生成代码仓库分支与本地 commit：PENDING。

### 真实远程 Worker 证据

- 状态：PENDING（loopback FastAPI fixture 不算真实远程验收）。
- 独立主机/运行环境标识：PENDING。
- HTTPS 证书与请求签名验证：PENDING。
- 默认网络隔离强制证据：PENDING。
- 有序状态与幂等取消：PENDING。
- compile、EditMode、PlayMode 成功作业：PENDING。
- 结果与产物哈希：PENDING。
- 陈旧结果拒绝：PENDING。

## 已知限制

- 当前远程身份是预共享凭据，不是多租户账号、OIDC 或细粒度授权系统。
- Worker 元数据存储适合单 Worker 服务；没有实现集群调度、弹性伸缩或跨节点租约。
- `UNITY_WORKER_NETWORK_ISOLATION_ENFORCED=true` 只是能力声明，必须由部署环境的防火墙、容器或虚拟机策略提供实际证据。
