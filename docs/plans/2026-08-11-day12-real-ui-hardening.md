# Day12 Real UI Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让现有 Gradio 审批工作台完整承载环境检查、任务生成、人工审批、Unity 验证、Repair 复审、本地 Git 提交与失败恢复，并通过真实 UI 端到端验收。

**Architecture:** 保留当前暗色三栏 Neural Control Deck 和单页 Gradio 架构，在工作流状态与组件渲染之间增加纯 View State 映射层。先修复生产/测试文件边界、Repair 重复提案与 Unity 编译污染，再将 UI 重构为环境检查、空闲、执行、审批、验证、完成、失败七类明确状态。

**Tech Stack:** Python 3.10+、Gradio、LangGraph、SQLite Checkpointer、Unity 2022.3 BatchMode、NUnit EditMode、Git CLI、unittest。

---

## 执行约束

- 视觉基线：用户提供的 1912×954 完整 UI 截图；保留暗色控制台、青色强调、三栏审批结构。
- Codex 桌面端机器人不是项目资产，不纳入实现或验收。
- Unity 测试工程固定为 `D:\Unity\Unity_Project\CodingAgentTest`。
- 不引入新的前端框架，不新增 push、PR、reset、rebase、merge 或任意命令执行能力。
- 当前分支已有未提交 Day12 改动；只做与本计划直接相关的增量修改，不覆盖用户改动。
- 未获得提交授权，本计划中的提交检查点仅作为建议，不实际执行。

## 当前状态

| 任务 | 状态 | 验证证据 |
|---|---|---|
| Task 1：计划文档与覆盖基线 | 已完成 | 基线 164 tests OK；覆盖矩阵已记录 |
| Task 2：生产/测试文件边界 | 已完成 | File Planner/Coder 聚焦测试 + 全量回归 |
| Task 3：Repair 同名文件合并 | 已完成 | Repair/Proposal/Approval 17 tests OK |
| Task 4：Unity 编译隔离与基线检查 | 已完成 | 真实 Unity 基线与变更后编译均通过；沙箱均已清理，真实工程未写入 |
| Task 5：统一 UI View State | 已完成 | 九类状态映射与失败门禁测试通过 |
| Task 6：九状态条件界面 | 已完成 | Gradio 组件显隐、失败门禁和完成态测试通过 |
| Task 7：功能详情与失败恢复 | 已完成 | Runtime 仅将真实 interrupt 标为可恢复；恢复、失败与摘要 UI 测试通过 |
| Task 8：响应式与可访问性 | 实现完成，视觉验收阻塞 | 980px 断点、焦点、强制颜色、减弱动效、12px 正文和 44px 操作测试通过；自动多视口截图受浏览器运行时阻塞 |
| Task 9：功能验收完成，视觉验收阻塞 | 部分完成 | 203 tests、compileall、安全审计、真实 DeepSeek→审批→Unity→Git 全链路通过；自动截图与视觉对比未完成 |
| Task 10：文档收尾完成，最终视觉签收待定 | 部分完成 | README、路线图与本文档已更新；不将视觉阻塞误报为完成 |

## 功能覆盖矩阵

| 当前能力 | 新 UI 承载位置 | 验收方式 |
|---|---|---|
| DeepSeek、Unity、Git、SQLite 环境 | 环境检查页 | 有效/无效配置测试 |
| 发起任务与示例输入 | 空闲主工作区 | 表单与流式启动测试 |
| SQLite 最近任务和恢复 | 任务历史抽屉 | 跨 Runtime 恢复测试 |
| Git 基线检查和任务分支 | 环境卡片、Git 卡片 | Git Tool/Agent 测试 |
| Project Understanding、Dependency Graph、Memory | 执行详情摘要 | 状态映射测试 |
| Architecture、Validator、File Planner、Coder | 执行时间线与计划文件 | 流式快照测试 |
| Coder/Repair 提案、逐文件 Diff | 审批工作区 | 提案与文件切换测试 |
| 全部批准、部分批准、拒绝、备注 | 条件审批栏 | Controller/节点测试 |
| 哈希冲突、原子应用、幂等决策 | 冲突/失败页 | Human Approval 测试 |
| Test Generator、Code Checker | 验证时间线 | 工作流路由测试 |
| Unity 编译、EditMode 测试、Reviewer | 验证详情 | 工具测试 + 真实 Unity |
| Repair 循环和再次审批 | 修复轮次 + 审批工作区 | 两轮工作流测试 |
| 本地 Git 提交 | 成功页 | 提交 hash/路径测试 |
| 不支持 push/PR | 安全边界说明 | 文案与命令面审计 |

