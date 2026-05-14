# FZU Homework Assistant

面向福州大学课程作业场景的 AI 作业资料工作台。项目把“上传资料、检索证据、生成报告、质量审稿、保存草稿、数据监控”串成一条可观测的 Agent 工作流，适合作为后端开发 / 大模型应用方向的简历项目展示。

## 项目亮点

- **自研 ReAct-lite Agent Loop**：Python Agent 按固定上限执行检索、生成、质量检测、自动改写等工具步骤，避免无限循环，并输出完整 `agent_trace`。
- **RAG 作业资料生成**：上传 PDF / Markdown / TXT 资料后，Agent 自动解析、切分、向量化到 ChromaDB，并基于检索片段生成 Markdown 报告草稿。
- **Skill Routing + Dynamic Planner**：支持实验报告、论文总结、课程问答等固定 skill；智能识别低置信度时进入动态规划 skill，先规划报告结构再生成内容。
- **模型质量门控**：使用模型对草稿进行多维审稿，输出结构完整度、资料依据、具体程度、可提交程度、风险分和总分；低于阈值时自动改写一次，仍未达标则标记为“需人工审核修改”。
- **端到端可观测性**：Java 后端保存路由结果、检索证据、质量指标和 Agent Trace；前端展示 AI 工作流程，监控页展示成功率、P95 耗时、改写率、阶段耗时和最近任务。
- **真实数据评测闭环**：支持从真实任务数据导出 JSONL，计算 Skill Routing Accuracy、Recall@k、MRR、章节完整率、证据覆盖率、改写触发率等指标。
- **Docker 一键启动**：前端、后端、Agent、MySQL、Redis、ChromaDB 通过 `docker compose` 编排，方便本地演示。

## 系统架构

```text
Next.js Frontend
  |  作业管理 / 资料上传 / AI 工作流程 / 报告编辑 / 数据监控
  v
Spring Boot Backend
  |  任务编排 / SSE 日志 / 报告版本 / MySQL 持久化 / Redis 预留
  v
FastAPI Python Agent
  |  Skill Routing / RAG / ReAct-lite Loop / 质量审稿 / 自动改写
  v
ChromaDB + DeepSeek OpenAI-compatible API + DashScope Embedding
```

数据存储：

- **MySQL**：作业、资料、报告、Agent 任务、任务日志、检索证据、质量指标、Trace。
- **ChromaDB**：资料切分后的向量检索库。
- **Redis**：已接入后端依赖，当前预留给运行中任务状态、最近访问上下文和 SSE 重连恢复。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS, lucide-react |
| Backend | Spring Boot 3, Java 21, MyBatis Plus, MySQL, Redis, SSE, SLF4J |
| Agent | FastAPI, Pydantic, OpenAI-compatible SDK, ChromaDB, pypdf |
| LLM Provider | DeepSeek OpenAI-compatible API, DashScope Embedding |
| DevOps | Docker Compose |

## 核心流程

1. 学生创建作业，填写课程、标题、截止时间、任务说明。
2. 上传课程资料、论文、实验要求或项目文档。
3. 后端创建异步生成任务，并通过 SSE 推送执行日志。
4. Python Agent 解析资料，写入 ChromaDB。
5. Agent 执行 Skill Routing：
   - 手动选择：直接进入指定 skill。
   - 智能识别：规则优先，必要时 LLM 分类。
   - 低置信度：进入 `dynamic_planner`。
6. Agent 检索相关资料片段，生成 Markdown 初稿。
7. 模型质量审稿器返回多维评分、问题列表和改写重点。
8. 若未达阈值，Agent 自动改写一次。
9. Java 后端保存最终草稿、检索证据、质量指标和 Trace。
10. 前端展示报告草稿、AI 工作流程和数据监控指标。

## Agent Loop

当前 Agent loop 默认最多执行 4 个关键步骤：

```text
search_materials -> build_report_draft -> check_report_quality -> rewrite_report(optional)
```

每一步都会记录：

- `step_index`
- `stage`
- `tool_name`
- `input_summary`
- `output_summary`
- `status`
- `duration_ms`

质量审稿返回：

- `structure_score`
- `grounding_score`
- `specificity_score`
- `readiness_score`
- `risk_score`
- `total_score`
- `decision`: `PASS` / `NEEDS_REWRITE` / `NEEDS_USER_INPUT`

前端会把状态翻译成面向学生的中文标签，例如“需人工审核修改”“需补充资料”。

## 页面功能

