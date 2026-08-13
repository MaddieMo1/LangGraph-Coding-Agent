# ADR 0007：确定性的多模型路由与跨 Provider 回退

- 状态：Accepted
- 日期：2026-08-13

## 背景

截至 Day12，Architecture、File Planner、Coder、Test Generator、Reviewer 和 Repair 共用一个 `DeepSeekLLM` 实例。单模型结构无法按工作负载选择更合适的推理、代码或快速模型；同一 Provider 故障也会阻断所有 LLM 节点。Day13 需要引入多模型能力，但项目战略明确要求不继续增加 Agent，并优先保证确定性、安全性和可验证性。

当前环境已验证 DeepSeek、Kimi、通义千问和智谱 GLM API 可用。Tavily 是搜索 API，不属于模型 Provider。

## 决策

引入普通 Python 服务 `ModelRouter`，不新增 LangGraph 节点或 Agent。每次模型调用由固定角色与纯函数复杂度评估器共同决定 `simple`、`standard` 或 `complex`，再从版本化路由表选择主模型和不同 Provider 的备用模型。

默认角色分工为：DeepSeek Pro 负责复杂架构，DeepSeek Flash 负责快速档和一般规划/复核，Kimi 长上下文模型负责复杂文件规划，Kimi Code 负责编码、测试生成和修复，GLM 负责复杂独立 Review，Qwen 作为主要代码及快速跨 Provider 备用。

主 Provider 发生可恢复调用错误时允许跨 Provider 回退一次。结构化输出格式错误时，先在当前模型追加输出契约纠正提示重试一次；仍失败后才切换备用 Provider。主备均失败时当前节点结构化失败，不循环切换，也不绕过现有审批和验证门禁。

Router 为每次调用返回内容和安全的路由元数据。角色、复杂度、选择原因、Provider、模型、主备身份、重试、回退、耗时和可用的 usage 数据写入 LangGraph 状态；API Key、完整 Prompt 和完整原始响应不得持久化。UI 只读展示结果，不允许用户逐任务手动指定模型。模型映射只能通过进程启动时读取的全局配置覆盖。

## 结果

### 正面

- 不增加 Agent 即可按架构、编码、评审和简单任务选择合适模型。
- 路由完全由可测试规则决定，不需要额外的路由模型调用。
- Reviewer 与 Coder 默认使用不同模型族，降低同源偏差。
- 单一 Provider 故障可通过一次受限回退恢复。
- 路由记录可直接支持 Day14 的成功率、延迟、token 和稳定性评估。
- 现有人工审批、Unity 门禁和本地 Git 安全边界保持不变。

### 负面

- 需要维护四家 Provider 的兼容配置和错误分类。
- 确定性规则可能不能立即得到全局最优的成本/质量组合。
- 多 Provider 会增加配置、真实验收和故障诊断的工作量。
- 不同 Provider 的 token usage 元数据可能不完整或口径不一致。

### 中性

- 模型路由表会随 Day14 的实测结果调整，但旧任务保留当时的实际选择记录。
- Provider 和模型可全局覆盖，但同一进程内使用启动时的配置快照。

## 考虑过的替代方案

### 所有 Agent 固定使用单一模型

改动最少，但没有角色专业化、快速档或 Provider 容灾，无法满足 Day13 目标。

### 每个角色固定一个模型

具备角色专业化，但简单任务仍承担高模型成本，且无法根据修复轮次和失败证据升级能力档位。

### 使用 LLM Router 动态选模

灵活但增加调用成本、延迟和新的故障点，选择结果难以复现，也与不增加 Agent 的约束冲突。

### 并行调用多个模型后投票

可能提高部分任务质量，但成本和延迟显著增加，结果合并也需要新的判断机制。它超出 Day13 最小范围，可在 Day14 有测量证据后重新评估。

## 安全与运行边界

- Router 不读取或写入生产代码，不执行 Shell/Git 命令。
- 只允许路由表中声明的 Provider、模型和备用关系。
- 主备必须属于不同 Provider；每次调用最多一次跨 Provider 回退。
- 认证、Key、Authorization header、完整 Prompt 和原始响应不进入日志、状态或 UI。
- 内容安全拒绝不得通过无限重试或模型轮换规避。
- 模型失败不能被解释为 Reviewer、Unity 验证或 Git 提交成功。

## 参考

- `docs/plans/2026-08-13-day13-multi-model-router-design.md`
- `docs/adr/0006-safe-local-git-agent.md`
- `C:/Users/admin/memory/projects/ai-coding-agent.md`