### Task 1: 计划文档与行为基线

**Files:**
- Create: `docs/plans/2026-08-11-day12-real-ui-hardening.md`
- Inspect: `README.md`
- Inspect: `memory/state.py`
- Inspect: `workflow/graph.py`
- Inspect: `ui/approval_app.py`

**Steps:**

1. 记录设计边界、功能覆盖矩阵和执行状态。
2. 运行现有全量测试，保存基线通过数。
3. 记录当前真实 UI 失败证据与未解决根因。
4. 每完成一个 Task，更新“当前状态”和对应验证证据。

### Task 2: 阻止测试文件进入生产代码目录

**Files:**
- Modify: `prompts/file_planner_prompt.py`
- Modify: `agents/file_planner.py`
- Modify: `agents/coder.py`
- Test: `tests/test_file_planner.py`
- Test: `tests/test_day11_agents.py`

**Steps:**

1. 写失败测试：File Planner 返回 `*Tests.cs` 时必须被拒绝或过滤。
2. 写失败测试：Coder 不得为生产提案生成测试文件。
3. 运行聚焦测试并确认先失败。
4. 在确定性代码边界实现最小校验；提示词只作为辅助约束。
5. 运行聚焦测试并确认通过。

### Task 3: 合并 Repair 同名文件提案

**Files:**
- Modify: `agents/repair.py`
- Test: `tests/test_repair_agent.py`
- Test: `tests/test_change_proposal_tool.py`

**Steps:**

1. 写失败测试：多个成功 action 返回同一文件时，Repair 输出每个文件最多一次。
2. 定义确定性合并规则：保持首次出现顺序，同名文件采用最后一个成功 action 的完整内容。
3. 运行测试并确认先失败。
4. 实现最小去重逻辑，不放宽 ChangeProposalTool 的重复文件安全拒绝。
5. 运行 Repair、提案和审批聚焦测试。

### Task 4: Unity 编译隔离与基线健康检查

**Files:**
- Modify: `tools/unity_compile_tool.py`
- Modify: `agents/unity_compiler.py`
- Modify: `workflow/graph.py`
- Test: `tests/test_unity_compile_tool.py`
- Test: `tests/test_day12_workflow.py`

**Steps:**

1. 写失败测试：编译不得永久修改真实测试工程 `Assets/Generated`。
2. 将编译改为临时沙箱，复制 `Assets`、`Packages`、`ProjectSettings` 后替换沙箱源码。
3. 写失败测试：任务代码生成前必须验证当前生产基线可编译。
4. 增加基线健康门；环境错误或基线错误直接结构化结束。
5. 运行工具测试，并对 `CodingAgentTest` 执行真实编译。

### Task 5: 统一 UI View State

**Files:**
- Create: `ui/view_state.py`
- Modify: `ui/approval_app.py`
- Modify: `memory/state.py`
- Test: `tests/test_approval_ui.py`

**Steps:**

1. 为 `preflight`、`idle`、`running`、`pending`、`validating`、`completed`、`failed`、`rejected`、`conflicted` 写映射测试。
2. 用纯函数将 AgentState 转为 UI View State。
3. 统一状态标签、活动阶段、错误摘要和可用动作。
4. 保持 Controller 只负责 Runtime 调用与 View State 转换。
5. 运行全部 UI 单元测试。

