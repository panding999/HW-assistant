# FZU Homework Assistant

AI 作业资料与实验报告工作台。当前 MVP 包含 Next.js 前端、Spring Boot 编排后端、FastAPI Agent 服务、MySQL、Redis 和 ChromaDB，可用于创建作业、上传 PDF/Markdown 资料、生成报告并实时查看任务日志。

## 功能概览

- 作业管理：创建作业并维护作业说明。
- 资料上传：支持 PDF 和 Markdown 资料上传。
- AI 生成：通过 DashScope/Qwen 的 OpenAI 兼容接口生成实验报告。
- 实时日志：后端通过 Server-Sent Events 推送任务执行日志。
- 报告编辑：前端支持查看和编辑 Markdown 报告。

## 技术栈

- `frontend`：Next.js 14 + TypeScript + Tailwind CSS。
- `backend-java`：Spring Boot 3 + MyBatis Plus + MySQL + Redis。
- `agent-python`：FastAPI + OpenAI Python SDK + ChromaDB。
- `docker-compose.yml`：本地一键启动前端、后端、Agent、数据库和向量库。

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

1. 创建作业。
2. 上传 PDF 或 Markdown 资料。
3. 发起报告生成任务。
4. 通过实时日志观察任务进度。
5. 查看并编辑生成的 Markdown 报告。

任务相关接口：

- 创建生成任务：`POST /api/assignments/{id}/generate`
- 订阅任务日志：`GET /api/tasks/{taskId}/events`

## 环境变量与安全

真实密钥只放在本地 `.env` 文件中，不要提交到 GitHub。仓库中只保留 `.env.example` 作为配置模板。

当前默认使用 DashScope/Qwen：

```env
LLM_PROVIDER=qwen
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
EMBEDDING_MODEL=text-embedding-v2
DASHSCOPE_API_KEY=your_dashscope_api_key
```

如果后续要迁移到其他 OpenAI 兼容服务，更新 `.env` 中的 `LLM_BASE_URL`、`LLM_MODEL` 和对应 API Key 即可。

## 上传到 GitHub 前检查

```bash
git status --ignored
git add README.md .gitignore .env.example docker-compose.yml frontend backend-java agent-python
git status --short
```

确认 `.env`、`.m2/`、`.docker-config/`、`node_modules/`、`.next/`、`target/` 等本地文件没有出现在待提交列表后，再提交和推送。
