# FZU Homework Assistant Roadmap

这份文档是给“下次继续开发”准备的上下文交接。下次进入项目时，优先读这里，再读 `README.md`，基本就能快速理解当前系统状态、关键设计口径和下一步任务。

## 当前项目定位

项目目标：做一个适合简历展示的 **可观测课程作业 Agent 工作台**。

核心不是“简单生成一段报告”，而是展示一个完整的大模型应用链路：

```text
作业管理 -> 资料上传 -> 资料解析/向量化 -> Skill Routing -> RAG 检索
-> 报告生成 -> 模型质量审稿 -> 自动改写 -> 后端保存草稿
-> 前端 AI 流程展示 -> 监控页统计真实任务数据
```

面向用户：福州大学学生，所以前端文案应优先使用中文、学生能理解的表达。后端和数据库可以保留工程状态码。

## 技术栈

- `frontend`：Next.js 14 + TypeScript + Tailwind CSS + lucide-react
- `backend-java`：Spring Boot 3 + Java 21 + MyBatis Plus + MySQL + Redis + SSE + SLF4J
- `agent-python`：FastAPI + Pydantic + OpenAI-compatible SDK + ChromaDB + pypdf
- LLM 默认：DeepSeek OpenAI-compatible API，Embedding 默认：DashScope text-embedding
- 本地编排：Docker Compose

## 当前已完成能力

### 1. 作业资料工作台

已实现：

- 新建 / 编辑 / 删除作业
- 弹窗式作业队列
- 上传 / 删除资料
- 生成报告草稿
- Markdown 预览、编辑、保存、导出
- 顶部统计卡片弹窗
- 主要工作区布局：左侧作业信息、任务历史、相关资料；右侧重点展示 AI 工作流程；报告草稿单独一栏展示

重要文件：

- `frontend/app/page.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`

### 2. Skill Routing

已实现：

- 固定 skill：
  - `lab_report`
  - `paper_summary`
  - `course_qa_report`
- 兜底 skill：
  - `dynamic_planner`
- `AUTO` 智能识别：
  - 规则关键词优先
  - 必要时 LLM 分类
  - 高置信命中固定 skill
  - 低置信进入 `dynamic_planner`
- 返回并持久化：
  - `resolved_skill_id`
  - `routing_mode`
  - `routing_confidence`
  - `routing_reason`

重要文件：

- `agent-python/app/main.py`
- `agent-python/app/skills/*`
- `backend-java/src/main/java/com/fzu/homework/service/AgentWorkflowService.java`

### 3. ReAct-lite Agent Loop

已实现轻量自研 loop，不引入完整 Agents SDK。

当前 loop：

```text
search_materials
-> build_report_draft
-> check_report_quality
-> rewrite_report(optional, at most once)
```

每一步输出 `agent_trace`：

- `step_index`
- `stage`
- `tool_name`
- `input_summary`
- `output_summary`
- `status`
- `duration_ms`

注意：

- 当前不是完全开放式 ReAct，不让模型无限选择工具。
- 默认最多 4 步，避免失控。
- Agent 不直接写业务数据库，最终报告仍由 Java 后端保存。

重要文件：

- `agent-python/app/agent_runtime.py`
- `agent-python/app/main.py`
- `agent-python/tests/test_agent_runtime.py`

### 4. RAG 与资料索引

已实现：

- PDF / Markdown / TXT 资料上传
- Python Agent 解析和切分资料
- embedding 写入 ChromaDB
- 生成报告前先检索 top-k 资料片段
- 返回 `retrieved_evidence`：
  - `chunk_id`
  - `material_id`
  - `filename`
  - `score`
  - `excerpt`

注意：

- 课程作业通常基于一个或少量文档，所以不再把“引用覆盖率 100%”作为前端核心展示指标。
- 检索证据更适合用于后端记录、监控和 eval，而不是在主工作台制造无意义 KPI。

### 5. 模型质量门控

已实现：

- 模型作为“质量审稿器”对草稿评分
- 评分维度：
  - `structure_score`
  - `grounding_score`
  - `specificity_score`
  - `readiness_score`
  - `risk_score`
  - `total_score`
  - `pass_score`
- 决策：
  - `PASS`
  - `NEEDS_REWRITE`
  - `NEEDS_USER_INPUT`
- 默认通过阈值：
  - `QUALITY_PASS_SCORE=0.70`
- 低于阈值：
  - 自动改写一次
  - 改写后仍低于阈值时，报告草稿仍保存，但任务标记为 `NEEDS_REWRITE`

前端中文展示：

- `PASS` / `SUCCEEDED`：已完成
- `NEEDS_REWRITE`：需人工审核修改
- `NEEDS_USER_INPUT`：需补充资料

重要设计口径：

