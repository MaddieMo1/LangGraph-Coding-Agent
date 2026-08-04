\# LangGraph Coding Agent



基于 \*\*LangGraph + LangChain + DeepSeek\*\* 构建的 Multi-Agent AI Coding Assistant。



该项目探索 AI Agent 在软件工程自动化开发中的应用，实现从需求理解、架构设计、代码生成、代码检查、代码审查到自动修复的完整闭环。



\---



\# Features



\## Multi-Agent Workflow



项目采用多 Agent 协作架构：



\- Coordinator Agent

\- Architecture Agent

\- File Planner Agent

\- Coder Agent

\- Code Checker Agent

\- Reviewer Agent

\- Repair Agent





\## Automated Coding Pipeline



支持：



\- 用户需求分析

\- 系统架构设计

\- 文件规划

\- 多文件代码生成

\- 代码质量检查

\- AI代码审查

\- 自动修复





\## Repair Loop



当 Reviewer 发现问题：



```

Reviewer



&#x20;   ↓



Review Router



&#x20;   ↓



Repair Agent



&#x20;   ↓



Code Checker



&#x20;   ↓



Reviewer

```



自动进入修复流程。





\---



\# System Architecture





```

User Request



&#x20;     |



&#x20;     v



Coordinator Agent



&#x20;     |



&#x20;     v



Architecture Agent



&#x20;     |



&#x20;     v



File Planner Agent



&#x20;     |



&#x20;     v



Coder Agent



&#x20;     |



&#x20;     v



Code Checker Agent



&#x20;     |



&#x20;     v



Reviewer Agent



&#x20;     |



&#x20;     +------------+



&#x20;     |            |



&#x20;   Pass       Repair



&#x20;                 |



&#x20;                 v



&#x20;            Code Checker

```





\---



\# Tech Stack





| Technology | Purpose |

|-|-|

| Python | Backend Language |

| LangGraph | Agent Workflow |

| LangChain | LLM Framework |

| DeepSeek | Large Language Model |

| FAISS | Vector Retrieval |

| Pydantic | State Management |





\---



\# Project Structure





```

LangGraph-Coding-Agent



├── agents

│   ├── coordinator.py

│   ├── architecture.py

│   ├── file\_planner.py

│   ├── coder.py

│   ├── code\_checker.py

│   ├── reviewer.py

│   └── repair.py

│

├── workflow

│   ├── graph.py

│   ├── router.py

│   └── review\_router.py

│

├── memory

│   └── state.py

│

├── tools

│

├── prompts

│

├── llm

│

└── rag

```





\---



\# Example





Input:



```

设计一个Unity背包系统并生成代码

```





Agent 自动生成：



```

InventoryData.cs



InventoryManager.cs



InventoryController.cs



InventoryView.cs



InventoryEvents.cs

```





\---



\# Installation





\## Clone





```bash

git clone https://github.com/MaddieMo1/LangGraph-Coding-Agent.git

```





\## Install





```bash

pip install -r requirements.txt

```





\## Configuration





复制：



```

.env.example

```



修改：



```

.env

```





填写：



```

DEEPSEEK\_API\_KEY

```





\---



\# Roadmap





\## v0.1.0



完成：



\- Multi-Agent Workflow

\- LangGraph State Management

\- Code Generation

\- Code Review

\- Automatic Repair Loop





\## v0.2.0



计划：



\- Real Compiler Code Check

\- Unity API Knowledge Base

\- RAG Code Retrieval





\## v0.3.0



计划：



\- Code Execution Sandbox

\- Human Approval Workflow

\- Long-term Memory





\---



\# License



MIT License

