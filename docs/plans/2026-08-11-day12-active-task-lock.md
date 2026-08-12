# Day12 Active Task Lock Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为单个生成代码仓库建立单活动任务所有权，自动恢复已有任务，允许原任务安全放弃并归档，并在任务恢复列表显示 Asia/Shanghai 更新时间。

**Architecture:** `WorkflowRuntime` 负责从 SQLite 最新检查点与当前 Git 分支识别仓库所有者，所有启动、归档和放弃操作都在 Runtime 再次校验所有权。`ApprovalController` 将新任务请求重定向到活动任务，并向 Gradio 暴露继续与放弃动作；UI 只负责显示锁定状态和本地化时间，不自行推断 Git 所有权。

**Tech Stack:** Python 3.10+、LangGraph SQLite Checkpointer、Gradio、Git CLI、`zoneinfo`、`unittest`。

---

## 安全与行为约束

- 一个 `GENERATED_SOURCE_PATH` 同时最多只有一个未完成任务拥有当前任务分支。
- 活动任务包括待审批任务、可重试失败任务，以及仍拥有已批准脏文件的终态失败任务。
- 新任务请求遇到活动任务时不得创建新 thread，必须返回原 thread 的最新 View。
- 后创建的 `DIRTY_BASELINE` 任务不得归档活动任务拥有的文件。
- “放弃并归档”只能从所有者 thread 执行；待审批提案先记录拒绝，再将已批准的跟踪和未跟踪文件保存到 stash。
- 初始审批尚未写入任何文件时，放弃任务只记录拒绝，不创建空 stash。
- 不新增 push、reset、checkout、merge、rebase 或任意命令入口。
- 恢复列表时间使用检查点 `updated_at`，转换到 `Asia/Shanghai`，格式为 `YYYY-MM-DD HH:mm`。

### Task 1: Runtime 活动任务所有权

**Files:**
- Modify: `workflow/runtime.py`
- Test: `tests/test_workflow_runtime.py`

**Steps:**

1. 写失败测试：当前分支存在 pending prepared thread 时返回该活动任务。
2. 写失败测试：已提交、已拒绝且 clean 的任务不占用仓库。
3. 写失败测试：同一分支多个记录时选择最新且真实拥有工作区的 thread。
4. 实现 `find_active_task()`，复用最新检查点、当前 Git inspect 与 approved hash 校验。
5. 运行 Runtime 聚焦测试。

### Task 2: 启动重定向与归档所有权保护

**Files:**
- Modify: `workflow/runtime.py`
- Modify: `ui/approval_app.py`
- Test: `tests/test_workflow_runtime.py`
- Test: `tests/test_approval_ui.py`

**Steps:**

1. 写失败测试：发起新任务时存在活动任务，不调用 `new_thread_id()` 或 `stream()`。
2. 写失败测试：非所有者 DIRTY_BASELINE thread 的归档返回 `ACTIVE_TASK_OWNS_WORKTREE`。
3. 实现 Controller 启动前锁检查并直接恢复原任务。
4. 在 Runtime 的归档入口强制所有权验证。
5. 运行 Controller 与 Runtime 聚焦测试。

### Task 3: 原任务放弃并归档

**Files:**
- Modify: `agents/git.py`
- Modify: `workflow/runtime.py`
- Modify: `ui/approval_app.py`
- Test: `tests/test_git_agent.py`
- Test: `tests/test_workflow_runtime.py`
- Test: `tests/test_approval_ui.py`

**Steps:**

1. 写失败测试：所有者任务可归档精确批准文件，现场漂移时拒绝。
2. 写失败测试：pending 提案先通过原 LangGraph interrupt 记录 reject，再归档已批准文件。
3. 实现 `abandon_active_task()`，返回 stash label、commit、文件或 clean/no-changes 结果。
4. UI 增加“继续当前任务”和“放弃并归档”操作；成功后恢复新任务入口。
5. 验证后创建的错误 thread 不再显示可执行归档动作。

### Task 4: 恢复任务日期

**Files:**
- Modify: `ui/approval_app.py`
- Test: `tests/test_approval_ui.py`

**Steps:**

1. 写失败测试：ISO `Z` 时间转换为 Asia/Shanghai 的 `YYYY-MM-DD HH:mm`。
2. 写失败测试：无效或缺失时间显示 `时间未知`，不抛异常。
3. 在任务下拉标签末尾追加本地更新时间。
4. 运行 UI 聚焦测试。

### Task 5: 全量与真实 UI 验收

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-08-11-day12-real-ui-hardening.md`
- Modify: `C:/Users/admin/memory/projects/ai-coding-agent.md`

**Steps:**

1. 运行完整 `unittest`、`compileall` 与 `git diff --check`。
2. 审计新增 Git 命令与所有权检查路径。
3. 在 7861 验证刷新后自动恢复 `fed6c707…`，任务列表显示日期。
4. 验证新任务请求不会创建额外失败 thread。
5. 保留当前 Repair 审批，不替用户批准；验证“放弃并归档”按钮可见但不实际点击。
6. 更新 Day 12 计划和路线图状态。

## 验收命令

```powershell
D:\Anaconda\Anaconda\envs\agent-learning\python.exe -m unittest discover -s tests -v
D:\Anaconda\Anaconda\envs\agent-learning\python.exe -m compileall -q agents tools workflow ui memory tests
git diff --check
```

当前开发分支存在用户的 Day 12 未提交改动，未获得提交授权，因此本计划不执行 commit。

## 完成记录（2026-08-11）

- [x] Runtime 识别当前 Git 分支的唯一活动任务，并覆盖待审批、执行中、可恢复 Test Generator 失败和持有已批准脏文件的终态失败。
- [x] 新任务入口重定向到原 thread；非所有者 `DIRTY_BASELINE` 归档由 Runtime 强制拒绝。
- [x] 原任务提供继续和主动放弃归档；归档前校验分支、HEAD、批准文件集合和 SHA-256。
- [x] 恢复列表显示 `Asia/Shanghai` 检查点时间，格式 `YYYY-MM-DD HH:mm`。
- [x] 真实 7861 状态恢复 `fed6c707…`，未创建额外 thread，未代替用户批准、拒绝或归档。
- [x] 212 个 Python 测试通过；`compileall`、`git diff --check` 和安全命令面审计通过。

状态：实现完成，等待用户在真实 UI 中决定继续审批或主动放弃并归档。
