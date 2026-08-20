# Day18 Readable Task Names Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** 为 Day18 只读观察任务增加安全、简短的中文名称，并为实际 `.env` 配置补充中文说明。

**Architecture:** 在观察快照白名单中增加 `task_name`，由确定性清理函数从 requirement goal/query 生成；UI 只负责组合状态、名称和短 ID。配置文件只增加注释，不改变值。

**Tech Stack:** Python、SQLite、FastAPI、Gradio、原生 JavaScript、unittest。

---

### Task 1: 公开名称契约

**Files:**
- Modify: `tests/test_day18_observation_contract.py`
- Modify: `memory/task_observation.py`

1. 添加名称提取、32 字符边界和敏感文本清理的失败测试。
2. 运行 `python -m unittest tests.test_day18_observation_contract -v`，确认失败。
3. 最小实现 `sanitize_task_name` 和快照 `task_name` 字段。
4. 重跑契约测试，确认通过。

### Task 2: 投影兼容与 UI 标签

**Files:**
- Modify: `tests/test_day18_observation_projector.py`
- Modify: `tests/test_day18_observation_api.py`
- Modify: `tests/test_day18_observation_ui.py`
- Modify: `ui/observation_app.py`

1. 添加新旧 checkpoint、API 快照与下拉标签测试。
2. 更新测试 fixture，并让下拉项显示 `状态 · 名称 · 短 ID`。
3. 运行全部 Day18 测试。

### Task 3: 中文配置注释

**Files:**
- Modify: `D:/Anaconda/Project/AI-Coding-Agent/agent-learning/.env`

1. 在不回显或修改值的前提下，为所有现有配置组增加中文说明。
2. 运行环境预检，确认配置仍为 READY。

### Task 4: 发布验证

1. 运行完整 unittest、compileall 和 `git diff --check`。
2. 重启 7860 服务，验证观察页 200、远程控制面 403。
3. 截图确认任务名称可读。
4. 使用中文 Conventional Commit 提交实现。
