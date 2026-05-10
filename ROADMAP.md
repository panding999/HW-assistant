# Project Roadmap

这个文档用于记录当前版本已经完成的功能、尚未完成的计划，以及下一次继续开发时可以优先询问和推进的方向。

## 本版本完成内容

### 1. Skill Routing v1

- 已在作业模型中加入 `skillId` 和 `resolvedSkillId`。
- 前端创建作业表单已支持：
  - 智能识别
  - 实验报告
  - 论文总结
  - 课程问答
- 手动选择具体 skill 时，后端会直接使用该 skill。
- 选择“智能识别”时，Python Agent 会执行自动路由。
- 生成完成后会保存实际执行的 `resolvedSkillId`，并在前端详情区展示“实际执行”。

### 2. 目录式 Skill Package

- 已从单一 JSON 配置升级为目录式 skill：

```text
agent-python/app/skills/<skill_id>/
  skill.json
  SKILL.md
```

- `skill.json` 用于机器读取元数据。
- `SKILL.md` 用于保存渐进式披露的详细技能说明，包括适用场景、角色设定、核心要求和输出格式。
- 当前已实现 4 个 skill：
  - `lab_report`
  - `paper_summary`
  - `course_qa_report`
  - `dynamic_planner`

### 3. 智能识别 + Dynamic Planner

- 自动路由结果已从单个 skill id 升级为结构化结果：
  - `mode`
  - `resolved_skill_id`
  - `confidence`
  - `reason`
- `AUTO` 路由逻辑：
  - 规则关键词优先。
  - 规则无法高置信判断时调用 LLM 分类。
  - 置信度 `>= 0.7` 时进入固定 skill。
  - 置信度 `< 0.7` 时进入 `dynamic_planner`。
- `dynamic_planner` 已作为未知任务的兜底路径：
  - 分析作业目标。
  - 生成动态章节结构。
  - 基于动态结构组织检索和报告生成。
  - 明确标注资料不足处。

### 4. Java Workflow 与任务日志

- Java 后端继续通过 `/agent/generate-report` 调用 Python Agent。
- 已读取并处理 Python 返回的：
  - `resolved_skill_id`
  - `routing_mode`
  - `routing_confidence`
  - `routing_reason`
- 已将实际执行 skill 保存回作业。
- AI 工作流程日志中已展示 Skill 路由结果，例如：
  - 命中论文总结，置信度 86%。
  - 未高置信命中固定 Skill，进入动态规划。

### 5. 前端工作台布局

- 已压缩顶部统计卡片和左侧导航区域。
- 已重新设计任务类型选择：
  - “智能识别”作为推荐的自动路由入口。
  - 三个固定 skill 作为手动选项。
- 已优化主工作区比例，让“AI 工作流程”和报告预览成为页面重点。
- 已调整主内容下边界，减少页面底部无边界的视觉问题。

### 6. Eval Harness 初版

- 已新增轻量离线评测目录：`agent-python/evals`。
- 当前支持统计：
  - `Recall@k`
  - `MRR`
  - `Skill Routing Accuracy`
  - `Section Completeness`
  - `Groundedness`
- 已提供示例 JSONL 输入和运行说明。

## 已验证内容

- Python skill registry 可以加载 4 个 skill。
- Python 单测覆盖 skill registry、规则路由、动态规划兜底等基础逻辑。
- Java 后端 Maven 打包通过。
- 前端 TypeScript typecheck 通过。
- Docker Compose 可以重新 build 并启动核心服务。
- 前端实测可以生成作业并展示动态规划路由日志。

## 尚未完成内容

### 1. 完整 ReAct / Tool Calling Loop

当前 `dynamic_planner` 只是动态规划 workflow，不是完整 ReAct。

还未实现：

- 多轮 Thought / Action / Observation 循环。
- Agent 主动选择工具。
- 工具调用结果回填上下文。
- 失败重试和工具选择审计日志。

后续可以把 `dynamic_planner` 扩展成 ReAct agent，让它不仅生成报告，还能根据任务主动决定是否检索、重查、抽取表格、生成代码分析等。

### 2. MCP 集成

当前项目没有真正接入 MCP。

后续可考虑：

- 做一个资料库 MCP Server。
- 做一个作业/报告 MCP Server。
- 让 Agent 通过 MCP 读取作业、资料、历史报告和评测结果。
- 在简历中强调“通过 MCP 将业务系统能力封装为 Agent 可调用工具”。

### 3. 评测 Harness 与真实数据打通

当前 eval harness 是离线脚本，还没有自动接入真实生成链路。

后续可做：

- 保存每次检索的 top-k chunk id。
- 保存人工标注的 expected skill 和 relevant chunk。
- 自动批量跑评测集。
- 输出可展示的数据报表。
- 用真实指标优化 chunk size、top_k、prompt 和路由阈值。

### 4. 更细的路由置信度设计

当前置信度是工程评分，不是严格统计概率。

后续可优化：

- 规则分数归一化。
- 引入更多负例样本。
- 让 LLM 输出结构化分类理由。
- 用 eval harness 调整 `0.7` 阈值。
- 将 confidence/reason 持久化到数据库，支持后续数据分析。

### 5. 更多 Skill

目前只有三个固定作业类型和一个动态规划兜底。

后续可新增：

- 代码阅读与实验复现 skill。
- PPT 汇报大纲 skill。
- 文献综述 skill。
- 课程复习笔记 skill。
- 数据分析报告 skill。
- Debug / 编程作业讲解 skill。

### 6. 报告质量控制

还未系统实现：

- 引用来源标注。
- 幻觉检测。
- 事实一致性检查。
- 报告改写与润色工作流。
- 生成后自动检查章节完整率。

### 7. 前端数据看板

当前前端主要展示工作流程和报告内容，还没有展示评测指标。

后续可以增加：

- Skill 命中分布。
- 平均路由置信度。
- 报告生成成功率。
- Recall@k / MRR 趋势。
- 每个作业的资料覆盖情况。

## 下次继续开发时建议先问

下一次继续完善功能时，可以先确认优先方向：

1. 是否继续做 ReAct / Tool Calling，让 `dynamic_planner` 变成更像真正 agent 的执行器？
2. 是否先做 MCP，把作业、资料、报告能力封装成 Agent 工具？
3. 是否先补 eval harness，把 Recall@k、MRR、Skill Routing Accuracy 跑出真实数据？
4. 是否继续增加更多作业 skill？
5. 是否优先打磨前端展示和报告质量控制？

## 上传指令

如果这是第一次上传到 GitHub，先在 GitHub 新建一个空仓库，然后执行：

```bash
git status
git add README.md ROADMAP.md .gitignore .env.example docker-compose.yml frontend backend-java agent-python
git status --short
git commit -m "feat: add skill routing and dynamic planner"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

如果已经绑定过远程仓库：

```bash
git status
git add README.md ROADMAP.md .gitignore .env.example docker-compose.yml frontend backend-java agent-python
git status --short
git commit -m "feat: add skill routing and dynamic planner"
git push
```

上传前请确认以下内容没有进入提交列表：

- `.env`
- `.m2/`
- `.docker-config/`
- `frontend/node_modules/`
- `frontend/.next/`
- `backend-java/target/`
- `agent-python/storage/`
- `__pycache__/`
