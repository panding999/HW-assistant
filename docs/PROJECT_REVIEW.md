# 项目代码审查结果

审查时间：2026-05-12  
审查范围：`frontend`、`backend-java`、`agent-python`、`docker-compose`、评测脚本与当前 Agent 生成链路。

## 总体结论

当前项目的核心亮点已经比较清楚：基于 RAG 的资料检索、任务类型识别、Agent 生成、质量门控、自动改写、任务日志和数据监控。整体可以作为一个“可观测的作业报告生成 Agent 系统”来讲。

本轮已修复部分会直接影响测试数据可信度和中文展示体验的问题：生成前会重建当前作业的 ChromaDB collection，删除作业时会请求清理向量集合，RAG 检索改为确定性多路 query 扩展，任务类型识别原因改为中文输出，监控指标拆分为任务完成率、质量通过率、改写触发率和改写采纳率。后续迭代又补充了质量反馈驱动的二次检索闭环、Python Agent 阶段事件流、再次优化版本保护、重试保留原任务类型和前端日志刷新兜底。

仍建议在简历和面试里保持克制：质量评分和引用覆盖仍是工程信号，不要包装成事实准确率；当前已做到逐阶段/逐工具完成事件流，但不是逐 token 流式输出，也不是所有阶段都有 start event。

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

### 2. 后端任务日志已接入 Agent 阶段事件流，但仍不是逐 token

涉及文件：
- `backend-java/src/main/java/com/fzu/homework/service/AgentWorkflowService.java`
- `agent-python/app/agent_runtime.py`
- `frontend/app/page.tsx`

当前状态：
- Python Agent 新增 `/agent/generate-report-stream` 和 `/agent/improve-report-stream`。
- Python 通过 NDJSON 输出 `stage`、`final`、`error` 事件。
- Java 后端优先读取流式事件，收到阶段完成事件后立即写入 `agent_task_logs` 并通过 SSE 推给前端。
- 非流式接口仍保留作为 fallback。

剩余风险：
- 当前事件是“阶段完成事件”，不是 token 级流式，也不是所有阶段都有“开始事件”。
- 自动改写这类阶段耗时较长时，前端需要根据上一阶段结果推断“自动改写进行中”。
- 前端已增加运行中任务定时刷新，避免 SSE 收尾断连导致最终 trace 或 `done` 未显示。

建议：
- 面试中表述为“逐阶段/逐工具级事件流”，不要说“逐 token”。
- 后续可补齐 `stage_start` 事件，让前端不再依赖推断运行态。

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

### 5. 已增加质量反馈驱动的二次检索，但仍限制为轻量闭环

涉及文件：
- `agent-python/app/agent_runtime.py`
- `agent-python/app/main.py`

当前状态：
- 当质量门控返回 `NEEDS_REWRITE`，且 grounding 偏低、章节缺失、证据过少或质量问题指向证据不足时，会触发 `reflect_retrieval_needs`。
- Agent 根据缺失章节、质量问题、rewrite focus、作业标题、课程和 Skill query hint 构造补充 query。
- 补充检索结果按 `chunk_id` 去重合并，若有新增证据，则重生成候选稿并重新质量评估。
- 候选稿评分更高才采纳，否则保留原稿并继续原有 rewrite 保护。

边界：
- 严格限制最多 1 轮补充检索，避免开放式 Agent 循环。
- `NEEDS_USER_INPUT` 不触发二次检索，避免资料明显不足时硬编。

建议：
- 面试中可以称为“轻量 Agentic RAG：质量反馈驱动的一轮补充检索闭环”。
- 不要包装成完整 LangGraph / Graph RAG / 多轮自主 Agent。

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
- 当前已支持基于质量问题的一轮补充检索，但仍不是开放式多轮规划，也不是 claim-level 检索。

建议：
- 继续保持最多 1 轮补充检索，避免自由 LLM query rewrite 失控。
- 后续如果要进一步提升事实可靠性，可以做 claim-level query：从报告断言中抽取需要支撑的 claim，再逐条检索和校验。

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
- 当前再次优化已使用上一版保存质量分作为 baseline，不再重复给原稿打分，避免 evaluator 波动影响版本采纳。
- 后续如果要继续增强，可以做评分缓存、多评估器投票、claim-evidence 对齐和小规模人工 gold set。

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
- 现有逻辑已经把“检索片段不足”纳入补充检索判断，后续可继续把引用覆盖率、claim 支撑率等信号接入 rewrite 判断。
- 如果后续不再需要独立参数，可以删除该参数，保持函数干净。

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
- “自动改写主要处理结构和表达问题；证据不足时我已经做了一轮补充检索闭环，后续会继续往 claim-level 检索和证据校验优化。”
- “质量门控分数会受 LLM-as-judge 波动影响，所以我把它定位为工程信号；再次优化用上一版保存分数做 baseline，后续会做评分缓存、多评估器和断言级证据校验。”
- “监控页统计任务耗时、阶段耗时、Skill 分布、改写率和检索片段数，用来支撑我调参和评估系统质量。”

不建议夸大：
- 不要说“事实准确率 100%”。
- 不要把 citation coverage 说成事实正确率。
- 不要说 Agent 阶段是逐 token 流式执行，当前是逐阶段/逐工具完成事件 + SSE 展示。