- “任务完成”表示技术流程完成。
- “质量通过”表示模型质量门控达标。
- 两者不要混在一起。低分草稿可以保存，但 UI 必须提示需要人工审核修改。

重要文件：

- `agent-python/app/agent_runtime.py`
- `backend-java/src/main/java/com/fzu/homework/service/AgentWorkflowService.java`
- `backend-java/src/main/java/com/fzu/homework/service/TaskLogService.java`
- `frontend/app/page.tsx`

### 6. 后端编排与日志

已实现：

- Java 后端创建 `AgentTask`
- 调用 Python Agent 的索引和生成接口
- 保存报告版本
- 保存实际 skill、路由原因、检索证据、质量指标、Agent Trace
- SSE 推送任务日志
- 失败时记录 SLF4J 异常日志，并给前端友好错误

任务状态重点：

- `QUEUED`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `NEEDS_REWRITE`
- `NEEDS_USER_INPUT`

注意：

- `NEEDS_REWRITE` 和 `NEEDS_USER_INPUT` 是终态，不是运行中状态。
- SSE 在 `done` 阶段遇到这些终态时应结束连接。

### 7. 数据监控页

已实现 `GET /api/monitoring/overview` 和前端监控页。

当前展示：

- 总任务数
- 生成成功率
- 平均耗时
- P95 耗时
- 动态规划兜底率
- 自动改写率
- 平均检索片段数
- 阶段平均耗时
- Skill 命中分布
- 最近任务
- 资料与报告资产

重要文件：

- `backend-java/src/main/java/com/fzu/homework/controller/MonitoringController.java`
- `backend-java/src/main/java/com/fzu/homework/service/MonitoringService.java`
- `frontend/app/page.tsx`

当前口径注意：

- `successRate` 目前按 `SUCCEEDED / totalTasks` 算，`NEEDS_REWRITE` 不算成功。
- 如果后续想展示“草稿生成率”，可以新增一个 KPI，不要混用成功率。

### 8. Eval Harness

已实现：

- `agent-python/evals/eval_harness.py`
- `agent-python/evals/export_task_results.py`
- `agent-python/evals/README.md`

支持指标：

- Skill Routing Accuracy
- Recall@k
- MRR
- Section Completeness
- Citation / Evidence Coverage
- Rewrite Trigger Rate

下一步应把真实任务数据自动导出和人工标注数据打通。

## 当前验证命令

提交前建议跑：

```powershell
npm.cmd run typecheck
```

```powershell
mvn -q "-Dmaven.repo.local=D:\HW Assistant\.m2" -DskipTests package
```

```powershell
python -m unittest discover agent-python\tests
```

Docker：

```powershell
$env:DOCKER_CONFIG=(Resolve-Path .docker-config).Path
docker compose up --build -d backend-java frontend agent-python
docker compose ps
```

