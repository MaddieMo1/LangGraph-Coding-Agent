# Day12 Failed Repair Resume Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 允许代码门禁终态失败的活动任务在原 thread、原分支和原批准文件上重新分析根因、生成 Repair 提案并再次进入人工审批。

**Architecture:** Repair Agent 先按目标文件聚合根因，同一个文件每轮只生成一个完整提案，避免多个旧快照互相覆盖。WorkflowRuntime 对失败任务执行所有权和工作区哈希校验后，在同一 LangGraph thread 上把执行点放回 Reviewer 出口，开启新的三轮 Repair 预算；UI 仅在满足恢复条件时显示“重新修复当前任务”，同时始终保留主动放弃归档入口。

**Tech Stack:** Python、LangGraph SQLite checkpointer、Gradio、unittest、Git 工作区哈希校验。

---

### Task 1: Repair 同文件根因聚合

**Files:**
- Modify: `agents/repair.py`
- Test: `tests/test_repair_agent.py`

**Steps:**

1. 写失败测试：两个根因指向同一文件时 LLM 只调用一次，提示词包含两条修复策略。
2. 写失败测试：不同目标文件仍分别生成提案。
3. 按目标文件保序分组；单一 `add_using` 继续走确定性工具，其余同文件根因合并为一次 LLM 修复。
4. 在 action 中保留 `roots`，并兼容既有 `root` 字段。
5. 运行 `python -m unittest tests.test_repair_agent -v`。

### Task 2: 同任务失败续修 Runtime

**Files:**
- Modify: `workflow/runtime.py`
- Modify: `memory/state.py`
- Test: `tests/test_workflow_runtime.py`

**Steps:**

1. 写失败测试：代码检查、Unity 编译、EditMode 或 Reviewer 终态失败可续修，系统错误、无批准文件、非 prepared 分支不可续修。
2. 写失败测试：续修保持 thread id，并先经过 Reviewer，再进入 Repair。
3. 复用 `GitAgent.verify_retry_state()` 校验分支、HEAD、文件集合和 SHA-256；所有权不匹配返回明确错误。
4. 清理当前轮验证/根因/提案状态，保留 query、批准历史、批准文件、Git 分支和历史记录；将 `repair_count` 重置为新预算并记录 `repair_retry_result`。
5. 以 `unity_compiler` 作为已完成节点更新检查点，使下一节点从 Reviewer 重新分析，而不是回到 Coder。
6. 运行 `python -m unittest tests.test_workflow_runtime -v`。

### Task 3: UI“重新修复当前任务”操作

**Files:**
- Modify: `ui/approval_app.py`
- Modify: `ui/view_state.py`
- Test: `tests/test_approval_ui.py`

**Steps:**

1. 写失败测试：可续修失败页显示按钮，普通失败页不显示；主动放弃归档仍显示。
2. 增加 Controller 流式入口，先显示“正在重新分析失败现场”，随后按 Reviewer、Repair、Change Proposal、人工审批快照刷新。
3. 更新活动任务锁文案：可续修时说明原地继续；不可续修时说明只能安全归档。
4. Repair 卡片兼容 grouped action 的多个根因。
5. 绑定按钮并补齐所有 render outputs。
6. 运行 `python -m unittest tests.test_approval_ui -v`。

### Task 4: 验证与真实任务验收

**Files:**
- Modify: `docs/plans/2026-08-11-day12-failed-repair-resume.md`
- Modify: `docs/plans/2026-08-11-day12-real-ui-hardening.md`

**Steps:**

1. 运行全量 `python -m unittest discover -s tests -p "test_*.py"`。
2. 运行 `python -m compileall agents tools workflow ui memory tests`。
3. 运行 `git diff --check` 并复核 Git 命令面没有新增 push、merge、rebase、reset 或任意 shell 入口。
4. 重启 7861，确认真实任务 `edd7c8cc…` 显示“重新修复当前任务”和“主动放弃并归档”。
5. 未经用户再次确认，不点击真实任务的续修或归档按钮；只验证可见性与检查点状态不变。
6. 更新完成记录和测试数量。

## 完成记录

- [x] Repair 按目标文件保序聚合根因；同文件只调用一次 LLM，不同文件保持独立提案；grouped action 同时保留全部结构化根因供 UI 展示。
- [x] 终态代码门禁失败可在活动任务所有权和工作区哈希校验通过后，保留原 thread、分支、批准文件与历史记录，从 Reviewer 重新分析并开启新的三轮 Repair 预算。
- [x] 左侧活动任务锁增加“重新修复当前任务”，并继续保留“主动放弃并归档”；不可续修状态不再显示误导性文案。
- [x] 刷新中断的非终态任务可从 SQLite 保存的 `next` 节点继续执行；“继续当前任务”不再只是重载页面。
- [x] 全量 228 tests OK；`compileall`、`git diff --check` 与 Git 命令面审计通过。
- [x] 7861 已重启。真实活动任务 `10c4d142…` 保持原 thread、`agent/d64e634e3674` 分支和 4 个未跟踪批准文件不变；检查点仍为 `next=repair`，UI 只读确认“继续当前任务”和“主动放弃并归档”可见，未点击任何任务操作。
- [x] 旧任务 `edd7c8cc…` 已由用户侧状态变更为 `rejected/archived`，不再拥有当前工作区，因此不会错误显示续修入口。
- [x] 继续执行时若 Repair 或其他 LangGraph 节点抛出运行时异常，Runtime 会立即结束 Gradio 流并返回 `WORKFLOW_NODE_ERROR`；页面退出全局 Processing、展示失败节点与错误，同时保留原检查点供再次继续。
- [x] CS0122 会从调用处诊断反查成员声明文件作为 Repair 目标；任务 `f8852bb6…` 的 `GroundClickManager.HandleGroundClick` 访问级别错误不再重复只修 `GroundClickController.cs`。
- [x] Repair 原因卡的 Gradio HTML、`.prose` 和内容节点统一使用透明暗色背景；全量 234 tests OK。
