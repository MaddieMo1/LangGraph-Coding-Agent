# Day12 Repair 复审上下文与 UI 一致性计划

**目标：** 修复活动任务锁白色背景和 Diff 双滚动条，并让每次 Repair 修复提案明确展示再次审批的原因、轮次和失败证据。

## 已确认设计

- 活动任务锁继续位于左侧，但完整继承 Neural Control Deck 深色主题。
- Diff 仅由 CodeMirror `.cm-scroller` 负责滚动；Gradio 外层容器全部隐藏溢出。
- Repair 提案在右侧提案信息和审批备注之间增加“本轮 Repair 原因”卡片。
- 卡片显示 Repair 轮次、本任务人工审批序号、失败门禁、错误代码、根因描述、相关文件和修复策略。
- Coder 初始提案不显示 Repair 卡片，仍使用原审批界面。
- 所有内容只读取现有 LangGraph 检查点，不调用模型、不改变审批状态。

## 验收标准

1. 活动任务锁及其 HTML 容器没有白色背景。
2. `#diff-view`、包装层和编辑器隐藏溢出，只有 `.cm-scroller` 为 `overflow: auto`。
3. Repair 待审批页面标题包含“第 N 轮 Repair 修复复审”。
4. Repair 原因卡展示失败门禁、错误代码、根因、文件和策略，并对内容进行 HTML 转义。
5. Coder 初始提案不显示 Repair 原因卡。
6. 当前真实任务只读恢复，不代替用户批准、拒绝或归档。

## 执行步骤

- [x] 添加聚焦测试并确认失败。
- [x] 实现 Repair 上下文纯函数和 UI 卡片。
- [x] 修复活动锁主题与 Diff 滚动容器 CSS。
- [x] 运行聚焦测试、全量测试、`compileall`、`git diff --check`。
- [x] 重启 7861 并通过真实 Runtime/Gradio 配置只读验收。

当前工作区包含用户尚未提交的 Day12 改动，本计划不执行 commit。

## 完成记录

- 聚焦 UI 测试：46/46 通过。
- 全量测试：216/216 通过。
- `compileall` 与 `git diff --check`：通过。
- 真实检查点 `8372a6bd…` 可提取 Repair 第 3 轮、本任务第 5 次人工审批、`Unity 编译 / 代码审查`、`CS0019 / CS7036`、两个结构化根因和相关文件。
- 7861 已重启并加载新 CSS 与 `repair-context-card`；当前任务为已拒绝终态，因此卡片按设计隐藏，未来 Repair 待审批时显示。
- 验收过程未批准、拒绝、归档或改写当前任务；分支仍为 `agent/802ce0de988d`，7 个现场文件保持不变。
