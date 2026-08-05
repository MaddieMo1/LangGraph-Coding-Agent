# Contributing Guide

感谢你参与 **LangGraph Coding Agent**。本项目使用 LangGraph、LangChain、DeepSeek 和 Unity Compiler 探索多 Agent 软件工程工作流。

欢迎提交 Bug 修复、Agent 或 Tool 能力、Workflow 路由、Prompt 稳定性、测试和文档改进。

## 开发流程

1. Fork 仓库并从最新 `main` 创建分支。
2. 使用与改动类型匹配的分支名：

```text
feature/xxx
fix/xxx
refactor/xxx
docs/xxx
```

3. 保持改动范围单一，避免在同一 PR 中混入无关重构。
4. 完成与风险相匹配的验证。
5. 在 PR 中说明改动、原因、测试结果和已知限制。

## 架构约束

- Agent 负责编排、判断和状态更新。
- Tool 封装文件、编译器或其他外部能力。
- Prompt 集中放在 `prompts/`。
- 共享字段集中定义在 `memory/state.py`。
- Router 应根据可验证状态路由，不应只依赖模型评分。
- 环境错误与代码错误必须使用不同状态表示。

当前核心闭环：

```text
Code Checker
→ Unity Compiler
→ Reviewer
→ Repair
→ Code Checker
```

## 新增或修改 Agent

Agent 应具有清晰的输入、输出和状态变化：

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

- `workflow/graph.py` 中的 Node 和 Edge。
- 条件路由的所有返回值都有对应映射。
- State 中使用的字段已定义且具有稳定类型。
- 循环有明确的重试或修复次数上限。

## Tool 开发

Tool 位于 `tools/`，应满足：

- 单一职责。
- 输入输出明确。
- 不包含 Agent 调度逻辑。
- 可独立测试。
- 文件写入范围受控。
- 外部进程提供超时和结构化错误。

## Prompt 与 Reviewer

- 结构化输出必须明确 JSON Schema 或示例。
- Compiler 结果是编译状态的权威来源。
- Unity 编译成功后，Reviewer 不得虚构 `compile_error` 或 `CSxxxx` 错误。
- Reviewer JSON 无效时必须进入有限重试，不能误判为成功。
- `pass=true` 必须与分数、剩余问题和工具结果一致。

## State 管理

新增字段时请说明用途、类型、写入方和读取方。历史字段应追加记录，不应覆盖前一轮结果。

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

## 测试要求

提交前至少完成：

1. Python 语法检查。
2. Workflow 可以初始化和编译。
3. Router 覆盖严格通过、编译失败、Reviewer 重试和系统错误。
4. 若修改 Unity Compiler，使用独立 Unity 工程执行真实 BatchMode 编译。
5. 若修改 Reviewer/Repair 闭环，验证以下过程：

```text
真实编译失败
→ Reviewer 提取 Root Cause
→ Repair 成功写入
→ 再次编译成功
→ Reviewer score >= 90
→ pass = true
→ remaining_issues = []
→ finish_task
```

测试结束后必须清理临时脚本，并确认恢复后的原代码仍能编译。

## Commit 规范

推荐格式：

```text
feat: 添加功能
fix: 修复问题
refactor: 重构模块
docs: 更新文档
test: 增加测试
chore: 工程维护
```

提交应保持可审查，并避免包含 `.env`、API Key、生成代码或大型日志。

## Pull Request

PR 描述请包含：

- 修改内容和原因。
- 关键设计选择。
- 修改过的 Agent、Tool、State 和 Router。
- 执行过的测试及结果。
- 环境依赖和已知限制。

对于 Unity 编译相关 PR，请注明 Unity 版本、测试工程路径配置方式，以及编译是否为真实 BatchMode 结果。

## License

提交贡献即表示你同意贡献内容按照项目的 [MIT License](./LICENSE) 发布。