### Task 6: 九状态条件界面

**Files:**
- Modify: `ui/approval_app.py`
- Test: `tests/test_approval_ui.py`

**Steps:**

1. 空闲时在中央显示任务输入和环境状态，隐藏空 Diff、Git 占位和审批栏。
2. 执行时显示节点时间线、项目理解、架构和计划文件摘要。
3. 审批时显示文件、Diff、统计、备注和三种决策。
4. 验证时显示静态检查、Unity 编译、测试和 Reviewer 状态。
5. 完成时显示测试摘要、Git 提交与安全边界。
6. 失败时显示失败节点、错误、日志、未提交状态与恢复入口。

### Task 7: 功能详情与恢复行为

**Files:**
- Modify: `workflow/runtime.py`
- Modify: `ui/approval_app.py`
- Test: `tests/test_workflow_runtime.py`
- Test: `tests/test_approval_ui.py`

**Steps:**

1. 展示 Project Context、Dependency Graph、Memory、验证与 Repair 摘要。
2. 保留最近任务、刷新后恢复和待审批继续功能。
3. 区分环境错误、代码错误、审批冲突、Git 错误。
4. 仅在 Runtime 能安全恢复时提供重试动作；否则明确要求发起新任务。
5. 验证失败任务不会被显示为“已完成”。

### Task 8: 响应式与可访问性

**Files:**
- Modify: `ui/approval_app.py`
- Test: `tests/test_approval_ui.py`

**Steps:**

1. 修复桌面、平板和移动端状态布局。
2. 确保关键正文不小于 12px，并提高弱对比文字可读性。
3. 确保状态不只依赖颜色，焦点和禁用态清晰。
4. 验证 `prefers-reduced-motion`、键盘操作和 200% 缩放。
5. 保存 1920、1440、1024、768、375 宽度截图。

### Task 9: 全量与真实 UI 验收

**Files:**
- Update: `docs/design-references/`
- Update: `docs/plans/2026-08-11-day12-real-ui-hardening.md`

**Steps:**

1. 运行完整 Python 测试和 `compileall`。
2. 运行安全命令面审计。
3. 使用真实 DeepSeek 从 UI 发起任务。
4. 在 UI 审阅并批准提案。
5. 验证 Unity 编译、EditMode 测试、Reviewer 和必要的 Repair 复审。
6. 验证仅在全部门禁通过后创建本地 Git 提交。
7. 截取空闲、执行、审批、验证、成功和失败状态。
8. 执行 Product Design `design-qa`，直到 P0/P1/P2 清零或记录阻塞。

### Task 10: 文档与路线图收尾

**Files:**
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `docs/plans/2026-08-11-day12-real-ui-hardening.md`
- Modify: `C:/Users/admin/memory/projects/ai-coding-agent.md`

**Steps:**

1. 更新配置、UI 状态、恢复行为和安全边界文档。
2. 将本文档所有任务更新为最终状态并附验证证据。
3. 仅在真实 UI、Unity 和 Git 提交全部通过后更新路线图为完成。
4. 记录未解决的 P3 视觉优化，不将其误报为阻断项。

## 验收命令

```powershell
D:\Anaconda\Anaconda\envs\agent-learning\python.exe -m unittest discover -s tests -v
D:\Anaconda\Anaconda\envs\agent-learning\python.exe -m compileall agents tools workflow ui memory tests
```

真实 UI 验收必须使用 `D:\Unity\Unity_Project\CodingAgentTest`，并核对嵌套生成代码仓库的分支、状态、提交 hash 和未暂存文件。

## 完成记录

