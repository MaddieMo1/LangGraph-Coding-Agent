# Day13 Multi-Model Router Design

## 目标

Day13 在不增加 Agent 数量、不改变现有审批、验证和 Git 安全边界的前提下，为 Architecture、File Planner、Coder、Test Generator、Reviewer 和 Repair 提供可解释、可回退、可持久化的多模型路由。

路由采用“角色 + 确定性复杂度规则”。用户不能在单次任务中手动指定模型；UI 只展示自动选择结果。全局模型映射可由环境配置覆盖，从而保证同一配置下的路由可复现，并为 Day14 Evaluation 提供可比较的数据。

## 已确认约束

- 可用 Provider：DeepSeek、Kimi、通义千问、智谱 GLM。
- Tavily 是搜索服务，不进入 Day13 模型路由。
- 不新增 Router Agent，也不让 LLM 决定使用哪个模型。
- 主模型发生可恢复调用失败时，允许自动切换到另一家 Provider。
- 每次调用最多使用一个主 Provider 和一个备用 Provider，不循环回退。
- 结构化输出不合法时，先在当前模型追加格式纠正提示重试一次；仍不合法再切换备用 Provider。
- UI 第一版只展示路由结果，不提供逐任务模型选择控件。
- `.env` 中的 Key 不进入 LangGraph state、日志或 UI。

## 非目标

- 增加新的业务 Agent 或改变现有 LangGraph 拓扑。
- 模型投票、并行生成、自动 A/B 测试或基于模型的路由决策。
- 在线价格发现、动态模型列表同步或自动挑选新发布模型。
- Tavily/Unity API 知识检索。
- Day14 的基准评分、成本对比和 `evaluation_report.md`。
- 修改人工审批、文件边界、Unity 门禁或 Git Agent 的权限。

## 方案选择

### 采用：角色 + 确定性复杂度规则

每个 LLM 工作负载先按角色获得候选模型，再由纯函数复杂度评估器读取有限的 `AgentState` 事实，得到 `simple`、`standard` 或 `complex`。路由表返回主模型和跨 Provider 备用模型。

优点：可解释、可单元测试、可复现；不产生额外模型调用；与项目现有“薄编排层 + 确定性工具”的架构一致。代价是规则需要随着 Day14 的评估结果迭代。

### 未采用：仅按角色固定模型

实现最简单，但无法把单文件、小影响范围任务交给快速模型，也不能满足路线图中的“小模型处理简单任务”。

### 未采用：让 LLM 动态选择模型

它会增加一次调用、成本和新的失败点，选择理由也难以稳定复现，与“不增加 Agent”和确定性约束冲突。

## 高层架构

```text
Agent node
  │ role + prompt + bounded AgentState + optional response validator
  ▼
ModelRouter
  ├── ComplexityAssessor  ──> simple / standard / complex + reasons
  ├── RouteTable          ──> primary route + fallback route
  └── InvocationPolicy
        ├── transport retry
        ├── format-correction retry
        └── one cross-provider fallback
  ▼
Provider adapters (OpenAI-compatible ChatOpenAI clients)
  ├── DeepSeek
  ├── Kimi
  ├── Qwen
  └── GLM
  ▼
ModelInvocationResult
  ├── content
  ├── selected route
  ├── attempts and fallback evidence
  └── usage/latency metadata
```

`ModelRouter` 是普通 Python 服务，不是 LangGraph 节点。现有 Agent 仍负责构建 Prompt、解析领域输出和更新业务状态。Router 只负责选择、调用、有限重试、回退和生成审计记录。

## 组件设计

### ProviderConfig 与 Provider Adapter

增加统一的 Provider 配置和 OpenAI-compatible 适配器。每个 Provider 只读取自己的 API Key、Base URL 和模型名，并实现相同的 `invoke(prompt)` 接口。适配器不记录 Prompt、Key 或完整原始响应。

建议的环境变量：

- `DEEPSEEK_API_KEY`、`KIMI_API_KEY`、`QWEN_API_KEY`、`GLM_API_KEY`
- 可选的 `<PROVIDER>_BASE_URL`
- 可选的 Day13 角色模型覆盖项；未设置时使用版本化默认路由表

