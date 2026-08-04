\# Contributing Guide



感谢你参与 \*\*LangGraph Coding Agent\*\* 项目。



本项目是一个基于 \*\*LangGraph + LangChain + LLM\*\* 构建的 Multi-Agent AI Coding Agent 框架，目标是探索 AI Agent 在软件工程自动化开发中的应用。



欢迎提交：



\- Bug 修复

\- Agent 能力扩展

\- Workflow 优化

\- Tool 开发

\- Prompt 优化

\- RAG 知识库增强

\- 工程化改进





\---



\# Development Workflow



\## 1. Fork Repository



Fork 项目仓库：



```text

https://github.com/MaddieMo1/LangGraph-Coding-Agent

```





\## 2. Create Branch



请基于功能创建独立开发分支：



```bash

git checkout -b feature/new-feature

```



分支命名规范：



```

feature/xxx

fix/xxx

refactor/xxx

docs/xxx

```



示例：



```text

feature/unity-code-agent



fix/reviewer-json-parser



refactor/workflow-router



docs/update-readme

```





\---



\# Project Architecture



项目采用 Multi-Agent 架构：



```

&#x20;                User Request

&#x20;                      |

&#x20;                      v

&#x20;             Coordinator Agent

&#x20;                      |

&#x20;                      v

&#x20;           Architecture Agent

&#x20;                      |

&#x20;                      v

&#x20;            File Planner Agent

&#x20;                      |

&#x20;                      v

&#x20;                Coder Agent

&#x20;                      |

&#x20;                      v

&#x20;            Code Checker Agent

&#x20;                      |

&#x20;                      v

&#x20;             Reviewer Agent

&#x20;                      |

&#x20;             +--------+--------+

&#x20;             |                 |

&#x20;           Pass              Repair

&#x20;                               |

&#x20;                               v

&#x20;                        Repair Agent

&#x20;                               |

&#x20;                               v

&#x20;                        Code Checker

```





新增功能时，请保持：



\- Agent 职责单一

\- Workflow 流程清晰

\- State 状态统一

\- Tool 能力独立





\---



\# Adding New Agent



新增 Agent 时，请遵循以下规范。





\## 1. 创建 Agent 文件



目录：



```

agents/

```





示例：



```

agents/

&#x20;   test\_agent.py

```





\---



\## 2. Agent 基础结构





推荐：



```python

class TestAgent:

&#x20;   """

&#x20;   Test Agent



&#x20;   负责:

&#x20;   1. xxx

&#x20;   2. xxx

&#x20;   """



&#x20;   def \_\_init\_\_(self, llm):

&#x20;       self.llm = llm





&#x20;   def run(self, state):

&#x20;       """

&#x20;       执行Agent任务



&#x20;       Args:

&#x20;           state:

&#x20;               Agent共享状态



&#x20;       Returns:

&#x20;           更新后的状态

&#x20;       """



&#x20;       return state

```





\---



\## 3. 接入 Workflow





新增 Agent 后需要修改：



```

workflow/graph.py

```





包括：



\- 添加 Node

\- 添加 Edge

\- 更新 Router

\- 更新任务流程





确保：



```

Agent

&#x20;|

&#x20;v

Workflow

&#x20;|

&#x20;v

State Update

```





\---



\# Tool Development



Tool 用于封装外部能力。





目录：



```

tools/

```





例如：



```

tools/



├── file\_tool.py



├── code\_tool.py



└── code\_check\_tool.py

```





开发 Tool 时要求：



\- 单一职责

\- 输入输出明确

\- 不包含 Agent 调度逻辑

\- 支持独立测试





推荐架构：



```

Agent



&#x20; |



&#x20; v



Tool



&#x20; |



&#x20; v



External Resource

```





\---



\# Prompt Development



Prompt 统一管理：



```

prompts/

```





例如：



```

prompts/



├── architecture\_prompt.py



├── coder\_prompt.py



├── reviewer\_prompt.py



└── repair\_prompt.py

```





修改 Prompt 时需要考虑：



\- Role 定义

\- 输入上下文

\- 输出格式

\- JSON稳定性

\- 异常情况





建议：



所有结构化输出使用：



```json

{

&#x20;   "result": "",

&#x20;   "status": ""

}

```





\---



\# State Management



项目使用统一 State 管理 Agent 数据。





文件：



```

memory/state.py

```





新增 State 字段时，请说明：



\- 字段用途

\- 数据类型

\- 使用 Agent





例如：



```python

repair\_history:list

```





用于记录：



\- 修复次数

\- 修复文件

\- 修复结果





\---



\# Code Style





\## Python



遵循：



\- 模块职责清晰

\- 核心类添加说明

\- 重要函数添加 Docstring

\- 避免重复代码





\## Agent



要求：



\- 明确输入

\- 明确输出

\- 状态变化可追踪





\## Import



保持：



\- 简洁

\- 清晰

\- 避免循环依赖





\---



\# Commit Convention





提交信息格式：



```

type: description

```





类型：



```

feat     新功能



fix      Bug修复



refactor 重构



docs     文档



test     测试



chore    工程维护

```





示例：



```bash

git commit -m "feat: add code review agent"



git commit -m "fix: repair reviewer json parser"



git commit -m "refactor: improve workflow router"

```





\---



\# Testing





提交代码前，请确认：





\## Workflow Test



检查：



\- Agent 是否正常执行

\- Router 是否正确跳转

\- State 是否正确更新





\## LLM Test



检查：



\- Prompt输出格式

\- JSON解析

\- 异常处理





\## Repair Loop Test





验证：



```

Reviewer



&#x20;   |



&#x20;   v



Repair Agent



&#x20;   |



&#x20;   v



Code Checker



&#x20;   |



&#x20;   v



Reviewer

```





是否可以正常完成闭环。





\---



\# Pull Request





提交 Pull Request 时，请包含：





\## Description



说明：



\- 修改内容

\- 修改原因

\- 设计方案





\## Changes





示例：



```

Added:

\- New Agent



Modified:

\- workflow/graph.py



Fixed:

\- Reviewer parser issue

```





\## Testing Result





提供：



\- 测试命令

\- 输出结果

\- 截图（可选）





\---



\# Issue Guidelines





\## Bug Report





请提供：



\- 问题描述

\- 运行环境

\- 错误日志

\- 复现步骤





示例：



```

Environment:



Python:

3.10



OS:

Windows 10





Error:



KeyError: xxx

```





\---



\## Feature Request





请说明：



\- 功能目标

\- 使用场景

\- 设计方案





\---



\# Code Review Principles





代码审核重点：





\## Agent Design



检查：



\- 职责是否单一

\- 是否存在重复能力





\## Workflow



检查：



\- Graph结构是否合理

\- Router是否正确





\## State



检查：



\- 数据是否必要

\- 是否影响已有流程





\## Tool



检查：



\- 是否独立

\- 是否可测试





\## Prompt



检查：



\- 输出是否稳定

\- 是否容易产生幻觉





\---



\# License



提交代码表示你同意：



你的贡献内容遵循项目 MIT License。

