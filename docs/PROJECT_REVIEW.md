# 项目代码审查结果

审查时间：2026-05-12  
审查范围：`frontend`、`backend-java`、`agent-python`、`docker-compose`、评测脚本与当前 Agent 生成链路。

## 总体结论

当前项目的核心亮点已经比较清楚：基于 RAG 的资料检索、任务类型识别、Agent 生成、质量门控、自动改写、任务日志和数据监控。整体可以作为一个“可观测的作业报告生成 Agent 系统”来讲。

本轮已修复部分会直接影响测试数据可信度和中文展示体验的问题：生成前会重建当前作业的 ChromaDB collection，删除作业时会请求清理向量集合，RAG 检索改为确定性多路 query 扩展，任务类型识别原因改为中文输出，监控指标拆分为任务完成率、质量通过率、改写触发率和改写采纳率。

仍建议在简历和面试里保持克制：质量评分和引用覆盖仍是工程信号，不要包装成事实准确率；Agent 内部 trace 仍是后端拿到结果后的可观测记录，不是逐工具实时流式回调。

## 高优先级问题

### 1. ChromaDB 向量数据一致性

涉及文件：
- `backend-java/src/main/java/com/fzu/homework/service/AssignmentService.java`
- `agent-python/app/main.py`

当前状态：
- `/agent/index` 已改为生成前重建 `assignment_{id}` collection。
- 后端删除作业时会调用 Agent 删除对应 collection。

剩余风险：
- 删除单个资料时暂未单独删除该资料对应 chunk，但下一次生成会全量重建 collection，能避免重新生成时被旧向量污染。
- 如果 Agent 服务不可用，后端删除作业仍会继续完成，只记录清理失败日志。

建议：
- 当前简历可表述为“按作业维度隔离并全量重建向量索引，降低历史资料污染”。
- 后续生产化可增加单资料级 chunk 删除和后台补偿任务。

### 2. 后端任务日志不是严格实时反映 Agent 内部阶段

涉及文件：
- `backend-java/src/main/java/com/fzu/homework/service/AgentWorkflowService.java`
- `agent-python/app/agent_runtime.py`
- `frontend/app/page.tsx`

现象：
- 后端先推送 `parse RUNNING`，索引完成后推 `parse SUCCEEDED`。
- 后端推送 `retrieve RUNNING` 后，马上进入 `/agent/generate-report` 这个同步 HTTP 调用。
- Python Agent 内部完成 retrieve、generate、quality、rewrite 后，一次性返回结果。
- 后端拿到最终结果后，才补推 `retrieve SUCCEEDED`、`skill SUCCEEDED`、`quality ...`、`rewrite ...`、`done ...`。

影响：
- 前端看起来有流程阶段，但 Agent 内部阶段不是边执行边推送，而是后端事后补日志。
- 如果生成耗时较长，用户会看到“正在生成”卡住，无法实时知道 RAG、质量检查、改写分别进行到哪里。

建议：
- 短期：文档中明确“后端以任务日志记录阶段，Agent trace 用于事后可观测分析”。
- 中期：把 Python Agent 拆成多个接口，后端逐步调用并逐步推 SSE。
- 或者让 Agent 支持 callback/webhook，把内部 trace 实时回传给后端。

### 3. 任务最终状态和作业状态语义不完全一致

涉及文件：
- `backend-java/src/main/java/com/fzu/homework/service/AgentWorkflowService.java`

现象：
- 即使质量门控返回 `NEEDS_REWRITE` 或 `NEEDS_USER_INPUT`，后端仍然执行：
  `assignment.setStatus("DONE")`
- 任务本身会记录 `NEEDS_REWRITE` / `NEEDS_USER_INPUT`。

影响：
- 作业列表看到的是 `DONE`，但任务日志显示“需要继续完善”。
- 对用户来说有一点割裂，监控统计也需要额外看 task status 才知道质量状态。

建议：
- 保留 task status 用于细粒度质量结果。
- Assignment 可以新增或使用更明确状态：`DONE`、`REVIEW_REQUIRED`、`NEEDS_INPUT`。
- 如果不改数据库，至少前端展示时优先展示最新 task status，而不是只看 assignment status。

