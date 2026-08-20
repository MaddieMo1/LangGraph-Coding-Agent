# Team Observation Productization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将团队只读观察从 Day18 阶段性标签升级为可发现、可长期使用的正式功能。

**Architecture:** 保留现有单服务、只读令牌、SSE 和本机控制权边界。只调整用户可见品牌与配置文档，并由 `ObservationSettings.enabled` 控制本机导航入口是否渲染。

**Tech Stack:** Python、Gradio、FastAPI、原生 HTML/CSS、unittest

---

### Task 1: 固化正式品牌与入口契约

**Files:**
- Modify: `tests/test_day18_observation_ui.py`
- Modify: `tests/test_approval_ui.py`

1. 增加失败测试，验证正式观察标签和按启用状态显示的安全新标签页入口。
2. 运行两组定向测试，确认当前实现失败。

### Task 2: 实现正式观察标签和本机入口

**Files:**
- Modify: `ui/observation_app.py`
- Modify: `ui/approval_app.py`
- Modify: `app.py`

1. 替换观察页阶段性标签。
2. 为 `build_approval_app` 增加默认关闭的 `observation_enabled` 参数。
3. 启用时渲染指向 `/observe/ui/` 的“团队观察”链接。
4. 在应用装配时传入 `settings.enabled`。
5. 运行定向测试并确认通过。

### Task 3: 正式化配置与运行文档

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify outside repository: `../.env`

1. 删除正式配置区的 Day18/临时测试措辞，同时保留路线图与发布历史中的 Day18。
2. 真实 `.env` 只修改注释，不修改配置值。
3. 执行环境配置预检。

### Task 4: 完整验证、重启与提交

**Files:**
- Test: `tests/test_day18*.py`
- Test: `tests/test_approval_ui.py`

1. 运行团队观察专项和完整测试集。
2. 执行 `compileall` 与 `git diff --check`。
3. 重启 7860 服务，验证本机根路径 200、局域网观察页 200、局域网根路径 403。
4. 浏览器检查正式标签和本机入口。
5. 使用中文提交信息提交改动。
