# Day13 Multi-Model Router Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** 为六个现有 LLM 工作负载增加确定性的角色/复杂度路由、格式纠正、单次跨 Provider 回退、持久化审计和只读 UI 展示。

**Architecture:** 新增统一 OpenAI-compatible Provider 和 `ModelRouter`，由无副作用的复杂度评估器选择版本化主备路由。角色适配器保持现有 `invoke(prompt)` FakeLLM 测试兼容；支持路由的 Agent 额外传入 state/validator，并把安全记录合并进 LangGraph state。

**Tech Stack:** Python 3、LangChain `ChatOpenAI`、LangGraph TypedDict/SQLite checkpoint、Gradio、`unittest`。

---

> 当前仓库已有未提交 Day13 设计文档和用户的未跟踪 `generated/`。本计划在当前工作区执行，不创建提交、不推送、不改动 `generated/`。

### Task 1: Router 核心与纯单元测试

**Files:**
- Create: `llm/provider.py`
- Create: `llm/model_router.py`
- Create: `tests/test_model_router.py`

1. 先写 Fake Provider 测试，覆盖角色路由、复杂度边界、格式纠正、可恢复错误回退、配置错误直达备用、主备失败和敏感信息去除。
2. 运行 `python -m unittest tests.test_model_router -v`，确认测试因模块缺失失败。
3. 实现最小 Provider 配置、错误分类、路由表、复杂度评估和调用策略。
4. 重跑聚焦测试并要求通过。

### Task 2: Agent 兼容接入与状态协议

**Files:**
- Create: `llm/invocation.py`
- Modify: `agents/architecture.py`
- Modify: `agents/file_planner.py`
- Modify: `agents/coder.py`
- Modify: `agents/test_generator.py`
- Modify: `agents/reviewer.py`
- Modify: `agents/repair.py`
- Modify: `memory/state.py`
- Modify: `workflow/graph.py`
- Create: `tests/test_day13_workflow.py`

1. 写测试证明六个角色使用正确适配器、旧 FakeLLM 仍可用、Coder 多文件记录多次调用、第二轮 Repair 进入 complex。
2. 运行聚焦测试并确认失败。
3. 实现统一调用辅助函数和有界状态合并；将 AgentWorkflow 的单一 DeepSeek 实例替换为 Router 角色适配器。
4. 运行 Day13、Day09–Day12 和各 Agent 聚焦回归。

### Task 3: 只读 UI 与配置示例

**Files:**
- Modify: `ui/approval_app.py`
- Modify: `.env.example`
- Modify: `tests/test_approval_ui.py`

1. 写任务详情格式化测试，验证 Provider、模型、复杂度、回退、请求数和耗时可见，Prompt/Key 不可见。
2. 实现只读模型路由摘要和任务详情映射。
3. 在 `.env.example` 增加四家 Provider 的占位配置和可选模型覆盖，不写真实 Key。
4. 运行 UI 聚焦测试。

### Task 4: Day13 验收材料与文档同步

**Files:**
- Create: `day13/Day13.ipynb`
- Modify: `README.md`
- Modify: `C:/Users/admin/memory/projects/ai-coding-agent.md`（仅在全部验收成功后更新完成状态）

1. 创建只使用 Fake Provider 的 no-LLM notebook，演示简单/复杂选择、格式纠正和跨 Provider 回退。
2. 执行 notebook 全部代码单元。
3. 更新 README 能力和路线图；只有真实 Provider 与 Unity 全链路通过后才标记 Day13 完成。

### Task 5: 完整验证

1. 运行 `python -m unittest discover -s tests -v`。
2. 运行 `python -m compileall agents llm memory workflow ui tests`。
3. 运行 `git diff --check` 并审计路由日志/状态没有 Key、Prompt 和任意命令入口。
4. 使用四家真实 Provider 做最小调用可用性验证，不输出 Key。
5. 在用户配置的 Unity 项目执行真实生成、审批、编译、测试、Review、Git 本地提交闭环；若运行环境或 API 阻塞，保留 Day13 为“实现完成、真实验收待完成”，不虚报完成。