启动时只验证路由表实际引用的 Provider。某个备用 Provider 未配置时，该 Route 标记为不可用，但不会影响完全不引用它的任务。主、备均不可用时，工作流以结构化配置错误结束。

### ComplexityAssessor

复杂度评估器是无网络、无文件写入的纯函数，输入仅为角色和当前状态的有限字段，输出：

```json
{
  "level": "standard",
  "reasons": ["planned_files=2", "dependency_impact=3"]
}
```

第一版规则：

| 角色 | Simple | Standard | Complex |
|---|---|---|---|
| Architecture | 查询命中一个已有类型，影响范围不超过 1，且不是重新规划 | 默认首次设计 | 架构回流，或命中类型的依赖影响范围不少于 6 |
| File Planner | 单一已有类型、影响范围不超过 1 | 默认规划 | 依赖影响范围不少于 6，或架构回流后的重新规划 |
| Coder | 仅 1 个计划文件，且影响范围不超过 1 | 2–3 个文件，或一般依赖改动 | 至少 4 个文件，或依赖影响范围不少于 6 |
| Test Generator | 仅 1 个生产文件且无既有失败证据 | 2–3 个生产文件 | 至少 4 个文件，或已有编译/测试失败证据 |
| Reviewer | 编译和测试均通过、代码不超过 1 个文件、无修复历史 | 验证通过的一般审查，或少量失败证据 | 编译错误不少于 3、测试失败不少于 2、代码不少于 4 个文件，或修复轮次不少于 2 |
| Repair | 不使用 simple；确定性的 `add_using` 继续由 Repair Tool 处理，不调用模型 | 第一轮、单目标且错误少于 3 | 修复轮次不少于 2、多目标、编译错误不少于 3或测试失败不少于 2 |

“查询命中类型”只把查询文本与 `project_context` 中的项目内类型名做规范化精确匹配；“依赖影响范围”只使用现有 dependency graph 的反向/传递查询结果。不使用模糊语义模型或不可复现的 Prompt 长度猜测。

规则采用“任一 complex 条件优先，其次 standard，否则 simple”。无法取得信号时使用该角色的 standard，不猜测为 simple。

### RouteTable

第一版默认路由如下：

| 角色与档位 | 主模型 | 备用模型 |
|---|---|---|
| Architecture / complex | DeepSeek `deepseek-v4-pro` | Kimi `kimi-k2.5` |
| Architecture / simple, standard | DeepSeek `deepseek-v4-flash` | GLM `glm-5.2` |
| File Planner / complex | Kimi `kimi-k2.5` | DeepSeek `deepseek-v4-pro` |
| File Planner / simple, standard | DeepSeek `deepseek-v4-flash` | Qwen `qwen3.7-flash` |
| Coder / standard, complex | Kimi `kimi-k2.7-code` | Qwen `qwen3-coder-plus` |
| Coder / simple | DeepSeek `deepseek-v4-flash` | Qwen `qwen3.7-flash` |
| Test Generator / all | Kimi `kimi-k2.7-code-highspeed` | Qwen `qwen3-coder-plus` |
| Reviewer / complex | GLM `glm-5.2` | DeepSeek `deepseek-v4-pro` |
| Reviewer / simple, standard | DeepSeek `deepseek-v4-flash` | GLM `glm-4.5-air` |
| Repair / standard, complex | Kimi `kimi-k2.7-code` | Qwen `qwen3-coder-plus` |

不同 Provider 的备用模型用于减少单一服务故障的相关性。模型名是版本化默认值，允许部署者通过环境变量全局覆盖；覆盖后应在启动日志中只显示 Provider 和模型名，不显示凭据。

### InvocationPolicy

调用按错误类别执行固定策略：

```text
主模型调用
  ├── 成功且格式有效 ──> 返回
  ├── 格式无效 ──> 同模型追加纠正提示重试 1 次
  │                    ├── 有效 ──> 返回
  │                    └── 无效 ──> 切换备用 Provider
  └── 可恢复传输错误 ──> 同模型短重试后切换备用 Provider

备用模型调用
  ├── 成功且格式有效 ──> 返回
  ├── 格式无效 ──> 同模型追加纠正提示重试 1 次
  └── 仍失败 ──> 结构化终止当前节点
```

