# FZU Homework Assistant

面向课程作业资料管理与报告生成的 AI 工作台。项目由 Next.js 前端、Spring Boot 编排后端、FastAPI Agent 服务、MySQL、Redis 和 ChromaDB 组成，支持创建作业、上传资料、RAG 检索、Skill Routing、动态规划生成报告，并在前端展示 AI 工作流程日志。

## 功能亮点

- 作业管理：创建课程作业，维护标题、课程、截止时间、作业说明和任务类型。
- 资料上传：支持 PDF / Markdown 资料上传，并由 Python Agent 解析、切分、向量化入库。
- RAG 报告生成：基于作业说明和已上传资料检索相关片段，生成 Markdown 报告草稿。
- Skill Routing：支持手动选择任务类型，也支持智能识别并自动路由到合适的 skill。
- Dynamic Planner：当智能识别无法高置信命中固定 skill 时，进入动态规划，先设计报告结构再生成内容。
- AI 工作流程：前端展示资料解析、Skill 路由、RAG 检索、报告生成、完成等任务日志。
- 报告编辑：前端支持预览、编辑、保存和导出生成后的 Markdown 报告。
- Eval Harness：提供轻量评测脚本，用于统计 RAG 和 Skill Routing 相关指标。

## 当前 Skill

项目采用目录式 skill package，每个 skill 包含 `skill.json` 元数据和 `SKILL.md` 详细说明：

```text
agent-python/app/skills/
  lab_report/
    skill.json
    SKILL.md
  paper_summary/
    skill.json
    SKILL.md
  course_qa_report/
    skill.json
    SKILL.md
  dynamic_planner/
    skill.json
    SKILL.md
```

当前支持：

- `lab_report`：实验报告，生成实验目的、实验原理、实验步骤、核心代码分析和实验总结。
- `paper_summary`：论文总结，生成研究背景、问题定义、方法、创新点、实验结果、局限和汇报提纲。
- `course_qa_report`：课程问答汇报，根据课程资料和问题生成讲解稿或汇报材料。
- `dynamic_planner`：智能识别低置信度时使用，先规划动态章节结构，再基于资料生成通用报告。

`dynamic_planner` 不作为前端手动选项展示，只作为“智能识别”的兜底执行路径。

## 技术栈

- `frontend`：Next.js 14 + TypeScript + Tailwind CSS + lucide-react。
- `backend-java`：Spring Boot 3 + MyBatis Plus + MySQL + Redis + Server-Sent Events。
- `agent-python`：FastAPI + OpenAI-compatible SDK + ChromaDB + pypdf。
- `evals`：Python JSONL 评测脚本。
- `docker-compose.yml`：本地一键启动前端、后端、Agent、数据库、缓存和向量库。

## 快速启动

1. 复制环境变量模板：

```bash
cp .env.example .env
```

2. 编辑 `.env`，填入你的 DashScope API Key：

```env
DASHSCOPE_API_KEY=your_dashscope_api_key
```

3. 启动全部服务：

```bash
docker compose up --build
```

4. 打开服务地址：

- 前端：http://localhost:3000
- Java API：http://localhost:8080
- Python Agent 文档：http://localhost:8000/docs
- ChromaDB：http://localhost:8001

## 核心流程

1. 创建作业，选择“智能识别”或手动选择任务类型。
2. 上传 PDF / Markdown 资料。
3. 发起报告生成任务。
4. Java 后端创建任务并调用 Python Agent。
5. Python Agent 执行 Skill Routing：
   - 手动选择：直接进入对应 skill。
   - 智能识别：规则优先，LLM 兜底分类。
   - 置信度高：进入固定 skill。
   - 置信度低：进入 `dynamic_planner`。
6. Agent 检索相关资料并生成 Markdown 报告。
7. Java 后端保存报告、保存实际执行 skill，并通过 SSE 推送日志。
8. 前端展示 AI 工作流程、报告预览和编辑界面。

任务相关接口：

- 创建生成任务：`POST /api/assignments/{id}/generate`
- 订阅任务日志：`GET /api/tasks/{taskId}/events`
- Agent 生成报告：`POST /agent/generate-report`
- Agent Skill 列表：`GET /agent/skills`

## Eval Harness

评测脚本位于 `agent-python/evals`，当前用于离线统计：

- `Recall@k`
- `MRR`
- `Skill Routing Accuracy`
- `Section Completeness`
- `Groundedness`

运行示例：

```bash
cd agent-python
python evals/eval_harness.py evals/sample_results.jsonl --k 5
```

这部分目前是轻量离线 harness，后续可以接入真实生成任务，形成更适合简历展示的数据指标。

## 环境变量与安全

真实密钥只放在本地 `.env` 文件中，不要提交到 GitHub。仓库只保留 `.env.example` 作为配置模板。

默认使用 DashScope / Qwen 的 OpenAI 兼容接口：

```env
LLM_PROVIDER=qwen
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
EMBEDDING_MODEL=text-embedding-v2
DASHSCOPE_API_KEY=your_dashscope_api_key
```

如果后续迁移到其他 OpenAI 兼容服务，更新 `.env` 中的 `LLM_BASE_URL`、`LLM_MODEL` 和对应 API Key 即可。

## 项目进度

本版本的实现情况和下一步计划记录在 [ROADMAP.md](ROADMAP.md)。

## 上传到 GitHub 前检查

确认 `.env`、`.m2/`、`.docker-config/`、`node_modules/`、`.next/`、`target/` 等本地文件没有被提交：

```bash
git status --ignored
```

推荐提交命令见 [ROADMAP.md](ROADMAP.md) 的“上传指令”部分。