### 4. 引用覆盖率计算偏粗，容易显得过高

涉及文件：
- `agent-python/app/agent_runtime.py`

现象：
- `calculate_citation_coverage` 通过检查 markdown 是否包含 filename 或 chunk_id 来计算覆盖率。
- 生成 prompt 主要要求 `[来源: filename]`，而不是每个 chunk 都引用。
- 如果只有一个文件名出现一次，多个证据片段的 coverage 也可能看起来很高。

影响：
- `citation_coverage` 不等价于“关键结论都有证据支撑”。
- 面试中如果把它说成严格 groundedness，容易被追问。

建议：
- 简历和面试里称为“引用覆盖信号”或“证据引用覆盖率”，不要称为事实准确率。
- 后续可要求模型输出 claim-evidence 对，然后计算“主张支撑率”。
- 或改成每个 evidence chunk 必须以 `[来源: filename#chunk_id]` 引用，再按 chunk_id 统计。

## 中优先级问题

### 5. 自动改写没有重新检索，无法解决“检索证据不够”的问题

涉及文件：
- `agent-python/app/agent_runtime.py`
- `agent-python/app/main.py`

现象：
- 自动改写复用第一次 RAG 的 `context_text`。
- 如果低分原因是检索片段不够、query 命中差、缺关键证据，改写只能在同一批材料上润色。

影响：
- 自动改写适合修结构、表达、章节完整度。
- 不适合修复召回不足或证据缺失。

建议：
- 把质量问题分成两类：
  - 表达/结构问题：走 rewrite。
  - 证据/召回问题：走 query expansion + re-retrieve。
- 已完成第一步：初始 RAG 已改为确定性多路 query 扩展和去重召回。
- 后续可增加“二次检索”阶段：根据 `issues` 和 `rewrite_focus` 生成补充 query，再重新检索。

### 6. RAG query 已采用确定性多路扩展，暂不做 LLM query rewrite

涉及文件：
- `agent-python/app/main.py`

现状：
- 检索 query 已拆成三路：
  - `assignment_query`：标题、课程、描述。
  - `skill_query`：Skill 标签、必要章节、query_hint。
  - `section_query`：必要章节和作业要求。
- 多路检索后按 `chunk_id` 去重，再按相似度分数截断到 `top_k`。

优点：
- 稳定、可解释、成本低，且比单 query 更容易覆盖不同资料区域。

不足：
- 仍不是基于质量问题的二次检索，也不是 claim-level 检索。

建议：
- 先不要做自由 LLM query rewrite，容易不可控。
- 后续如果召回不足，可以增加 issue query：根据质量检查指出的问题点生成补充 query。

### 7. 质量评分已改为独立审稿链路 + 本地加权

涉及文件：
- `agent-python/app/agent_runtime.py`
- `agent-python/app/main.py`

现状：
- 质量审稿可通过 `EVALUATOR_BASE_URL`、`EVALUATOR_MODEL`、`EVALUATOR_API_KEY` 单独配置 evaluator 模型。
- 未配置 evaluator 时回退默认生成模型，保证本地演示不被额外配置卡住。
- 模型返回 5 个维度分数和审稿意见，系统按本地权重重算 `total_score`。
- 质量结果会记录 `evaluator_model` 和 `evaluator_mode`，前端质量卡片展示审稿来源。

影响：
- 同一个生成模型“自己写、自己评”的同源偏差已降低。
- 分数仍是工程质量门控信号，不等价于最终事实准确率或教师评分。

建议：
- 面试中说“独立审稿模型 + 本地加权规则 + 版本保护”，不要说是严格客观测量。
- 后续如果要继续增强，可以做 claim-evidence 对齐、二次检索和小规模人工 gold set。

### 8. `dynamic_planner` 的中文展示已改为“动态任务规划”