- 主、备各最多 2 次实际请求：首次请求加一次传输重试，或首次请求加一次格式纠正请求；单个 Route 不超过 4 次实际请求。
- 超时、限流、连接中断和 Provider 5xx 属于可恢复传输错误。
- 认证失败、无效模型名和缺少配置不在同一 Provider 重试，直接尝试备用 Provider。
- 内容安全拒绝或请求本身非法不通过重复重试绕过；只有备用模型在同一合法 Prompt 下可尝试一次。
- 备用失败后抛出包含安全摘要的 `ModelRouteError`，由当前节点记录失败，不能宣称业务完成。

格式校验回调由 Agent 提供：File Planner、Test Generator、Reviewer 和 Repair 使用现有 JSON/结构解析规则；Coder 校验能否提取非空 C# 内容；Architecture 只要求非空文本。纠正提示只包含原 Prompt、格式错误摘要和输出契约，不包含其他 Provider 的原始响应。

## 状态协议与可观测性

在 `AgentState` 中新增：

```text
model_route                 当前节点最近一次成功或最终失败的路由摘要
model_routing_history       本任务的有界调用记录
model_usage                 按 provider/model 聚合的请求、输入/输出 token 与耗时
model_error                 当前模型调用的结构化最终错误
```

单次记录建议包含：

```json
{
  "role": "coder",
  "complexity": "standard",
  "reasons": ["planned_files=2"],
  "provider": "kimi",
  "model": "kimi-k2.7-code",
  "route": "primary",
  "attempts": 1,
  "fallback_used": false,
  "format_retry_used": false,
  "status": "success",
  "latency_ms": 1820,
  "input_tokens": 0,
  "output_tokens": 0,
  "error_code": ""
}
```

Provider 未返回 usage 时 token 字段保留为 0，并通过 `usage_available: false` 区分“未知”和真实的零。历史记录设置固定上限，建议 100 条；超出时保留最近记录，聚合值继续累计。Coder 多文件生成的每次模型调用分别记录，便于 Day14 计算真实调用次数。

不得持久化 API Key、Authorization header、完整 Prompt 或完整原始响应。错误只保存分类、Provider 请求 ID（若安全可用）和去敏后的短消息。

## Agent 集成

现有 `AgentWorkflow` 不再创建并共享单个 `DeepSeekLLM`，而是创建一个 `ModelRouter`。六个使用模型的 Agent 注入同一个 Router，并在调用时传入固定角色：

- `architecture`
- `file_planner`
- `coder`
- `test_generator`
- `reviewer`
- `repair`

Coordinator、Project Understanding、Code Checker、Unity Compiler、Unity Test、审批工具、Git Agent 和 Memory 保持确定性，不接入模型路由。`ArchitectureValidator` 当前未调用模型，继续保持确定性校验，不因构造函数中的可选 `llm` 参数而接入 Router。

每个 Agent 在原有业务返回值上追加路由记录，不改变现有 `current_agent`、提案、审批和验证字段。路由失败时不得产生半成品生产变更；Coder/Repair 仍只形成提案，写入继续受 Day11 审批边界保护。

## UI

Day13 第一版只读展示：

- 当前/最近模型：Provider、模型、复杂度与主/备身份。
- 选择原因：使用短标签，例如“计划文件 4 个”“第 2 轮修复”。
- 回退状态：是否发生格式纠正、是否跨 Provider、最终错误类别。
- 任务详情：累计调用次数、可用时的 token 与总耗时。

UI 不展示 Prompt、响应正文、Key、Base URL，也不提供模型下拉框。历史任务从 SQLite checkpoint 读取其当时的实际路由记录，而不是按当前配置重新推断。

## 配置与启动行为

默认路由表进入版本控制；`.env.example` 只列变量名和示例占位符。启动时执行只读配置校验：