- 开始时间：2026-08-11。
- 功能验收时间：2026-08-11 12:15（Asia/Shanghai）。
- 全量测试：203 tests OK。
- Python 语法编译：`compileall` 通过。
- Unity 编译：真实 `CodingAgentTest` 基线与变更后编译均通过，`sandbox_cleaned=true`；真实工程未出现 `ScoreValue.cs` 或生成测试文件。
- EditMode 测试：14/14 通过，0 failed，0 skipped。
- 真实 UI：通过 Gradio 事件接口完成真实 DeepSeek 任务发起、提案审阅、批准、刷新恢复与终态读取；自动浏览器截图因 in-app Browser 的 `Cannot redefine property: process` 和本机 Edge 远程调试启动策略阻塞。
- 本地 Git 提交：临时验收仓库分支 `agent/a5bd4f51bb7b`，提交 `b3b5c55fce56080e027a9cdbdd46ceef669d212b`，仅新增 `ScoreValue.cs`，工作区干净。
- 安全审计：Git 命令面包含 inspect、branch switch/create、diff、按批准路径 add、commit，以及用户显式触发的固定参数 stash 归档；无 push、pull、fetch、remote、merge、rebase、reset 或任意 shell 命令入口。
- 最终结论：功能闭环完成；自动多视口截图和 Product Design 视觉对比仍待人工浏览器验收，因此不标记完整视觉验收完成。

## 执行日志

### 2026-08-11 · 第一批

- 创建本计划并以 164 个既有测试全部通过作为行为基线。
- File Planner 过滤 `Test.cs`/`Tests.cs`，Coder 在生产提案边界再次拒绝测试文件；测试仍由独立 Test Generator 负责。
- Repair 汇总多个成功 action 时按文件去重：保持首次出现顺序，同名文件采用最后一个成功 action 的完整内容。
- ChangeProposalTool 的重复文件拒绝保持不变，继续作为安全兜底。
- 新增 3 个回归测试；全量 167 tests OK，`compileall` 通过。

### 2026-08-11 · 第二批

- Unity 编译改为临时沙箱：复制真实工程的 `Assets`、`Packages`、`ProjectSettings` 后，仅在沙箱替换生成源码；退出时清理沙箱，不永久修改真实测试工程。
- 在 Git 准备与 Coordinator 之间增加独立基线编译门禁，结果写入 `baseline_compile_result`，不污染后续任务代码的 `compile_result`。
- 新增纯 `ui/view_state.py`，统一映射 `preflight`、`idle`、`running`、`pending`、`validating`、`completed`、`failed`、`rejected`、`conflicted` 九类用户可见状态。
- 只有本地 Git 已提交才显示“已完成”；审批错误、Git 错误、基线错误及终态验证失败统一显示失败节点和错误摘要。
- 保留暗色三栏控制台视觉；空闲、审批、验证、完成与失败使用条件组件，空的 Diff、Git 和决策占位不再常驻。
- 新增 7 个回归测试；全量 174 tests OK，`compileall` 与 `git diff --check` 通过。

### 2026-08-11 · 第三批

- Runtime 最近任务的 `resumable` 改为读取真实 LangGraph interrupt，避免把普通中间检查点误报为可恢复审批。
- UI 增加 Project Context、Dependency Graph、Memory、Repair、验证门禁和 Git 终态摘要；失败任务不提供盲目重跑入口。
- 响应式断点调整为 980px，并增加键盘焦点、强制颜色、减弱动效、关键文字和触控尺寸契约。
- 真实 UI 首轮发现模型越界改写既有 Inventory 文件，随后收紧 Architecture/File Planner 提示词，只允许围绕用户请求规划；拒绝流程验证未写入、未提交。
- 真实批准流程发现 Windows CRLF 与批准内容 LF 的哈希假冲突；Git Agent 改用通用换行读取，并新增平台换行回归测试，同时保留真实内容漂移拦截。
- 在隔离临时仓库完成第二轮真实任务：仅生成并批准 `ScoreValue.cs`，Unity 基线与变更后编译通过，EditMode 14/14、Reviewer 通过，最后创建单一本地提交 `b3b5c55`。
- 最终全量 179 tests OK，`compileall` 通过，安全命令面审计通过。两个验收临时仓库均保留，未删除或覆盖用户数据。