涉及文件：
- `agent-python/app/skills/dynamic_planner/skill.json`
- `backend-java/src/main/java/com/fzu/homework/service/MonitoringService.java`
- `backend-java/src/main/java/com/fzu/homework/service/AgentWorkflowService.java`

当前状态：
- UI、后端日志和 Skill label 已改为“动态任务规划”。

剩余建议：
- 代码标识仍保留 `dynamic_planner`，用于兼容已有数据和测试。

- 简历里可写“动态 Skill Planner / 动态任务规划”，不要写“动态规划算法”。

### 9. 资料解析对 PDF 质量依赖较强，缺少空内容保护

涉及文件：
- `agent-python/app/main.py`

现象：
- PDF 通过 `pypdf` 提取文本。
- 扫描版 PDF 或公式/表格密集 PDF 可能提取为空或错乱。
- 后端只检查“有材料”，没有检查“成功索引到有效 chunk”。

影响：
- 用户上传了文件但实际没有可用证据，生成质量会不稳定。

建议：
- 如果 `chunks_indexed == 0`，后端直接失败并提示“资料无法提取文本”。
- 后续可接入 OCR 或对扫描 PDF 给出清晰提示。

### 10. 监控指标已拆分，但口径仍需在简历中说明

涉及文件：
- `backend-java/src/main/java/com/fzu/homework/service/MonitoringService.java`

现状：
- 后端已新增：
  - `taskCompletionRate`
  - `qualityPassRate`
  - `rewriteTriggerRate`
  - `rewriteAcceptRate`
- 保留旧的 `successRate` 和 `rewriteRate` 用于兼容前端旧字段。

影响：
- 如果产品定义是“成功生成但建议人工完善”，成功率会偏低。
- 如果产品定义是“完全通过质量门控才算成功”，则当前统计合理。

建议：
- 简历上优先写“任务完成率、质量通过率、改写触发率、改写采纳率、平均耗时”，不要只写“成功率”。

## 低优先级问题

### 11. `should_rewrite` 参数里 `evidence` 暂未使用

涉及文件：
- `agent-python/app/agent_runtime.py`

影响较小，但说明 rewrite 判断还没有用到证据数量、引用覆盖等信号。

建议：
- 如果保留参数，可以加入“检索片段不足时不改写，改走补资料/二次检索”的逻辑。
- 否则删除该参数，保持函数干净。

### 12. 前端 AgentQualityMetrics 类型缺少 `manual_review_reason`

涉及文件：
- `frontend/lib/types.ts`

现象：
- 后端 quality JSON 已包含 `manual_review_reason`，前端类型暂未声明。

影响：
- 当前前端主要显示 `quality_note`，不影响运行。
- 但后续如果要单独展示人工审核原因，会缺类型。

建议：
- 在 `AgentQualityMetrics` 中补充：
  `manual_review_reason?: string;`

### 13. 数据库约束偏少，主要依赖应用层删除

涉及文件：
- `backend-java/src/main/resources/schema.sql`

现状：
- 表之间没有外键级联。
- 删除作业时由 `AssignmentService` 手动删除材料、任务、日志、报告。

影响：
- 当前小项目可接受。
- 如果后续多个入口写数据库，可能出现孤儿数据。

建议：
- 面试里可以说“为了演示和部署简单，当前用应用层级联删除”。
- 生产化可以增加外键或统一事务边界。

## 面试时建议如何表述

可以强调：
- “我没有把 LLM 当黑盒直接生成，而是设计了任务类型识别、RAG 检索、质量门控、自动改写和可观测 trace。”
- “质量门控不是 100% 客观评分，而是模型审稿 + 本地规则兜底，用于工程上的自动化判断。”
- “自动改写只处理结构和表达问题；证据不足更适合走二次检索或补充材料，这是我后续优化方向。”
- “监控页统计任务耗时、阶段耗时、Skill 分布、改写率和检索片段数，用来支撑我调参和评估系统质量。”

不建议夸大：
- 不要说“事实准确率 100%”。
- 不要把 citation coverage 说成事实正确率。
- 不要说 Agent 阶段是完全实时流式执行，当前是后端 SSE + 事后 trace 汇总。