1. 路由表中的主、备 Provider 名称合法。
2. 主、备不是同一 Provider。
3. 每条路由均有非空模型名。
4. 至少一条可用路径存在；完全不可用的角色在启动时明确报错。
5. 不进行付费探测调用；真实可用性由聚焦验收测试确认。

为了保持改动最小，Day13 不引入 YAML、数据库配置表或远程配置服务。

## 失败模式与处理

| 失败 | 行为 |
|---|---|
| 主 Provider 超时/限流/5xx | 短重试一次；仍失败则跨 Provider 回退 |
| 主 Provider Key/模型配置错误 | 不原地重试，直接尝试备用 Provider |
| 输出格式错误 | 当前模型纠正一次；仍失败则回退 |
| 主备都不可用 | 当前节点结构化失败，保留检查点和既有安全状态 |
| usage 缺失 | 内容仍可使用，标记 `usage_available=false` |
| 路由记录写入失败 | 不能影响已获得的模型内容；记录系统警告供诊断 |
| 旧 checkpoint 无 Day13 字段 | 使用空默认值恢复，保持 Day11/Day12 任务兼容 |
| 配置在任务中途改变 | 已持久化历史不改写；下一次模型调用使用进程启动时的配置快照 |

## 测试与验收

### 单元测试

- 每个角色、每个边界条件产生正确复杂度与原因。
- 路由表选择正确的主模型和不同 Provider 的备用模型。
- 超时、429、5xx、认证错误和无效模型分别遵循固定策略。
- JSON/代码格式错误先在当前模型纠正一次，再回退。
- 主备均失败时产生结构化错误且不泄露 Key/Prompt。
- 路由历史有界、usage 聚合正确，缺少 usage 时语义明确。
- 环境覆盖只影响指定路由，非法配置启动失败。

### 工作流回归

- Fake Provider 证明六个 LLM 角色分别经过 Router。
- 简单单文件任务使用快速档；多文件任务使用代码模型。
- Reviewer 与 Coder 默认来自不同模型族。
- 第二轮 Repair 强制进入 complex。
- 回退后工作流仍沿用原 thread、审批记录和 Git 分支。
- 模型全部失败不会进入审批、验证成功或 Git 提交状态。
- Day11、Day12 旧 checkpoint 可恢复。

### 集成验收

- 对四家 Provider 各执行一次最小真实调用，不打印 Key。
- 执行一个简单任务，确认 `deepseek-v4-flash` 快速档被选择。
- 执行一个多文件编码任务，确认 Kimi Code 主模型被选择。
- 使用 Fake Provider 注入主模型失败，证明只跨 Provider 回退一次。
- 完整 Python 测试、`compileall`、`git diff --check` 和 Day13 no-LLM notebook 全部通过。
- 使用真实 Unity 项目完成至少一次生成、审批、编译、测试、Review 和本地 Git 提交闭环。

## 实施边界

建议最小新增模块：

- `llm/provider.py`：统一 Provider 配置、客户端与错误分类。
- `llm/model_router.py`：复杂度评估、路由表、调用策略和记录。
- `tests/test_model_router.py`：纯单元测试。
- `tests/test_day13_workflow.py`：工作流路由与回退测试。
- `day13/Day13.ipynb`：无 Key、可复现的 Fake Provider 验收教程。

修改范围限制在六个 LLM Agent、`workflow/graph.py`、`memory/state.py`、UI 的只读展示、`.env.example`、README 和相关测试。不得顺带重构现有工作流或 Provider 无关代码。

## Day13 完成定义

只有同时满足以下条件才能将路线图更新为 Day13 完成：

1. 六个现有 LLM 工作负载全部经过确定性 Router，且未增加 Agent。
2. 角色和复杂度路由、格式纠正、跨 Provider 单次回退均有自动化测试。
3. 路由决策和 usage 元数据持久化并在 UI 只读可见。
4. 所有旧工作流回归通过，审批、Unity 验证和 Git 安全边界不变。
5. 四家 Provider 的最小真实调用与至少一个真实 Unity 全链路验收通过。
6. 不在代码、日志、状态、Notebook 或文档中泄露任何 API Key。