### 2026-08-11 · 第四批（真实 UI 反馈）

- 顶部模块标题由 View State 驱动，按环境检查、任务执行、审阅变更、应用与验证、完成、失败、拒绝和冲突动态切换，不再常驻“人工审批”。
- Diff 改为 `360–620px` 自适应固定视口，代码在框内滚动；进入审批默认选择第一份变更文件。
- Runtime 增加审批恢复流式快照；点击全部或部分批准后先显示“正在原子应用”，再逐节点刷新 Code Checker、Unity 编译、EditMode、Reviewer 和 Git 状态。
- 失败阶段轨迹保留已发生事实：批准内容已写入时第三步显示完成，代码或 Unity 门禁失败时第四步标红；失败活动不再误显示“完成任务”。
- 对用户任务 `48a169ec…` 的持久化状态复盘确认，`InventorySaveData` 与 `ItemType` 均在 `InventoryItemData.cs`、`InventoryManager.cs` 跨文件重复声明。Code Checker 新增确定性 `DUPLICATE_TYPE` 检查，在 Unity 启动前返回完整类型名和冲突文件列表。
- 新增 8 个回归测试；最终全量 187 tests OK，`compileall` 与 `git diff --check` 通过。

### 2026-08-11 · 第五批（失败现场安全归档）

- 复盘任务 `421300ac…` 确认：三轮 Repair 后验证仍失败，5 个已批准文件保留在任务分支工作区；后续任务 `859668b0…` 因正确触发 `DIRTY_BASELINE` 而停止。刷新页面不会改变 Git 状态。
- `DIRTY_BASELINE` Git 卡片现在展示精确脏文件列表，并提供“归档失败现场并清理工作区”按钮；其他失败类型不显示该动作。
- 归档前重新读取仓库并要求当前文件集合与失败检查点完全一致；检测到外部新增或删除文件时以 `DIRTY_BASELINE_DRIFT` 拒绝操作。
- 归档使用固定参数 `git stash push --include-untracked --message <内部安全标签>`，同时保存跟踪与未跟踪文件；完成后再次检查工作区必须 clean，并返回 stash commit 与标签。
- 在 7861 真实 Gradio 事件链恢复任务 `859668b0…` 并触发归档：生成 `stash@{0}` / `55a239f4ea7f051731db1402dffba6af6f774c79`，保存 4 个修改文件和 1 个新增文件，归档后仓库 clean、页面 HTTP 200。内置浏览器仍受宿主 `Cannot redefine property: process` 阻塞，因此本批未新增自动截图。
- 新增 7 个回归测试；最终全量 194 tests OK，`compileall`、`git diff --check` 与 Git 命令安全审计通过。

### 2026-08-11 · 第六批（同任务测试生成恢复）

- 复盘任务 `fed6c707…`：生产代码已批准并写入，分支 `agent/2da5f5306224` 保持 prepared，唯一失败为 Test Generator 返回截断 JSON；原路由直接进入 `finish_task`，导致 UI 只能重新开始。
- Test Generator 仅对缺失、截断或非法 JSON 自动重试最多 2 次（共 3 次尝试）；Tool 的路径、文件名、空内容等安全校验失败不自动重试。
- 解析重试耗尽后写入 `MODEL_OUTPUT_PARSE_ERROR`、`retryable=true` 和 attempts；旧检查点通过既有错误文本保持兼容。
- 失败页增加“重试生成测试”；Runtime 在同一 thread 上从已批准出口重新进入 Test Generator，不重复生成或应用生产代码，也不重复人工审批。
- 恢复前校验当前任务分支、基准 commit、脏文件集合和每个批准文件的 SHA-256；分支、HEAD、文件集合或内容漂移均拒绝继续。
- 在 7861 对真实旧检查点 `fed6c707…` 触发同任务恢复：Test Generator 成功越过原 JSON 解析错误，随后 Code Checker/Unity 发现生产代码问题并进入 Repair 第 1 轮；工作流停在新的 Repair 人工审批检查点，thread ID 与 `agent/2da5f5306224` 分支均保持不变。
- 修复恢复状态文案在后续 Repair 审批中的残留；恢复提示仅在 Test Generator 正在执行时显示。
- 新增 9 个回归测试；最终全量 203 tests OK，`compileall`、`git diff --check` 与恢复命令面审计通过。

