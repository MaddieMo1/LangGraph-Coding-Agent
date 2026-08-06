# ADR 0005: LangGraph 原生中断与持久化人工审批

- 状态：Accepted
- 日期：2026-08-06

## 背景

Coder 和 Repair 原先能够直接写入生产 C# 文件。即使 Diff、哈希校验和补丁历史已经降低了误写风险，用户仍无法在变更落盘前审阅并明确授权。工作流还需要在进程退出后保留待审批状态。

## 决策

所有 Coder 与 Repair 产生的生产代码变更都先转换为只读补丁提案。`ApprovalStore` 用版本化 JSON 保存不可变审批包，`HumanApprovalNode` 使用 LangGraph `interrupt()` 暂停工作流，并通过同一 thread ID 和 `Command(resume=...)` 恢复。

LangGraph 检查点保存在 `memory/workflow_checkpoints.sqlite`。默认审批模式是整批批准或拒绝；高级模式允许选择文件，但批准的子集仍作为一个原子批次应用。应用前必须完成全部补丁预检，写入失败则补偿回滚。

本地 Gradio UI 是 Day11 的操作入口。它不启用公网分享，并将回调并发限制为 1。

## 结果

- AI 生成的生产代码在审批前不会写盘。
- 重启 UI 后，可以使用原 thread ID 恢复 SQLite 中的待审批任务。
- 哈希漂移会产生 `conflicted` 状态，不会覆盖外部修改。
- 重复审批是幂等的，不会重复应用补丁或记录历史。
- JSON 审批历史与 SQLite 工作流检查点承担不同职责，需要一并保留。

## 非目标

- 公网部署、身份认证和多用户授权。
- 对自动生成的隔离 EditMode 测试进行审批。
- Git 提交或分支管理；这些属于 Day12。

## 恢复与运行

运行 `python app.py` 启动本地 UI。若页面刷新或进程重启，将界面中显示的 thread ID 粘贴到“Thread ID”并点击“恢复任务”。如果 SQLite 中不存在对应检查点，界面会返回明确错误；不要删除 `workflow_checkpoints.sqlite` 或复用其他任务的 thread ID。