常用健康检查：

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8080/api/monitoring/overview
```

## 下次优先开发建议

### P0：把“质量门控”做得更产品化

当前已能评分和标记 `NEEDS_REWRITE`，下一步建议：

- 前端在报告草稿顶部显示质量结果卡片：
  - 总分
  - 通过阈值
  - 中文状态
  - 模型评价摘要
  - 问题列表 `issues`
  - 改写建议 `rewrite_focus`
- 对 `NEEDS_REWRITE` 提供按钮：
  - “再次优化草稿”
  - “标记为已人工审核”
- 后端新增再次优化接口：
  - `POST /api/tasks/{taskId}/rewrite`
  - 或 `POST /api/assignments/{id}/improve-report`

推荐理由：

- 这是当前项目最像 Agent 产品的地方。
- 也能解释为什么低分草稿仍保存：保存的是可编辑草稿，不代表质量通过。

### P0.5：降低单 Agent 自评虚高

当前质量门控属于 **Planner-Generator-Evaluator inspired single-agent harness**：生成、评审和改写都在同一个 Agent Runtime 内完成。它适合作为简历项目里的自动质量门控，但不要把它描述成严格客观评测。后续如果继续增强，优先做三件事：

1. **Evaluator 换成不同模型或不同 prompt 角色**

   例如 Generator 使用 DeepSeek，Evaluator 使用另一个模型，或者至少使用更严格的审稿 system prompt，降低同源偏差。

2. **给总分加硬性上限**

   当前总分由结构、证据、具体性、可提交性、低风险五个维度加权得到。后续可以加入硬规则，避免模型自评虚高：

   ```text
   citation_coverage < 0.4 时，total_score 最高只能 0.65
   retrieved_chunks = 0 时，不能 PASS
   section_completeness < 1.0 时，不能 PASS
   ```

3. **做一个小型人工标注 eval set**

   不用很多，20-50 条就足够支撑简历项目展示。用于测 `Hit Rate@5`、`Recall@5`、`Section Completeness`、人工可接受率，并和线上 `quality_metrics_json` 对照。

推荐理由：

- 这能把“模型自己评自己”的风险讲清楚，也能展示工程上如何用本地规则、人工 gold set 和模型审稿组合成更可靠的评测闭环。
- 对简历项目来说，这比引入真正多 Agent 或 LangGraph 更划算，工作量可控，展示价值高。

### P1：Eval 数据闭环

当前监控页已有运行指标，但 Recall@k / MRR 还需要真实标注。

下一步建议：

- 新增简单标注表或 JSON 文件：
  - assignmentId
  - expectedSkillId
  - relevantChunkIds
  - expectedSections
- 在前端或脚本中导出任务结果
- 用真实数据跑：
  - Skill Routing Accuracy
  - Recall@k
  - MRR
  - Rewrite Trigger Rate
- 把评测结果接入监控页的次级区域

推荐理由：

- 简历上“有真实数据支撑”比只写 RAG 更有说服力。

### P2：Redis Memory 落地

Redis 已作为依赖接入，但目前主要是预留。

建议实现：

- `task:status:{taskId}`：缓存运行中任务状态
- `recent:assignments`：记录最近访问作业
- SSE 重连时：
  - 先读 Redis 最近状态
  - 再回查 MySQL 历史日志
- 前端刷新页面后恢复最近作业和当前任务状态

简历表达：

> 基于 Redis 缓存任务运行状态和最近访问上下文，提升 Agent 工作台状态恢复与 SSE 重连体验。

### P3：MCP Server 包装

本阶段还没有真正做 MCP。

可以做一个轻量 MCP Server，把已有业务能力包装成 tools：

- `list_assignments`
- `get_assignment_detail`
- `search_materials`
- `get_report`
- `get_monitoring_overview`
- `export_eval_dataset`

推荐做法：

- 先不要改主流程。
- 作为独立 `mcp-server` 模块包装现有 HTTP API。
- README 中说明“通过 MCP 将作业系统能力暴露给外部 Agent 调用”。

### P4：更多作业 Skill

可新增：

- `code_review_report`：代码阅读 / 实验复现报告
- `ppt_outline`：汇报 PPT 大纲
- `literature_review`：文献综述
- `exam_review_notes`：课程复习笔记
- `debug_explainer`：编程作业 Debug 讲解

新增 skill 时遵守现有目录结构：

```text
agent-python/app/skills/<skill_id>/
  skill.json
  SKILL.md
```

## 容易踩坑的地方

### 1. 编码乱码

之前 `README.md` 和 `ROADMAP.md` 出现过中文乱码。后续编辑时注意：

- 文件使用 UTF-8
- 不要用会误判编码的编辑器保存
- 提交前打开 README / ROADMAP 看一下中文是否正常

### 2. 不要提交密钥和本地缓存

不要提交：

- `.env`
- `.docker-config/`
- `.m2/`
- `node_modules/`
- `.next/`
- `target/`
- `storage/`
- `__pycache__/`

检查：

```powershell
git status --ignored
git ls-files .env .docker-config .m2
```

### 3. Docker on Windows 权限

有些 Docker 命令需要提升权限。常用：

```powershell
$env:DOCKER_CONFIG=(Resolve-Path .docker-config).Path
docker compose ps
docker compose logs --tail=80 backend-java
docker compose logs --tail=80 agent-python
```

### 4. DashScope 网络/Embedding 问题

如果报告生成失败，优先看：

- `docker compose logs --tail=100 agent-python`
- `docker compose logs --tail=100 backend-java`
- `.env` 中 `DASHSCOPE_API_KEY`
- `LLM_BASE_URL`
- `EMBEDDING_MODEL`

前端显示的友好错误可能是：

- Embedding 服务连接失败
- 缺少 API Key
- 向量化批次过大

### 5. 质量检测耗时

现在质量检测包含模型审稿，因此不应长期为 `0ms`。如果又出现 0 或 1ms，要检查：

- 是否模型审稿失败后走了 fallback
- `agent_trace_json`
- `agent-python/app/agent_runtime.py`

## 当前 GitHub 状态

远程仓库：

```text
https://github.com/panding999/HW-assistant.git
```

当前主分支：

```text
main
```

最近一次大提交：

```text
feat: add observable homework agent workflow
```

## 下次继续时推荐开场

可以直接对 Codex 说：

> 继续完善 HW Assistant，先读 ROADMAP.md 和 README.md。优先做 P0：质量门控产品化，把总分、问题列表、改写建议展示到报告区域，并增加再次优化草稿入口。

或者：

> 继续完善 HW Assistant，先读 ROADMAP.md。今天优先做 Eval 数据闭环，把真实任务导出、人工标注和监控页评测指标接起来。