### 2026-08-11 · 第七批（单活动任务锁与主动归档）

- Runtime 将当前 Git 分支与最新 SQLite 检查点关联，识别待审批、执行中、可恢复测试生成失败，以及仍持有已批准脏文件的唯一活动任务。
- 页面启动时自动恢复活动任务；重复点击“开始并生成提案”会重定向到原 thread，不创建新的 `DIRTY_BASELINE` 记录。真实状态验证前后任务数量保持 9→9。
- 后创建的失败 thread 不能归档活动任务工作区，Runtime 返回 `ACTIVE_TASK_OWNS_WORKTREE`；归档所有权不依赖前端按钮可见性。
- 原任务显示“继续当前任务”和“主动放弃并归档”。待审批提案先通过原 LangGraph interrupt 记录拒绝，再仅对精确匹配的已批准文件执行 stash；初始提案未写入文件时只记录拒绝，不创建空 stash。
- 恢复任务标签末尾追加检查点的北京时间，格式为 `YYYY-MM-DD HH:mm`；缺失或非法时间显示“时间未知”。
- 7861 真实只读验收自动恢复 `fed6c707…` 的 Repair 审批，分支 `agent/2da5f5306224`、2 个 Repair patches 和待审批状态保持不变；活动锁与两个原任务操作可见，新任务按钮禁用，普通失败现场归档按钮隐藏。未点击批准、拒绝或主动归档。
- 新增 9 个回归测试；最终全量 212 tests OK，`compileall`、`git diff --check` 与 Git 命令安全审计通过。内置浏览器仍因宿主初始化冲突无法截图，验收改用真实 Runtime 与 Gradio `/config` 只读状态。

### 2026-08-11 · 第八批（Repair 复审上下文与 UI 一致性）

- 活动任务锁补齐深色背景、边框和文字覆盖，Gradio HTML 容器不再回落为白色。
- Diff 外层 `#diff-view`、`.wrap`、`.code_wrap` 与 `.cm-editor` 固定为 `overflow: hidden`，仅 `.cm-scroller` 保留滚动，消除重叠的双纵向滚动条。
- Repair 待审批标题改为“第 N 轮 Repair 修复复审”，并显示本任务人工审批序号，明确它是验证失败后的新修复提案而非重复提交。
- 右侧新增“本轮 Repair 原因”卡片，从既有检查点显示失败门禁、错误代码、根因、相关文件和修复策略；Coder 初始提案不显示该卡片，所有检查点文字均 HTML 转义。
- 真实只读验证从任务 `8372a6bd…` 提取 Repair 第 3 轮、第 5 次人工审批、`Unity 编译 / 代码审查`、`CS0019 / CS7036` 与两个结构化根因；未改变其已拒绝状态和 7 个现场文件。
- 新增 4 个回归测试；最终全量 216 tests OK，`compileall`、`git diff --check` 与命令面审计通过。

### 2026-08-11 · 第九批（Repair 卡片样式回归与失败诊断）

- Repair 原因卡的 Gradio HTML 内层容器补齐透明深色背景和文字颜色覆盖，避免外层为深色而内层仍显示白底。
- 只读复盘任务 `edd7c8cc…`：第 3 轮 Repair 对 3 个根因分别调用 LLM，但 3 次都以磁盘上的同一份旧 `InventoryView.cs` 为上下文；同文件提案去重时只保留最后一次完整文件结果，导致前两次删除重复类型的修复丢失，最终仍在 `InventoryManager.cs` 与 `InventoryView.cs` 重复声明 `InventorySystem.InventoryManager`。
- 当前 `success` 仅表示 Repair 输出被成功解析为文件提案，不表示提案已通过静态检查或 Unity 编译；最终门禁正确拦截了错误代码。
- 新增 1 个 UI 回归测试；最终全量 217 tests OK。诊断过程未批准、拒绝、归档或改写当前真实任务。

