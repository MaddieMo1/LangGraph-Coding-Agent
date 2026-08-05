# 🤝 贡献指南

感谢你参与 **LangGraph Coding Agent**。本项目使用 LangGraph、LangChain、DeepSeek 和 Unity Compiler 探索多智能体软件工程工作流。

欢迎提交缺陷修复、智能体或工具能力、工作流路由、提示词稳定性、测试和文档改进。

> 🌱 **贡献原则**：保持改动范围清晰、状态变化可追踪、测试结果可复现。

## 🌿 开发流程

1. 复刻仓库，并从最新 `main` 创建分支。
2. 使用与改动类型匹配的分支名：

```text
feature/xxx
fix/xxx
refactor/xxx
docs/xxx
```

3. 保持改动范围单一，避免在同一个合并请求中混入无关重构。
4. 完成与改动风险相匹配的验证。
5. 在合并请求中说明改动内容、改动原因、测试结果和已知限制。

## 🏗️ 架构约束

- 智能体负责编排、判断和状态更新。
- 工具负责封装文件、编译器或其他外部能力。
- 提示词集中存放在 `prompts/`。
- 共享字段集中定义在 `memory/state.py`。
- 路由器应根据可验证状态进行路由，不能只依赖模型评分。
- 环境错误与代码错误必须使用不同状态表示。

当前核心闭环：

<p align="center">
  <img src="./assets/workflow.png" alt="LangGraph Coding Agent 工作流架构" width="850" />
</p>

```text
静态检查
→ Unity 编译
→ 代码审核
→ 代码修复
→ 静态检查
```

## 🤖 新增或修改智能体

智能体应具有清晰的输入、输出和状态变化：

```python
class ExampleAgent:
    def __init__(self, llm):
        self.llm = llm

    def run(self, state):
        return {
            "current_agent": "example"
        }
```

接入工作流时需要同步检查：

- `workflow/graph.py` 中的节点和边；
- 条件路由的所有返回值都有对应映射；
- 状态中使用的字段已定义且类型稳定；
- 循环有明确的重试或修复次数上限。

## 🧰 工具开发

工具位于 `tools/`，应满足：

- 职责单一；
- 输入输出明确；
- 不包含智能体调度逻辑；
- 可以独立测试；
- 文件写入范围受控；
- 外部进程具有超时设置和结构化错误结果。

## 🧠 提示词与代码审核

- 结构化输出必须提供明确的 JSON 结构或示例。
- 编译器结果是编译状态的权威来源。
- Unity 编译成功后，Reviewer 不得虚构 `compile_error` 或 `CSxxxx` 错误。
- Reviewer JSON 无效时必须进入有限重试，不能误判为成功。
- `pass=true` 必须与评分、剩余问题和工具结果一致。

## 🗃️ 状态管理

新增字段时请说明用途、类型、写入方和读取方。历史字段应追加记录，不能覆盖前一轮结果。

Day06-4 使用的主要字段包括：

```text
compile_result
compile_history
review
review_history
review_retry_count
root_causes
repair_count
repair_history
```

## 🧪 测试要求

提交前至少完成：

1. Python 语法检查；
2. 工作流可以正常初始化和编译；
3. 路由测试覆盖严格通过、编译失败、Reviewer 重试和系统错误；
4. 修改 Unity Compiler 时，必须使用独立 Unity 工程执行真实 BatchMode 编译；
5. 修改 Reviewer 或 Repair 闭环时，必须验证以下过程：

```text
真实编译失败
→ Reviewer 提取根因
→ Repair 成功写入
→ 再次编译成功
→ Reviewer score >= 90
→ pass = true
→ remaining_issues = []
→ finish_task
```

测试结束后必须清理临时脚本，并确认恢复后的原代码仍能编译。

<p align="center">
  <img src="./assets/demo_repair_log.png" alt="真实修复闭环运行日志" width="850" />
</p>

> ⚠️ **验收提醒**：`finish_task` 只表示工作流结束。只有 Checker、Compiler、Reviewer 和剩余问题字段同时满足通过条件，才能认定测试成功。

## 📦 提交规范

推荐格式：

```text
feat: 添加功能
fix: 修复问题
refactor: 重构模块
docs: 更新文档
test: 增加测试
chore: 工程维护
```

提交应保持便于审查，并避免包含 `.env`、接口密钥、生成代码或大型日志。

> 🔐 **安全要求**：提交前务必检查暂存内容，不要上传 API Key、个人环境配置、Unity 日志或临时生成文件。

## 🔀 合并请求

合并请求描述应包含：

- 修改内容和原因；
- 关键设计选择；
- 修改过的智能体、工具、状态和路由器；
- 执行过的测试及其结果；
- 环境依赖和已知限制。

对于 Unity 编译相关的合并请求，请注明 Unity 版本、测试工程路径的配置方式，以及编译是否为真实 BatchMode 结果。

## 📄 许可证

提交贡献即表示你同意贡献内容按照项目的 [MIT 许可证](./LICENSE)发布。
