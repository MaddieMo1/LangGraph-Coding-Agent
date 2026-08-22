# Day19：隔离 Unity Worker 与双模式验证

状态：实现、离线验收和真实 HTTPS Worker 验收已完成；控制器上的独立本机 Worker 模式仍待单独验收。本文把可在仓库内复现的证据、真实本地 Unity 证据和真实远程 Worker 证据分开记录；未运行的探针必须保持 `PENDING`，不能由 fixture、loopback 测试或远程 Worker 内部的本机执行替代。

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
- Day19 专项：2026-08-22 执行计划列出的 11 个测试模块，76 项通过，耗时 1.688 秒。
- 完整 Python 回归：2026-08-22 执行 `python -m unittest discover -s tests -p "test_*.py"`，573 项通过，耗时 23.560 秒；运行中存在既有 asyncio 资源告警和 `httpx2` 弃用告警，但没有测试失败。
- `python -m compileall agents tools worker workflow memory ui tests` 与 `git diff --check` 通过。
- 提交差异凭据/路径审计只命中示例占位值、固定测试 fixture、脱敏负例和既有默认 Unity 路径，没有发现实际凭据。
- fixture 只证明契约、拒绝路径和状态机逻辑，不证明真实 Unity、真实 HTTPS 链路或强制网络隔离。

### 本地 Unity 证据

- 状态：PENDING。
- 环境预检：控制器上的 Unity Editor 可执行文件、Unity 测试工程和生成代码 Git 仓库均通过；独立本机 Worker 模式尚未运行完整验收。远程主机内部虽然使用相同的本机执行器，但不替代这一项。
- Unity 2022.3 版本：PENDING。
- compile 结果：PENDING。
- EditMode 通过/总数：PENDING。
- PlayMode 通过/总数：PENDING。
- Reviewer 结果：PENDING。
- sandbox 清理：PENDING。
- 源工程前后指纹：PENDING。
- 生成代码仓库分支与本地 commit：PENDING。

### 真实远程 Worker 证据

- 状态：PASSED（2026-08-22，在局域网独立主机上通过真实 HTTPS 链路完成）。
- 独立环境：控制器 `172.16.10.36`，Worker `172.16.10.71`；Worker 标识 `unity-worker-172-16-10-71`，Unity `2022.3.62f2c1`。
- HTTPS 与认证：Worker 使用本地 CA 签发的 RSA 3072 位证书，控制器显式信任该 CA；所有请求经时间戳、nonce、请求体摘要和专用凭据 HMAC 签名。真实陈旧签名请求返回 HTTP 401 与稳定错误码 `REQUEST_STALE`。
- 网络隔离：Worker 的 Public 防火墙配置为允许来自控制器的局域网通信和 TCP 8443，并阻断非局域网 IPv4 与全部 IPv6 出站。启用后 `ping 172.16.10.36` 成功，而对 `example.com:443` 和 `www.microsoft.com:443` 的直连均失败；能力端点报告 `network_isolation_enforced=true`。
- 固定快照：34 个文件，81,209 字节；快照 SHA-256 `529f7f4bc7e3b098b098207f6ed15119ec2ebd67ea6d523b8767c1e87e704add`，归档 SHA-256 `4b2ed955e75a68939525d92622654c5b86875a7455dc216d38146fc97cdb6485`。源工程构建前后指纹均为 `bad0eacb93ce00ba5ec3f4c0414ef11cb5bd0ab7495e00703cf4b4913fad1d6f`。
- 有序门禁：compile 作业 `4fe23603...18bc6`、EditMode 作业 `8b52f602...f5134`、PlayMode 作业 `f4c00c94...45e6b` 依次完成，时间区间没有交叠。compile 通过；EditMode 1/1 通过；PlayMode 1/1 通过。
- 结果摘要：compile `c327d7e69e314929bbf5798ca2247af8ba9217e51dfb8f0e538f78049fcc4da1`，EditMode `9ab8ccb254612d664492ef29e571453782230f9dc290e41805126c757d270dda`，PlayMode `e75104f87867eef282e4db8f852a0411bb87fc012931c83ab7ced88b4a8df94f`；三个作业均报告进程停止和沙箱删除成功。
- 幂等取消：作业 `78cbfe02...c841e` 从 running 转为 cancelled；首次和重复取消均成功，错误码为 `WORKER_CANCELLED`，进程停止与沙箱删除均为 true。
- 证据产物：热修复后的真实 compile 作业 `72456a22...42f26` 通过，下载 `unity-evidence.json`（116 字节）；Worker 声明值与控制器下载值的 SHA-256 均为 `584ca2c93af6379b0234fae434d975ac7daf28763688eab69b44715114af4af5`，结果 SHA-256 为 `8c9a2e0539e71e474262ca4d2026626d4b3a0fd9dd8e5f351aa793922cc6780b`，清理状态均为 true。

### Reviewer 与本地 Git 证据

- Reviewer 对已通过三项 Unity 门禁的批准内容给出 100 分，`pass=true`，没有根因或剩余问题。
- 生成代码在隔离仓库分支 `agent/day19accept` 上完成路径限定提交；基线提交为 `b8af2294aa362308e2035cefdfbb8c8d2d3aa81a`，验收提交为 `a60cc48e1b1ae69f6a676d039efebe8e12a77129`，提交后工作区干净。
- 获批文件 `Day19AcceptanceProbe.cs` 的内容 SHA-256 为 `c542a56efa373e21c83c91ac61360518c0199b4f8c5ff2c0650f79c13802c75a`。

## 已知限制

- 当前远程身份是预共享凭据，不是多租户账号、OIDC 或细粒度授权系统。
- Worker 元数据存储适合单 Worker 服务；没有实现集群调度、弹性伸缩或跨节点租约。
- `UNITY_WORKER_NETWORK_ISOLATION_ENFORCED=true` 只是能力声明，必须由部署环境的防火墙、容器或虚拟机策略提供实际证据。