### 2026-08-11 · 第十批（失败任务原地续修与刷新断点恢复）

- Repair Agent 改为按目标文件聚合根因；同一文件的重复类型、接口不一致等策略进入一次完整文件修复，避免多个旧快照按“最后提案覆盖”丢失先前修复。
- Runtime 新增代码门禁终态失败续修：校验活动任务所有权、分支、HEAD、脏文件集合和批准文件 SHA-256 后，在同一 thread 上从 Reviewer 重新分析，保留批准文件与历史记录并开启新的 Repair 预算。
- UI 新增“重新修复当前任务”，仅对可安全续修的活动任务显示；“主动放弃并归档”继续作为安全出口，活动锁文案按可继续、可重新修复或仅可归档三种状态切换。
- 修复刷新导致的流式执行中断：只要 LangGraph 检查点保存了未执行的 `next` 节点，“继续当前任务”就从该节点继续，而不是只重载同一页面。
- 真实只读验证发现新任务 `10c4d142…` 停在 `next=repair`；7861 重启后“继续当前任务”和“主动放弃并归档”可见，分支 `agent/d64e634e3674` 与 4 个工作区文件保持不变，未代替用户继续或归档。
- 新增 9 个回归测试；最终全量 226 tests OK，`compileall`、`git diff --check` 与 Git 命令面审计通过。

### 2026-08-12 · 第十一批（继续任务异常收敛）

- 定位任务 `10c4d142…` 的长时间 Processing：保存的下一节点为 `repair`，上一次节点执行记录为 `OSError(22, "Invalid argument")`；同一检查点的只读 Repair 诊断可成功生成提案，说明任务数据与 Repair 分组逻辑仍可恢复。
- `continue_active_task_stream` 现在捕获工作流节点异常并返回结构化 `WORKFLOW_NODE_ERROR`，附带失败节点与 `retryable` 标记；Gradio 事件会正常结束，不再无限显示全局 Processing。
- UI 收到该结果后显示“继续任务失败：<节点>: <错误>”，并继续提供“继续当前任务”和“主动放弃并归档”，原 thread、分支、批准文件与 SQLite 下一节点均不变。
- 清理误启动的 7862 副本并以真实临时仓库、Unity 工程和 SQLite 检查点重新启动唯一 7861 实例；`/config` 返回 HTTP 200，继续与归档按钮可见。
- 新增 2 个回归测试；最终全量 228 tests OK，`compileall` 与 `git diff --check` 通过。

### 2026-08-12 · 第十二批（Unity 基线环境故障恢复）

- 复盘任务 `f8852bb6…` 的完整 Unity 日志，确认失败发生在代码生成前：LicensingClient 返回 `No valid Unity Editor license found`，并非 C# 基线代码错误。
- Unity 编译工具将该日志识别为 `UNITY_LICENSE_UNAVAILABLE`，UI 直接提示先在 Unity Hub 登录并激活许可证，不再只显示泛化的“进程异常退出”。
- 系统级基线失败保留为活动任务，新增“重新检查 Unity 基线”；重试前校验原分支、基准 commit 与 clean 工作区，通过后在同一 thread 从基线节点继续进入 Coordinator，不重新创建任务。
- “主动放弃并归档”继续作为安全出口；许可证仍不可用时，重试停留在原任务并显示可操作错误。
- 新增 4 个回归测试；最终全量 232 tests OK，`compileall` 与 `git diff --check` 通过。

### 2026-08-12 · 第十三批（CS0122 声明目标 Repair 与暗色卡片收口）