- **作业资料工作台**：创建作业、选择作业、上传资料、生成报告。
- **AI 工作流程**：展示 Skill 路由、资料解析、RAG 检索、报告生成、质量检查、自动改写、完成状态。
- **报告草稿**：支持预览、编辑、保存、导出 Markdown。
- **弹窗式作业队列**：从顶部统计卡片进入任务列表，切换当前展示作业。
- **数据监控页**：展示 Agent Loop / RAG / Skill Routing 的运行画像，包括：
  - 任务总数、成功率、平均耗时、P95 耗时
  - 动态规划兜底率、自动改写率
  - 阶段平均耗时
  - Skill 命中分布
  - 最近任务
  - 资料与报告资产统计

## 快速启动

### 1. 准备环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入 DeepSeek API Key 和 DashScope Embedding API Key：

```env
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=your_deepseek_api_key
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v2
DASHSCOPE_API_KEY=your_dashscope_api_key
QUALITY_PASS_SCORE=0.70
```

> 真实密钥只放本地 `.env`，不要提交到 GitHub。

### 2. 启动服务

```bash
docker compose up --build
```

默认服务地址：

- Frontend: http://localhost:3000
- Backend API: http://localhost:8080
- Python Agent Docs: http://localhost:8000/docs
- ChromaDB: http://localhost:8001

Docker 网络内 Agent 访问 ChromaDB 使用容器端口 `8000`；宿主机本地开发默认访问映射端口 `8001`。

### 3. 基本使用

1. 打开 `http://localhost:3000`。
2. 点击“新建”创建作业。
3. 上传资料。
4. 点击“生成当前报告草稿”。
5. 在 AI 工作流程中观察路由、检索、质量检测和改写过程。
6. 在报告草稿区域继续编辑和保存。
7. 进入数据监控页查看真实任务指标。

## 常用命令

前端类型检查：

```bash
cd frontend
npm.cmd run typecheck
```

后端打包：

```bash
cd backend-java
mvn -q -DskipTests package
```

Python Agent 单测：

```bash
python -m unittest discover agent-python/tests
```

查看 Docker 服务：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f backend-java
docker compose logs -f agent-python
docker compose logs -f frontend
```

## API 概览

Backend：

- `GET /api/dashboard/summary`
- `GET /api/assignments`
- `POST /api/assignments`
- `PUT /api/assignments/{id}`
- `DELETE /api/assignments/{id}`
- `GET /api/assignments/{id}`
- `POST /api/assignments/{id}/materials`
- `DELETE /api/materials/{id}`
- `POST /api/assignments/{id}/generate`
- `GET /api/assignments/{id}/tasks`
- `POST /api/tasks/{taskId}/retry`
- `GET /api/tasks/{taskId}/events`
- `GET /api/monitoring/overview`
- `GET /api/reports/{assignmentId}`
- `PUT /api/reports/{reportId}`
- `GET /api/reports/{assignmentId}/export`

Agent：

- `GET /health`
- `GET /agent/skills`
- `POST /agent/index`
- `POST /agent/generate-report`

## Eval Harness

评测脚本位于 `agent-python/evals`，支持离线统计：

- `Skill Routing Accuracy`
- `Recall@k`
- `MRR`
- `Section Completeness`
- `Citation / Evidence Coverage`
- `Rewrite Trigger Rate`

示例：

```bash
cd agent-python
python evals/eval_harness.py evals/sample_results.jsonl --k 5
```

从真实任务数据导出 JSONL 后再评测：

```bash
python evals/export_task_results.py tasks.json evals/task_results.jsonl
python evals/eval_harness.py evals/task_results.jsonl --k 5
```

## 项目结构

```text
.
├── frontend/              # Next.js 前端工作台与监控页
├── backend-java/          # Spring Boot 后端编排、持久化、SSE
├── agent-python/          # FastAPI Agent、RAG、Skill、质量审稿
│   ├── app/
│   │   ├── main.py
│   │   ├── agent_runtime.py
│   │   └── skills/
│   ├── evals/
│   └── tests/
├── docker-compose.yml
├── ROADMAP.md
└── README.md
```

## 适合写进简历的描述

> 基于 Spring Boot + FastAPI + Next.js 构建课程作业 Agent 工作台，接入 DeepSeek OpenAI-compatible API、DashScope Embedding 和 ChromaDB，实现资料解析、RAG 检索、任务类型识别、模型质量门控、自动改写和报告版本保存；基于 MySQL 持久化 Agent Trace、检索证据和质量指标，构建可观测数据监控页，支持任务完成率、质量通过率、P95 耗时、改写率、阶段耗时和检索指标统计。

## 安全说明

- `.env`、`.docker-config/`、`.m2/`、`node_modules/`、`.next/`、`target/`、上传资料和本地缓存均已加入忽略规则。
- 仓库只保留 `.env.example` 作为配置模板。
- 日志不输出 API Key、完整 Prompt 或完整资料正文，只输出摘要、数量、阶段、耗时和错误类型。