- 复盘任务 `f8852bb6…`：`GroundClickController.cs` 调用了 `GroundClickManager.HandleGroundClick(Vector3)`，而 `GroundClickManager.cs` 仅声明私有无参方法；编译器把 CS0122 报在调用文件，前三轮 Reviewer 因而持续把 Repair 目标错误地留在 Controller。
- Reviewer 对 CS0122 从诊断中的 `类型.成员` 反查声明文件，将调用处保留为 `source_file`、声明处设为 `target_file`；Repair 因此同时获得调用和声明上下文，并修改真正拥有访问级别/API 定义的文件。
- Repair 原因卡补齐 Gradio 主题变量、`.prose` 与最终内容节点的透明背景覆盖，避免 HTML 容器在暗色卡片内继承白色底纹。
- 新增 2 个回归测试；最终全量 234 tests OK。未替用户修改、批准或归档任务 `f8852bb6…` 的现场文件。

### 2026-08-12 · 第十四批（Repair HTML 默认样式根因修复）

- 真实 UI 复核确认白色矩形并非 Repair 内容节点自身背景，而是 Gradio 6.22 `HTML` 动态内容默认注入的 `prose gradio-style` 表面；加载态的 `.html-container.pending` 只改变透明度，因此此前追加透明选择器无法稳定消除底色。
- `repair-context-info` 关闭 `apply_default_css`，从组件配置源头移除默认 prose 表面，同时保持 `container=false` 和现有暗色 CSS 兜底。
- 任务 `f8852bb6…` 已通过 Unity 基线、静态检查、Unity 编译、EditMode 与 Reviewer，并在 `agent/db30aa68b197` 创建本地提交 `187310b0…`，工作流状态为完成。
- 新增 1 个组件配置回归测试；最终全量 235 tests OK。

### 2026-08-12 · 第十五批（已保存任务管理体验）

- 已保存任务下拉标签改为“月日时间 · 状态 · 16 字标题”，不再把完整标题、状态、短 ID 和完整日期挤在同一选项中；选中后通过独立详情卡展示完整标题、状态、上海时间和 thread ID。
- 新增“删除所选任务”与显式确认框；删除只清理 SQLite 中该 thread 的 `checkpoints` / `writes`，不删除 Git 分支、提交、stash、生成代码或 Unity 工程文件。
- 当前仍拥有工作区的活动任务禁止直接删除，必须先通过“主动放弃并归档”安全释放现场；删除后任务列表立即刷新且不改写主工作区。
- 已提交任务的内部审批状态（例如 `no_changes`）在历史列表中统一映射为“已完成”，不向用户暴露工作流内部枚举。
- 新增 6 个回归测试；最终全量 241 tests OK。

### 2026-08-12 · 第十六批（独立任务中心）

- 顶部新增“工作台 / 任务中心”一级切换，同时保留运行状态、任务 ID 与提案来源；切换只改变主内容区可见性，不重建工作流或清空未提交任务要求。
- 左侧旧恢复下拉管理器默认隐藏，保留“前往任务中心”快捷入口；任务中心使用全宽横向卡片，活动任务固定置顶，其余按最后更新时间倒序。
- 新增全部、进行中、需要处理、已完成四类统计入口，以及搜索、状态筛选、刷新、横向卡片选择、右侧详情抽屉和深色删除确认界面。
- 所有非活动任务支持单条或批量删除；活动任务由 Runtime 强制阻止删除。批量删除使用单个 SQLite 事务，包含活动任务或缺失任务时整批拒绝，不会发生部分删除。
- 删除仅作用于被选 thread 的 `checkpoints` 与 `writes`，不执行任何 Git/shell 命令，不修改分支、commit、stash、生成代码或 Unity 工程。
- 新增 7 个回归测试；最终全量 248 tests、17 subtests OK，`compileall` 与 `git diff --check` 通过。7861 服务 `/config` 已确认新组件与 35 条事件依赖加载；内置浏览器仍受宿主 `process` 属性冲突限制，最终视觉点击保留人工验收。
