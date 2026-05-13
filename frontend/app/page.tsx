"use client";

import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  BarChart3,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Circle,
  Clock3,
  Download,
  FileText,
  Folder,
  Home,
  Loader2,
  Moon,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Sun,
  Trash2,
  Upload,
  UserRound,
  Workflow
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { API_BASE_URL, api } from "@/lib/api";
import type {
  AgentTask,
  AgentTaskLog,
  Assignment,
  AssignmentDetail,
  DashboardSummary,
  Material,
  MonitoringOverview,
  Report
} from "@/lib/types";

const demoAssignments: Assignment[] = [
  {
    id: -1,
    title: "编程作业3：人脸识别程序",
    course: "计算机视觉",
    description: "完成一个人脸识别实验，上传实验要求、论文或课件后生成报告草稿。",
    dueAt: "2026-05-08T23:59:00",
    skillId: "AUTO",
    resolvedSkillId: "lab_report",
    status: "READY"
  },
  {
    id: -2,
    title: "编程作业4：CIFAR-10 图像分类",
    course: "计算机视觉",
    description: "构建 CNN 分类器并分析训练结果。",
    dueAt: "2026-05-08T23:59:00",
    skillId: "AUTO",
    status: "DRAFT"
  },
  {
    id: -3,
    title: "图像分割算法实验",
    course: "计算机视觉",
    description: "实现基础图像分割方法并完成对比分析。",
    dueAt: "2026-05-10T23:59:00",
    skillId: "AUTO",
    status: "DRAFT"
  }
];

const demoReport = `# 数字化教学平台使用教程 - 个人作业报告

## 实验目的
熟悉资料整理、任务分析与报告草稿生成流程，完成一份可继续编辑的实验报告。

## 实验原理
系统通过上传资料、文本切分、向量检索和大模型生成，把实验要求转换为结构化 Markdown 草稿。

## 实验步骤
1. 创建作业并填写课程、截止时间和说明。
2. 上传 PDF、Markdown 或 TXT 资料。
3. 触发 AI 工作流，完成资料解析、RAG 检索和报告生成。
4. 在右侧 Markdown 编辑器中继续修改并保存。

## 核心代码分析
待补充。请结合上传的代码、实验截图或论文内容完善。

## 实验总结
本次实验完成了资料整理、任务分析与报告草稿生成流程，后续可继续补充实验数据、截图和代码解释。`;

const demoMaterials: Material[] = [
  {
    id: -1,
    assignmentId: -1,
    filename: "实验要求.pdf",
    contentType: "application/pdf",
    sizeBytes: 2400000,
    storagePath: "",
    indexStatus: "INDEXED"
  },
  {
    id: -2,
    assignmentId: -1,
    filename: "参考报告.md",
    contentType: "text/markdown",
    sizeBytes: 1100,
    storagePath: "",
    indexStatus: "INDEXED"
  }
];

const demoLogs: AgentTaskLog[] = [
  { taskId: -1, stage: "parse", status: "SUCCEEDED", message: "资料解析完成，已提取关键内容。" },
  { taskId: -1, stage: "retrieve", status: "SUCCEEDED", message: "RAG 检索完成，已匹配相关片段。" },
  { taskId: -1, stage: "generate", status: "SUCCEEDED", message: "报告草稿已生成。" },
  { taskId: -1, stage: "done", status: "SUCCEEDED", message: "任务完成。" }
];

const initialSummary: DashboardSummary = {
  assignments: 7,
  materials: 4,
  reports: 7,
  overdue: 3
};

type WorkspaceView = "workspace" | "monitoring";

const emptyMonitoring: MonitoringOverview = {
  kpis: {
    totalTasks: 0,
    successRate: 0,
    taskCompletionRate: 0,
    qualityPassRate: 0,
    avgDurationSeconds: 0,
    p95DurationSeconds: 0,
    dynamicPlannerRate: 0,
    rewriteRate: 0,
    rewriteTriggerRate: 0,
    rewriteAcceptRate: 0,
    avgRetrievedChunks: 0
  },
  skillDistribution: [],
  stageDurations: [],
  recentTasks: [],
  resourceStats: {
    assignments: 0,
    materials: 0,
    indexedMaterials: 0,
    reports: 0,
    avgMaterialsPerAssignment: 0
  }
};

const skillOptions = [
  { value: "lab_report", label: "实验报告" },
  { value: "paper_summary", label: "论文总结" },
  { value: "course_qa_report", label: "课程问答" }
];

export default function HomePage() {
  const fileInput = useRef<HTMLInputElement | null>(null);
  const refreshInFlight = useRef(false);

  const [summary, setSummary] = useState<DashboardSummary>(initialSummary);
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>("workspace");
  const [monitoring, setMonitoring] = useState<MonitoringOverview | null>(null);
  const [isMonitoringLoading, setIsMonitoringLoading] = useState(false);
  const [assignments, setAssignments] = useState<Assignment[]>(demoAssignments);
  const [selectedId, setSelectedId] = useState<number>(demoAssignments[0].id);
  const [materials, setMaterials] = useState<Material[]>(demoMaterials);
  const [report, setReport] = useState<Report | null>({
    id: -1,
    assignmentId: -1,
    title: "数字化教学平台使用教程 - 个人作业报告",
    markdown: demoReport,
    version: 1
  });
  const [markdown, setMarkdown] = useState(demoReport);
  const [logs, setLogs] = useState<AgentTaskLog[]>(demoLogs);
  const [taskHistory, setTaskHistory] = useState<AgentTask[]>([]);
  const [activeTask, setActiveTask] = useState<AgentTask | null>(null);
  const [reportMode, setReportMode] = useState<"preview" | "edit">("preview");
  const [isBusy, setIsBusy] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastRefreshAt, setLastRefreshAt] = useState<Date | null>(null);
  const [refreshStatus, setRefreshStatus] = useState<"idle" | "success" | "failed">("idle");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [error, setError] = useState<string | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [isQueueOpen, setIsQueueOpen] = useState(false);
  const [queueSelectedId, setQueueSelectedId] = useState<number>(demoAssignments[0].id);
  const [isAssignmentFormOpen, setIsAssignmentFormOpen] = useState(false);
  const [overviewModal, setOverviewModal] = useState<"materials" | "reports" | "overdue" | null>(null);
  const [allMaterials, setAllMaterials] = useState<Material[]>([]);
  const [allReports, setAllReports] = useState<Report[]>([]);
  const [formMode, setFormMode] = useState<"create" | "edit">("create");
  const [keyword, setKeyword] = useState("");
  const [draft, setDraft] = useState({
    title: "",
    course: "",
    description: "",
    dueAt: "",
    skillId: "AUTO"
  });

  const selected = useMemo(
    () => assignments.find((assignment) => assignment.id === selectedId) ?? assignments[0],
    [assignments, selectedId]
  );
  const visibleLogs = useMemo(() => latestStageLogs(logs), [logs]);
  const isDemo = selected?.id < 0;
  const latestTask = taskHistory[0] ?? activeTask;
  const overdueAssignments = useMemo(
    () => assignments.filter((assignment) => isOverdue(assignment.dueAt)),
    [assignments]
  );

  useEffect(() => {
    const savedTheme = window.localStorage.getItem("fzu-theme");
    const nextTheme = savedTheme === "dark" ? "dark" : "light";
    setTheme(nextTheme);
    document.documentElement.classList.toggle("dark", nextTheme === "dark");
  }, []);

  useEffect(() => {
    void refresh();
  }, [keyword]);

  useEffect(() => {
    if (workspaceView === "monitoring") {
      void loadMonitoring();
    }
  }, [workspaceView]);

  useEffect(() => {
    if (!selected || isDemo) {
      return;
    }
    void loadDetail(selected.id);
  }, [selectedId]);

  useEffect(() => {
    if (!activeTask || activeTask.id < 0) {
      return;
    }
    const source = new EventSource(`${API_BASE_URL}/api/tasks/${activeTask.id}/events`);
    source.addEventListener("log", (event) => {
      const log = JSON.parse(event.data) as AgentTaskLog;
      setLogs((current) => [...current, log]);
      if (log.status === "SUCCEEDED" || log.status === "FAILED") {
        if (log.stage === "done" || log.status === "FAILED") {
          source.close();
          setActiveTask(null);
        }
        setTimeout(() => void loadDetail(activeTask.assignmentId), 900);
      }
    });
    source.onerror = () => source.close();
    return () => source.close();
  }, [activeTask?.id]);

  async function refresh() {
    if (refreshInFlight.current) {
      return;
    }
    refreshInFlight.current = true;
    setIsRefreshing(true);
    setError(null);
    try {
      const [summaryData, assignmentData] = await Promise.all([
        api.summary(),
        api.assignments({ keyword, sort: "createdDesc" })
      ]);
      setSummary(summaryData);
      setAssignments(assignmentData);
      if (assignmentData.length) {
        const nextId = assignmentData.some((assignment) => assignment.id === selectedId)
          ? selectedId
          : assignmentData[0].id;
        setSelectedId(nextId);
        await loadDetail(nextId);
      } else {
        setSelectedId(0);
        setMaterials([]);
        setReport(null);
        setMarkdown("");
        setLogs([]);
        setTaskHistory([]);
      }
      setLastRefreshAt(new Date());
      setRefreshStatus("success");
    } catch (err) {
      setRefreshStatus("failed");
      setError(err instanceof Error ? err.message : "无法连接后端，当前展示演示数据。");
    } finally {
      refreshInFlight.current = false;
      setIsRefreshing(false);
    }
  }

  async function loadDetail(id: number) {
    if (id < 0) {
      setMaterials(demoMaterials);
      setReport({
        id: -1,
        assignmentId: -1,
        title: "数字化教学平台使用教程 - 个人作业报告",
        markdown: demoReport,
        version: 1
      });
      setMarkdown(demoReport);
      setLogs(demoLogs);
      setTaskHistory([]);
      setActiveTask(null);
      return;
    }

    const detail: AssignmentDetail = await api.assignmentDetail(id);
    setAssignments((current) => current.map((assignment) => assignment.id === id ? detail.assignment : assignment));
    setMaterials(detail.materials);
    setReport(detail.report ?? null);
    setMarkdown(normalizeMarkdown(detail.report?.markdown ?? ""));

    const tasks = await api.assignmentTasks(id);
    setTaskHistory(tasks);
    if (tasks.length) {
      const latest = await api.task(tasks[0].id);
      setLogs(latest.logs);
      setActiveTask(["QUEUED", "RUNNING"].includes(tasks[0].status) ? tasks[0] : null);
    } else {
      setLogs([]);
      setActiveTask(null);
    }
  }

  function toggleTheme() {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    window.localStorage.setItem("fzu-theme", nextTheme);
    document.documentElement.classList.toggle("dark", nextTheme === "dark");
  }

  async function submitAssignment() {
    if (!draft.title.trim()) {
      setError("请输入作业标题。");
      return;
    }
    setIsBusy(true);
    try {
      const payload = {
        title: draft.title,
        course: draft.course,
        description: draft.description,
        dueAt: draft.dueAt || undefined,
        skillId: draft.skillId
      };
      const saved =
        formMode === "edit" && selected && !isDemo
          ? await api.updateAssignment(selected.id, payload)
          : await api.createAssignment(payload);
      setDraft({ title: "", course: "", description: "", dueAt: "", skillId: "AUTO" });
      setFormMode("create");
      setIsAssignmentFormOpen(false);
      await refresh();
      setSelectedId(saved.id);
      setQueueSelectedId(saved.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存作业失败。");
    } finally {
      setIsBusy(false);
    }
  }

  function startEditAssignment() {
    if (!selected || isDemo) {
      return;
    }
    setFormMode("edit");
    setDraft({
      title: selected.title,
      course: selected.course || "",
      description: selected.description || "",
      dueAt: selected.dueAt ? selected.dueAt.slice(0, 16) : "",
      skillId: selected.skillId || "AUTO"
    });
    setIsAssignmentFormOpen(true);
    setIsDetailOpen(false);
  }

  async function loadMonitoring() {
    setIsMonitoringLoading(true);
    setError(null);
    try {
      setMonitoring(await api.monitoringOverview());
      setLastRefreshAt(new Date());
      setRefreshStatus("success");
    } catch (err) {
      setRefreshStatus("failed");
      setError(err instanceof Error ? err.message : "监控数据加载失败。");
    } finally {
      setIsMonitoringLoading(false);
    }
  }

  function startCreateAssignment() {
    setFormMode("create");
    setDraft({ title: "", course: "", description: "", dueAt: "", skillId: "AUTO" });
    setIsQueueOpen(false);
    setIsAssignmentFormOpen(true);
  }

  function confirmQueueSelection() {
    setSelectedId(queueSelectedId);
    setIsQueueOpen(false);
  }

  async function openOverviewModal(kind: "materials" | "reports" | "overdue") {
    setOverviewModal(kind);
    setError(null);
    try {
      if (kind === "materials") {
        setAllMaterials(await api.materials());
      }
      if (kind === "reports") {
        setAllReports(await api.reports());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载概览失败。");
    }
  }

  async function deleteAssignment() {
    if (!selected || isDemo) {
      return;
    }
    if (!window.confirm(`确定删除“${selected.title}”及其资料、任务和报告吗？`)) {
      return;
    }
    setIsBusy(true);
    try {
      await api.deleteAssignment(selected.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除作业失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function uploadMaterial(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !selected || isDemo) {
      return;
    }
    setIsBusy(true);
    setError(null);
    try {
      await api.uploadMaterial(selected.id, file);
      await loadDetail(selected.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败。");
    } finally {
      setIsBusy(false);
      event.target.value = "";
    }
  }

  async function deleteMaterial(id: number) {
    if (!window.confirm("确定删除这份资料吗？")) {
      return;
    }
    setIsBusy(true);
    try {
      await api.deleteMaterial(id);
      if (selected && !isDemo) {
        await loadDetail(selected.id);
        await refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除资料失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function generateReport() {
    if (!selected || isDemo) {
      setError("请先创建一个真实作业并上传资料，再生成报告。");
      return;
    }
    if (materials.length === 0) {
      setError("请先上传 PDF、Markdown 或 TXT 资料。");
      return;
    }
    if (report && !window.confirm("重新生成会覆盖当前报告草稿并增加版本号，确定继续吗？")) {
      return;
    }
    setIsBusy(true);
    setError(null);
    setLogs([]);
    try {
      const task = await api.generate(selected.id);
      setActiveTask(task);
      setLogs([{ taskId: task.id, stage: "queued", status: "QUEUED", message: "任务已创建，等待 Agent 执行。" }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成任务创建失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function retryTask(taskId: number) {
    setIsBusy(true);
    setError(null);
    setLogs([]);
    try {
      const task = await api.retryTask(taskId);
      setActiveTask(task);
      setLogs([{ taskId: task.id, stage: "queued", status: "QUEUED", message: "重试任务已创建，等待 Agent 执行。" }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "重试失败。");
    } finally {
      setIsBusy(false);
    }
  }

  async function saveReport() {
    if (!report || report.id < 0) {
      return;
    }
    setIsBusy(true);
    try {
      const saved = await api.updateReport(report.id, markdown);
      setReport(saved);
      setReportMode("preview");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存报告失败。");
    } finally {
      setIsBusy(false);
    }
  }

  function exportReport() {
    if (selected && report && report.id >= 0) {
      window.open(api.exportReportUrl(selected.id), "_blank");
    }
  }

  return (
    <main className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-16 border-r border-slate-200 bg-white/88 backdrop-blur xl:flex xl:flex-col xl:items-center xl:py-5 dark:border-slate-800 dark:bg-slate-950">
        <div className="mb-10 flex h-10 w-10 items-center justify-center rounded-lg bg-moss-700 text-white shadow-sm">
          <Workflow size={21} />
        </div>
        <nav className="flex flex-1 flex-col items-center gap-4">
          <SidebarButton icon={Home} active={workspaceView === "workspace"} title="作业工作台" onClick={() => setWorkspaceView("workspace")} />
          <SidebarButton icon={Folder} title="资料库" />
          <SidebarButton icon={FileText} title="报告草稿" />
          <SidebarButton icon={BarChart3} active={workspaceView === "monitoring"} title="数据监控" onClick={() => setWorkspaceView("monitoring")} />
          <SidebarButton icon={Settings} title="设置" />
        </nav>
        <Button variant="ghost" size="icon" title="用户">
          <UserRound size={18} />
        </Button>
      </aside>

      <section className={`px-4 py-3 sm:px-6 xl:ml-16 xl:px-6 ${workspaceView === "monitoring" ? "min-h-screen pb-10" : "xl:h-screen xl:overflow-hidden xl:pb-5"}`}>
        <header className="mb-2 flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">FZU HOMEWORK ASSISTANT</p>
            <h1 className="mt-0.5 text-2xl font-bold tracking-normal text-slate-950">
              {workspaceView === "monitoring" ? "数据监控" : "作业资料工作台"}
            </h1>
            {workspaceView === "monitoring" && (
              <p className="mt-1 text-xs text-slate-500">Agent Loop / RAG / Skill Routing 运行画像</p>
            )}
          </div>
          <div className="flex w-full flex-wrap items-center gap-2 lg:w-auto lg:flex-nowrap lg:justify-end">
            <div className="flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <div className={`flex items-center gap-2 font-medium ${refreshStatus === "failed" ? "text-red-600 dark:text-red-400" : "text-moss-700 dark:text-emerald-300"}`}>
                {isRefreshing || isMonitoringLoading ? <Loader2 size={16} className="animate-spin" /> : refreshStatus === "failed" ? <Circle size={16} /> : <CheckCircle2 size={16} />}
                {isRefreshing || isMonitoringLoading ? "同步中" : refreshStatus === "failed" ? "同步失败" : "数据已刷新"}
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">{formatRefreshTime(lastRefreshAt)}</p>
            </div>
            <Button
              className="h-9 px-3 text-xs"
              onClick={() => workspaceView === "monitoring" ? void loadMonitoring() : void refresh()}
              disabled={isRefreshing || isMonitoringLoading}
            >
              <RefreshCw size={15} className={isRefreshing || isMonitoringLoading ? "animate-spin" : undefined} />
              {isRefreshing || isMonitoringLoading ? "同步中" : "同步"}
            </Button>
            {workspaceView === "workspace" && (
              <>
                <Button className="h-9 px-3 text-xs" variant="primary" onClick={startCreateAssignment} disabled={isBusy}>
                  <Plus size={15} />
                  新建作业
                </Button>
                <div className="flex h-9 w-full min-w-0 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs shadow-sm dark:border-slate-700 dark:bg-slate-900 sm:w-[230px]">
                  <Search size={15} className="text-slate-400" />
                  <input
                    className="min-w-0 flex-1 bg-transparent text-slate-900 outline-none placeholder:text-slate-400 dark:text-slate-100"
                    placeholder="搜索作业"
                    value={keyword}
                    onChange={(event) => setKeyword(event.target.value)}
                  />
                </div>
                <Button className="h-9 px-3 text-xs" variant="primary" onClick={() => fileInput.current?.click()} disabled={!selected || isDemo || isBusy}>
                  <Plus size={15} />
                  上传资料
                </Button>
              </>
            )}
            <input ref={fileInput} hidden type="file" accept=".pdf,.md,.markdown,.txt" onChange={uploadMaterial} />
            <Button className="h-9 w-9" variant="ghost" size="icon" onClick={toggleTheme} title={theme === "dark" ? "切换浅色" : "切换深色"}>
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </Button>
          </div>
        </header>

        {workspaceView === "monitoring" ? (
          <>
            {error && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">{error}</div>}
            <MonitoringDashboard data={monitoring ?? emptyMonitoring} loading={isMonitoringLoading} onRefresh={loadMonitoring} />
          </>
        ) : (
          <>
        <section className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-4">
          <Metric
            icon={BookOpen}
            value={summary.assignments}
            label="作业总数"
            hint="点击选择作业"
            onClick={() => {
              setQueueSelectedId(selected?.id ?? assignments[0]?.id ?? 0);
              setIsQueueOpen(true);
            }}
          />
          <Metric icon={Folder} value={summary.materials} label="匹配资料" hint="点击查看资料库" onClick={() => void openOverviewModal("materials")} />
          <Metric icon={FileText} value={summary.reports} label="报告草稿" hint="点击查看报告" tone="blue" onClick={() => void openOverviewModal("reports")} />
          <Metric icon={Clock3} value={summary.overdue} label="已过期" hint="点击处理" tone="red" onClick={() => void openOverviewModal("overdue")} />
        </section>

        {error && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">{error}</div>}

        <section className="mt-2.5 grid gap-3 border-b border-slate-200 pb-3 xl:h-[calc(100vh-157px)] xl:min-h-0 xl:grid-cols-[minmax(720px,1fr)_minmax(560px,0.62fr)]">
          <Card className="flex min-h-0 flex-col overflow-hidden">
            <div className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(280px,0.78fr)_minmax(420px,1.22fr)]">
              <div className="min-h-0 space-y-4 overflow-y-auto pr-1">
                <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-moss-700">{selected?.course || "课程概览"}</p>
                      <h2 className="mt-1 truncate text-xl font-bold text-slate-950">{selected?.title}</h2>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                  <StatusBadge status={latestTask?.status || activeTask?.status || selected?.status || "DRAFT"} />
                      <Button size="icon" variant="ghost" onClick={startEditAssignment} disabled={!selected || isDemo}>
                        <Pencil size={17} />
                      </Button>
                      <Button size="icon" variant="ghost" onClick={deleteAssignment} disabled={!selected || isDemo || isBusy}>
                        <Trash2 size={17} />
                      </Button>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setIsDetailOpen(true)}
                      className="group inline-flex max-w-full items-center gap-2 rounded-full border border-moss-200 bg-moss-50 px-3 py-1.5 text-sm font-semibold text-moss-800 shadow-sm transition hover:-translate-y-0.5 hover:border-moss-500 hover:bg-white hover:shadow-md dark:border-moss-700 dark:bg-moss-900/30 dark:text-emerald-100"
                      title="查看作业详情"
                    >
                      <Sparkles size={15} className="shrink-0 transition group-hover:rotate-12" />
                      <span className="truncate">{selected?.course || selected?.title || "项目作业"}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setIsDetailOpen(true)}
                      className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition hover:bg-moss-50 hover:text-moss-800 dark:hover:bg-slate-800"
                      title="展开详情"
                    >
                      <ChevronRight size={17} />
                    </button>
                  </div>
                </div>

                <div>
                  <Button className="h-9 px-3 text-xs" variant="primary" onClick={generateReport} disabled={isBusy}>
                    <FileText size={17} />
                    生成当前报告草稿
                  </Button>
                </div>

                <section className="rounded-lg border border-slate-100 bg-white/70 p-3 dark:border-slate-800 dark:bg-slate-900/70">
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="font-semibold">任务历史</h3>
                    <span className="text-sm text-slate-500">{taskHistory.length} 条</span>
                  </div>
                  {taskHistory.length === 0 ? (
                    <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">还没有生成任务。</p>
                  ) : (
                    <div className="space-y-2">
                      {taskHistory.slice(0, 4).map((task) => (
                        <div key={task.id} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-900">
                          <div className="flex items-center justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <StatusBadge status={task.status} />
                            </div>
                            {task.status === "FAILED" && (
                              <button
                                type="button"
                                onClick={() => void retryTask(task.id)}
                                disabled={isBusy}
                                className="inline-flex h-7 shrink-0 items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-600 transition hover:border-moss-400 hover:text-moss-800 disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                <RotateCcw size={13} />
                                重试
                              </button>
                            )}
                          </div>
                          <p className="mt-2 inline-flex items-center gap-1 text-sm text-slate-700">
                            <Clock3 size={13} className="shrink-0 text-slate-400" />
                            <span>{formatDateTime(task.createdAt)}</span>
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            阶段：{stageLabel(task.currentStage || "queued")} · 耗时：{formatDuration(task.startedAt, task.finishedAt)}
                          </p>
                          {task.draftVersionReason && <p className="mt-1 line-clamp-1 text-xs text-slate-500">{task.draftVersionReason}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                </section>

                <section className="rounded-lg border border-slate-100 bg-white/70 p-3 dark:border-slate-800 dark:bg-slate-900/70">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold">相关资料</h3>
                      <p className="mt-1 text-xs text-slate-500">当前作业资料库</p>
                    </div>
                    <Button size="sm" onClick={() => fileInput.current?.click()} disabled={!selected || isDemo || isBusy}>
                      <Upload size={15} />
                      上传
                    </Button>
                  </div>
                  {materials.length === 0 ? (
                    <button
                      onClick={() => fileInput.current?.click()}
                      disabled={!selected || isDemo || isBusy}
                      className="flex min-h-[120px] w-full flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50/70 px-4 py-6 text-center transition hover:border-moss-600 hover:bg-moss-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900"
                    >
                      <Upload size={22} className="mb-3 text-moss-700" />
                      <p className="font-medium text-slate-900">上传资料后再生成报告</p>
                      <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">支持 PDF、Markdown、TXT。</p>
                    </button>
                  ) : (
                    <div className="space-y-2">
                      {materials.map((material) => (
                        <div key={material.id} className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                          <div className="flex items-start gap-3">
                            <FileText size={18} className="mt-0.5 text-slate-600" />
                            <div className="min-w-0 flex-1">
                              <div className="flex items-start justify-between gap-2">
                                <p className="truncate text-sm font-medium text-slate-900">{material.filename}</p>
                                <button className="text-slate-400 hover:text-red-600" onClick={() => void deleteMaterial(material.id)} disabled={isBusy}>
                                  <Trash2 size={15} />
                                </button>
                              </div>
                              <p className="mt-1 text-xs text-slate-500">{fileKind(material.filename)} · {formatSize(material.sizeBytes)}</p>
                              <div className="mt-2"><StatusBadge status={material.indexStatus} /></div>
                              {material.indexStatus === "FAILED" && material.errorMessage && (
                                <p className="mt-2 text-xs leading-5 text-red-600">{material.errorMessage}</p>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              </div>

              <section className="min-h-0 overflow-y-auto rounded-lg border border-moss-100 bg-moss-50/30 p-3 dark:border-moss-900 dark:bg-moss-950/10">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-lg font-semibold">AI 工作流程</h3>
                  <span className="rounded-full bg-white px-2.5 py-0.5 text-xs text-moss-700 shadow-sm dark:bg-slate-900">Agent Loop</span>
                </div>
                <div className="space-y-3.5 rounded-lg border border-slate-100 bg-white/80 p-3 dark:border-slate-800 dark:bg-slate-900/80">
                  {visibleLogs.length ? visibleLogs.map((log, index) => (
                    <div key={`${log.stage}-${index}`} className="grid grid-cols-[24px_1fr_auto] items-start gap-3">
                      <StepIcon status={log.status} />
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{stageLabel(log.stage)}</p>
                        <p className="mt-1 text-xs leading-5 text-slate-500">{log.message}</p>
                      </div>
                      <span className="rounded-full bg-slate-50 px-2.5 py-0.5 text-xs text-slate-500">{statusText(log.status)}</span>
                    </div>
                  )) : (
                    <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">还没有生成任务。</p>
                  )}
                </div>
              </section>
            </div>
          </Card>

          <Card className="flex min-h-0 flex-col overflow-hidden">
            <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-100 px-3 py-3">
              <h2 className="flex shrink-0 items-center gap-2 text-sm font-semibold leading-5">
                <FileText size={16} />
                <span className="whitespace-nowrap">报告草稿</span>
              </h2>
              <div className="flex min-w-0 items-center justify-end gap-2">
                {report && (
                  <div className="hidden shrink-0 text-right text-xs text-slate-500 2xl:block">
                    <p>v{report.version}</p>
                    <p>{formatDateTime(report.updatedAt)}</p>
                  </div>
                )}
                <Button className="h-8 whitespace-nowrap px-2.5 text-xs" size="sm" variant={reportMode === "preview" ? "primary" : "outline"} onClick={() => setReportMode("preview")}>预览</Button>
                <Button className="h-8 whitespace-nowrap px-2.5 text-xs" size="sm" variant={reportMode === "edit" ? "primary" : "outline"} onClick={() => setReportMode("edit")}>编辑</Button>
                <Button className="h-8 whitespace-nowrap px-2.5 text-xs" size="sm" variant="primary" onClick={saveReport} disabled={!report || report.id < 0 || isBusy}>
                  <Save size={15} />
                  保存
                </Button>
                <Button className="h-8 whitespace-nowrap px-2.5 text-xs" size="sm" onClick={exportReport} disabled={!report || report.id < 0}>
                  <Download size={15} />
                  导出
                </Button>
              </div>
            </div>
            {reportMode === "edit" ? (
              <textarea
                className="min-h-0 flex-1 resize-none border-0 bg-white p-4 font-mono text-[13px] leading-6 text-slate-900 outline-none dark:bg-slate-900 dark:text-slate-100"
                value={markdown}
                onChange={(event) => setMarkdown(event.target.value)}
              />
            ) : (
              <div className="markdown-preview min-h-0 flex-1 overflow-auto p-4">
                {markdown ? (
                  <ReactMarkdown>{markdown}</ReactMarkdown>
                ) : (
                  <div className="flex min-h-[360px] items-center justify-center text-sm text-slate-500">生成报告后将在这里显示 Markdown 草稿。</div>
                )}
              </div>
            )}
          </Card>
        </section>
          </>
        )}
      </section>
      {isQueueOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 px-4 py-6 backdrop-blur-sm" onClick={() => setIsQueueOpen(false)}>
          <div
            className="flex max-h-[82vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-white/70 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-800">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-moss-700">ASSIGNMENT QUEUE</p>
                <h3 className="mt-1 text-xl font-bold text-slate-950">选择要展示的作业</h3>
              </div>
              <Button size="sm" onClick={startCreateAssignment}>
                <Plus size={15} />
                新建
              </Button>
            </div>
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4">
              {assignments.length ? assignments.map((assignment) => (
                <button
                  key={assignment.id}
                  type="button"
                  onClick={() => setQueueSelectedId(assignment.id)}
                  className={`w-full rounded-lg border p-3 text-left transition ${
                    queueSelectedId === assignment.id ? "border-moss-600 bg-moss-50 shadow-sm dark:bg-moss-800/30" : "border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h4 className="truncate text-sm font-semibold text-slate-950">{assignment.title}</h4>
                      <p className="mt-1 text-xs text-slate-500">{assignment.course || "未设置课程"}</p>
                    </div>
                    <StatusBadge status={assignment.status} />
                  </div>
                  <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                    <span>截止：{formatDue(assignment.dueAt)}</span>
                    <span>{skillLabel(assignment.resolvedSkillId || assignment.skillId)}</span>
                  </div>
                </button>
              )) : (
                <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">还没有作业，先新建一个。</p>
              )}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-5 py-3 dark:border-slate-800">
              <Button variant="ghost" onClick={() => setIsQueueOpen(false)}>取消</Button>
              <Button variant="primary" onClick={confirmQueueSelection} disabled={!queueSelectedId}>
                打开作业
              </Button>
            </div>
          </div>
        </div>
      )}
      {isAssignmentFormOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 px-4 py-6 backdrop-blur-sm" onClick={() => setIsAssignmentFormOpen(false)}>
          <div
            className="w-full max-w-xl overflow-hidden rounded-xl border border-white/70 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-moss-700">{formMode === "edit" ? "EDIT ASSIGNMENT" : "NEW ASSIGNMENT"}</p>
              <h3 className="mt-1 text-xl font-bold text-slate-950">{formMode === "edit" ? "编辑作业" : "新建作业"}</h3>
            </div>
            <div className="space-y-3 px-5 py-4">
              <input className="field" placeholder="作业标题" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
              <input className="field" placeholder="课程名称，例如：字节ai全栈挑战赛" value={draft.course} onChange={(event) => setDraft({ ...draft, course: event.target.value })} />
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <span className="block text-xs font-medium text-slate-600">任务类型</span>
                  <span className="rounded-full bg-moss-50 px-2 py-0.5 text-[10px] font-medium text-moss-700">可自动路由</span>
                </div>
                <button
                  type="button"
                  onClick={() => setDraft({ ...draft, skillId: "AUTO" })}
                  className={`flex h-10 w-full items-center justify-between rounded-lg border px-3 text-left text-sm transition ${
                    draft.skillId === "AUTO"
                      ? "border-moss-700 bg-moss-50 text-moss-800 shadow-sm"
                      : "border-slate-200 bg-white text-slate-600 hover:border-moss-300 hover:bg-moss-50/60 dark:border-slate-700 dark:bg-slate-900"
                  }`}
                >
                  <span className="flex min-w-0 items-center gap-2 font-semibold">
                    <Sparkles size={15} className="shrink-0" />
                    智能识别
                  </span>
                  <span className="rounded-full bg-white/80 px-2 py-0.5 text-[10px] text-moss-700 shadow-sm">推荐</span>
                </button>
                <div className="mt-2 grid grid-cols-3 gap-2">
                  {skillOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setDraft({ ...draft, skillId: option.value })}
                      className={`h-9 rounded-md border px-2 text-xs font-medium transition ${
                        draft.skillId === option.value
                          ? "border-moss-700 bg-moss-700 text-white shadow-sm"
                          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-950 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-slate-600">截止时间</span>
                <input className="field" type="datetime-local" value={draft.dueAt} onChange={(event) => setDraft({ ...draft, dueAt: event.target.value })} />
              </label>
              <textarea className="field min-h-28 resize-none" placeholder="作业说明" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} />
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-5 py-3 dark:border-slate-800">
              <Button variant="ghost" onClick={() => setIsAssignmentFormOpen(false)}>取消</Button>
              <Button variant="primary" onClick={submitAssignment} disabled={isBusy}>
                {formMode === "edit" ? <Save size={17} /> : <Plus size={17} />}
                {formMode === "edit" ? "保存修改" : "创建作业"}
              </Button>
            </div>
          </div>
        </div>
      )}
      {overviewModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 px-4 py-6 backdrop-blur-sm" onClick={() => setOverviewModal(null)}>
          <div
            className="flex max-h-[82vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-white/70 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-800">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-moss-700">OVERVIEW</p>
                <h3 className="mt-1 text-xl font-bold text-slate-950">{overviewTitle(overviewModal)}</h3>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setOverviewModal(null)}>关闭</Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {overviewModal === "materials" && (
                allMaterials.length ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {allMaterials.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          setSelectedId(item.assignmentId);
                          setOverviewModal(null);
                        }}
                        className="rounded-lg border border-slate-200 bg-white p-3 text-left transition hover:border-moss-500 hover:bg-moss-50 dark:border-slate-800 dark:bg-slate-900"
                      >
                        <div className="flex items-start gap-3">
                          <FileText size={18} className="mt-0.5 text-slate-600" />
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-semibold text-slate-950">{item.filename}</p>
                            <p className="mt-1 text-xs text-slate-500">作业 #{item.assignmentId} · {fileKind(item.filename)} · {formatSize(item.sizeBytes)}</p>
                            <div className="mt-2"><StatusBadge status={item.indexStatus} /></div>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">还没有资料。</p>
                )
              )}
              {overviewModal === "reports" && (
                allReports.length ? (
                  <div className="space-y-2">
                    {allReports.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          setSelectedId(item.assignmentId);
                          setOverviewModal(null);
                        }}
                        className="flex w-full items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-3 text-left transition hover:border-sky-500 hover:bg-sky-50 dark:border-slate-800 dark:bg-slate-900"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-950">{item.title}</p>
                          <p className="mt-1 text-xs text-slate-500">作业 #{item.assignmentId} · v{item.version} · {formatDateTime(item.updatedAt)}</p>
                        </div>
                        <ChevronRight size={16} className="shrink-0 text-slate-500" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">还没有报告草稿。</p>
                )
              )}
              {overviewModal === "overdue" && (
                overdueAssignments.length ? (
                  <div className="space-y-2">
                    {overdueAssignments.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          setSelectedId(item.id);
                          setOverviewModal(null);
                        }}
                        className="flex w-full items-center justify-between gap-3 rounded-lg border border-red-100 bg-white p-3 text-left transition hover:border-red-300 hover:bg-red-50 dark:border-slate-800 dark:bg-slate-900"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-950">{item.title}</p>
                          <p className="mt-1 text-xs text-red-600">截止：{formatDue(item.dueAt)} · {item.course || "未设置课程"}</p>
                        </div>
                        <StatusBadge status={item.status} />
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">当前没有过期作业。</p>
                )
              )}
            </div>
          </div>
        </div>
      )}
      {isDetailOpen && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 px-4 py-6 backdrop-blur-sm" onClick={() => setIsDetailOpen(false)}>
          <div
            className="w-full max-w-lg overflow-hidden rounded-xl border border-white/70 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="border-b border-slate-100 bg-gradient-to-br from-moss-50 to-white px-5 py-4 dark:border-slate-800 dark:from-slate-900 dark:to-slate-900">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-moss-700">PROJECT DETAIL</p>
                  <h3 className="mt-1 truncate text-xl font-bold text-slate-950">{selected.title}</h3>
                  <p className="mt-1 text-sm text-slate-500">{selected.course || "未设置课程名称"}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setIsDetailOpen(false)}
                  className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:border-moss-500 hover:text-moss-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                >
                  关闭
                </button>
              </div>
            </div>
            <div className="space-y-4 px-5 py-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <InfoItem label="截止时间" value={formatDue(selected.dueAt)} tone={isOverdue(selected.dueAt) ? "red" : "default"} />
                <InfoItem label="资料数量" value={`${materials.length} 条`} />
                <InfoItem label="选择类型" value={skillLabel(selected.skillId)} />
                <InfoItem label="实际执行" value={skillLabel(selected.resolvedSkillId)} />
              </div>
              <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800">
                <h4 className="text-sm font-semibold text-moss-700">作业说明</h4>
                <p className="mt-2 whitespace-pre-line text-sm leading-6 text-slate-600 dark:text-slate-300">{selected.description || "暂无作业说明。"}</p>
              </div>
              {latestTask && (
                <div className="rounded-lg border border-slate-100 p-3 dark:border-slate-800">
                  <div className="mb-2 flex items-center justify-between">
                    <h4 className="text-sm font-semibold">最近一次 Agent 执行</h4>
                    <StatusBadge status={latestTask.status} />
                  </div>
                  <p className="text-xs leading-5 text-slate-500">阶段：{stageLabel(latestTask.currentStage || "queued")} · 耗时：{formatDuration(latestTask.startedAt, latestTask.finishedAt)}</p>
                  {latestTask.routingReason && <p className="mt-2 text-xs leading-5 text-slate-500">识别原因：{latestTask.routingReason}</p>}
                  {latestTask.draftVersionReason && <p className="mt-1 text-xs leading-5 text-slate-500">{latestTask.draftVersionReason}</p>}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function SidebarButton({ icon: Icon, active = false, title, onClick }: { icon: LucideIcon; active?: boolean; title: string; onClick?: () => void }) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`flex h-10 w-10 items-center justify-center rounded-lg transition ${
        active
          ? "bg-moss-700 text-white shadow-sm"
          : "text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-100"
      }`}
    >
      <Icon size={19} />
    </button>
  );
}

function MonitoringDashboard({ data, loading, onRefresh }: { data: MonitoringOverview; loading: boolean; onRefresh: () => void | Promise<void> }) {
  const kpis = data.kpis;
  const maxStage = Math.max(1, ...data.stageDurations.map((item) => item.avgDurationMs));
  const maxSkill = Math.max(1, ...data.skillDistribution.map((item) => item.count));
  const hasTasks = kpis.totalTasks > 0;

  const kpiItems = [
    { label: "生成任务", value: String(kpis.totalTasks), hint: "Agent 运行次数", icon: Workflow, accent: "bg-moss-700" },
    { label: "任务完成率", value: formatPercent(kpis.taskCompletionRate ?? kpis.successRate), hint: "已产出报告 / 总任务", icon: CheckCircle2, accent: "bg-emerald-600" },
    { label: "质量通过率", value: formatPercent(kpis.qualityPassRate ?? kpis.successRate), hint: "质量门控 PASS", icon: ShieldCheck, accent: "bg-teal-600" },
    { label: "平均耗时", value: formatMonitoringSeconds(kpis.avgDurationSeconds), hint: "端到端生成", icon: Clock3, accent: "bg-sky-600" },
    { label: "P95 耗时", value: formatMonitoringSeconds(kpis.p95DurationSeconds), hint: "慢请求画像", icon: BarChart3, accent: "bg-indigo-600" },
    { label: "动态任务规划率", value: formatPercent(kpis.dynamicPlannerRate), hint: "动态任务规划占比", icon: Sparkles, accent: "bg-amber-500" },
    { label: "改写触发率", value: formatPercent(kpis.rewriteTriggerRate ?? kpis.rewriteRate), hint: "触发自动改写", icon: RefreshCw, accent: "bg-rose-500" },
    { label: "改写采纳率", value: formatPercent(kpis.rewriteAcceptRate ?? 0), hint: "改写优于初稿", icon: CheckCircle2, accent: "bg-lime-600" }
  ];

  return (
    <section className="monitoring-surface relative mt-3 rounded-xl pb-8">
      <div className="relative z-10">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {kpiItems.map((item) => (
          <Card key={item.label} className="group overflow-hidden border-slate-200 bg-white p-0 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-moss-200 hover:shadow-md">
            <div className={`h-1 ${item.accent}`} />
            <div className="p-3">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500">{item.label}</span>
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-50 text-slate-500 transition group-hover:bg-moss-50 group-hover:text-moss-700">
                  <item.icon size={15} />
                </span>
              </div>
              <p className="text-2xl font-bold tracking-normal text-slate-950">{item.value}</p>
              <p className="mt-1 text-[11px] text-slate-500">{item.hint}</p>
            </div>
          </Card>
        ))}
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1.08fr)_minmax(380px,0.92fr)]">
        <div className="grid gap-3">
          <Card className="overflow-hidden border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss-700">AGENT LOOP</p>
                <h2 className="mt-1 text-lg font-bold text-slate-950">阶段平均耗时</h2>
              </div>
              <button
                type="button"
                onClick={() => void onRefresh()}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-xs text-slate-600 transition hover:border-moss-500 hover:text-moss-800"
              >
                <RefreshCw size={14} className={loading ? "animate-spin" : undefined} />
                刷新
              </button>
            </div>
            {loading && !hasTasks ? (
              <MonitoringEmpty label="正在读取真实任务数据" />
            ) : data.stageDurations.length === 0 ? (
              <MonitoringEmpty label="还没有可聚合的 Agent trace" />
            ) : (
              <div className="space-y-4">
                {data.stageDurations.map((item) => (
                  <div key={item.stage}>
                    <div className="mb-1.5 flex items-center justify-between text-xs">
                      <span className="font-medium text-slate-700">{item.label}</span>
                      <span className="text-slate-500">{formatMonitoringMs(item.avgDurationMs)}</span>
                    </div>
                    <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="monitoring-bar h-2.5 rounded-full bg-moss-700 shadow-[0_0_0_1px_rgba(10,94,74,0.08)]"
                        style={{ width: `${barPercent(item.avgDurationMs, maxStage)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card className="overflow-hidden border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-4 flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss-700">RECENT RUNS</p>
                <h2 className="mt-1 text-lg font-bold text-slate-950">最近任务</h2>
              </div>
              <span className="rounded-full bg-slate-50 px-2.5 py-1 text-xs text-slate-500">{data.recentTasks.length} 条</span>
            </div>
            {data.recentTasks.length === 0 ? (
              <MonitoringEmpty label="生成一次报告后，这里会出现真实运行记录" />
            ) : (
              <div className="overflow-auto">
                <div className="grid min-w-[620px] grid-cols-[1.1fr_92px_88px_88px_88px] border-b border-slate-100 pb-2 text-xs font-medium text-slate-500">
                  <span>作业</span>
                  <span>状态</span>
                  <span>Skill</span>
                  <span>耗时</span>
                  <span>证据</span>
                </div>
                <div className="min-w-[620px] divide-y divide-slate-100">
                  {data.recentTasks.map((task) => (
                    <div key={task.taskId} className="grid grid-cols-[1.1fr_92px_88px_88px_88px] items-center py-2.5 text-sm">
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-900">{task.assignmentTitle}</p>
                        <p className="mt-0.5 text-xs text-slate-500">{formatDateTime(task.createdAt)}</p>
                      </div>
                      <span className={`inline-flex w-fit items-center rounded-full px-2 py-0.5 text-xs font-medium ${monitoringStatusClass(task.status)}`}>{statusText(task.status)}</span>
                      <span className="truncate text-xs text-slate-600">{skillLabel(task.resolvedSkillId)}</span>
                      <span className="text-xs text-slate-600">{formatMonitoringSeconds(task.durationSeconds ?? 0)}</span>
                      <span className="text-xs text-slate-600">{task.retrievedChunks ?? 0} 段</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </div>

        <div className="grid gap-3">
          <Card className="overflow-hidden border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss-700">ROUTING</p>
              <h2 className="mt-1 text-lg font-bold text-slate-950">任务类型识别分布</h2>
            </div>
            {data.skillDistribution.length === 0 ? (
              <MonitoringEmpty label="暂无任务类型识别样本" />
            ) : (
              <div className="space-y-3">
                {data.skillDistribution.map((item) => (
                  <div key={item.skillId} className="rounded-lg border border-slate-100 bg-white/70 p-3 shadow-sm transition hover:border-moss-100 hover:bg-moss-50/30">
                    <div className="mb-2 flex items-center justify-between text-sm">
                      <span className="font-medium text-slate-900">{item.label}</span>
                      <span className="text-xs text-slate-500">{item.count} 次</span>
                    </div>
                    <div className="h-2.5 overflow-hidden rounded-full bg-slate-50">
                      <div className="monitoring-bar h-2.5 rounded-full bg-moss-600" style={{ width: `${barPercent(item.count, maxSkill)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card className="overflow-hidden border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss-700">RESOURCES</p>
              <h2 className="mt-1 text-lg font-bold text-slate-950">资料与报告资产</h2>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <ResourceMini label="作业" value={data.resourceStats.assignments} />
              <ResourceMini label="资料" value={data.resourceStats.materials} />
              <ResourceMini label="已索引" value={data.resourceStats.indexedMaterials} />
              <ResourceMini label="报告" value={data.resourceStats.reports} />
            </div>
            <div className="mt-4 rounded-lg border border-moss-100 bg-moss-50/60 p-3">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium text-moss-900">平均资料 / 作业</span>
                <span className="text-lg font-bold text-moss-900">{data.resourceStats.avgMaterialsPerAssignment.toFixed(1)}</span>
              </div>
              <div className="mt-3 h-2 rounded-full bg-white">
                <div
                  className="h-2 rounded-full bg-moss-700"
                  style={{ width: `${Math.min(100, data.resourceStats.avgMaterialsPerAssignment * 35)}%` }}
                />
              </div>
            </div>
            <div className="mt-4 rounded-lg border border-slate-100 bg-white p-3 text-xs leading-5 text-slate-500">
              这些指标来自 MySQL 中持久化的 Agent Task、质量指标和 Trace。后续 Redis memory 可以承接运行中状态与最近访问上下文，用于 SSE 重连恢复。
            </div>
          </Card>
        </div>
      </div>
      </div>
    </section>
  );
}

function MonitoringEmpty({ label }: { label: string }) {
  return (
    <div className="flex min-h-[140px] items-center justify-center rounded-lg border border-dashed border-moss-200 bg-white px-4 text-center text-sm text-slate-500">
      {label}
    </div>
  );
}

function ResourceMini({ label, value }: { label: string; value: number }) {
  return (
    <div className="group rounded-lg border border-slate-100 bg-white p-3 shadow-sm transition hover:-translate-y-0.5 hover:border-moss-100 hover:bg-moss-50">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs text-slate-500">{label}</p>
        <span className="h-1.5 w-1.5 rounded-full bg-moss-600 opacity-50 transition group-hover:opacity-100" />
      </div>
      <p className="text-2xl font-bold text-slate-950">{value}</p>
    </div>
  );
}

function Metric({ icon: Icon, value, label, hint, tone = "green", onClick }: { icon: LucideIcon; value: number; label: string; hint: string; tone?: "green" | "blue" | "red"; onClick?: () => void }) {
  const toneClass =
    tone === "red" ? "bg-red-50 text-red-700" : tone === "blue" ? "bg-sky-50 text-sky-700" : "bg-moss-50 text-moss-700";
  const content = (
    <>
      <div className="flex items-center gap-3">
        <div className={`flex h-9 w-9 items-center justify-center rounded-full ${toneClass}`}>
          <Icon size={18} />
        </div>
        <div>
          <p className="text-xl font-bold leading-5 text-slate-950">{value}</p>
          <p className="mt-1 text-xs font-medium text-slate-700">{label}</p>
          <p className="text-[11px] text-slate-500">{hint}</p>
        </div>
      </div>
      <ChevronRight size={16} className="text-slate-500" />
    </>
  );
  return (
    <Card className={`min-h-[64px] p-0 ${onClick ? "transition hover:-translate-y-0.5 hover:border-moss-500 hover:shadow-md" : ""}`}>
      {onClick ? (
        <button type="button" onClick={onClick} className="flex min-h-[64px] w-full items-center justify-between p-3 text-left">
          {content}
        </button>
      ) : (
        <div className="flex min-h-[64px] items-center justify-between p-3">{content}</div>
      )}
    </Card>
  );
}

function InfoItem({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "red" }) {
  return (
    <div>
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className={`mt-0.5 text-sm font-medium leading-5 ${tone === "red" ? "text-red-700" : "text-slate-900"}`}>{value}</p>
    </div>
  );
}

function StatusBadge({ status }: { status?: string }) {
  const normalized = status || "DRAFT";
  let className = "bg-slate-100 text-slate-600";
  if (normalized === "DONE" || normalized === "SUCCEEDED" || normalized === "INDEXED") {
    className = "bg-moss-50 text-moss-700";
  } else if (normalized === "FAILED") {
    className = "bg-red-50 text-red-700";
  } else if (normalized === "NEEDS_REWRITE" || normalized === "NEEDS_USER_INPUT") {
    className = "bg-amber-50 text-amber-700";
  } else if (normalized === "RUNNING" || normalized === "READY" || normalized === "INDEXING") {
    className = "bg-emerald-50 text-emerald-700";
  }
  return <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>{statusText(normalized)}</span>;
}

function StepIcon({ status }: { status: string }) {
  if (status === "SUCCEEDED") return <CheckCircle2 size={19} className="text-moss-700" />;
  if (status === "FAILED") return <Circle size={19} className="text-red-600" />;
  if (status === "NEEDS_REWRITE" || status === "NEEDS_USER_INPUT") return <Circle size={19} className="text-amber-600" />;
  if (status === "RUNNING") return <Loader2 size={19} className="animate-spin text-moss-700" />;
  return <Circle size={19} className="text-slate-400" />;
}

function statusText(status: string) {
  const labels: Record<string, string> = {
    DRAFT: "草稿",
    READY: "就绪",
    DONE: "已生成",
    QUEUED: "等待中",
    RUNNING: "进行中",
    SUCCEEDED: "已完成",
    FAILED: "失败",
    NEEDS_REWRITE: "需人工审核修改",
    NEEDS_USER_INPUT: "需补充资料",
    PENDING: "未索引",
    INDEXING: "索引中",
    INDEXED: "已索引"
  };
  return labels[status] || status;
}

function stageLabel(stage: string) {
  const labels: Record<string, string> = {
    queued: "任务排队",
    skill: "任务类型识别",
    parse: "资料解析",
    retrieve: "RAG 检索",
    generate: "生成报告草稿",
    quality: "质量检查",
    rewrite: "自动改写",
    done: "完成",
    failed: "失败"
  };
  return labels[stage] || stage;
}

function latestStageLogs(logs: AgentTaskLog[]) {
  const byStage = new Map<string, AgentTaskLog>();
  for (const log of logs) byStage.set(log.stage, log);
  return ["queued", "skill", "parse", "retrieve", "generate", "quality", "rewrite", "done", "failed"]
    .map((stage) => byStage.get(stage))
    .filter((log): log is AgentTaskLog => Boolean(log));
}

function skillLabel(skillId?: string) {
  const labels: Record<string, string> = {
    AUTO: "智能识别",
    lab_report: "实验报告",
    paper_summary: "论文总结",
    course_qa_report: "课程问答汇报",
    dynamic_planner: "动态任务规划"
  };
  return skillId ? labels[skillId] || skillId : "待识别";
}

function normalizeMarkdown(markdown: string) {
  const trimmed = markdown.trim();
  const fenced = trimmed.match(/^```(?:markdown|md)?\s*\n([\s\S]*?)\n```$/i);
  return fenced ? fenced[1].trim() : trimmed;
}

function formatDue(dueAt?: string) {
  return dueAt ? dueAt.replace("T", " ").slice(0, 16) : "未设置";
}

function formatDateTime(value?: string) {
  return value ? value.replace("T", " ").slice(0, 16) : "暂无时间";
}

function formatRefreshTime(value: Date | null) {
  if (!value) return "等待同步";
  return `今天 ${value.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })}`;
}

function formatDuration(startedAt?: string, finishedAt?: string) {
  if (!startedAt) return "未开始";
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const start = new Date(startedAt).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "计算中";
  const seconds = Math.max(1, Math.round((end - start) / 1000));
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function formatPercent(value: number) {
  return `${Math.round((Number.isFinite(value) ? value : 0) * 100)}%`;
}

function formatMonitoringSeconds(value?: number | null) {
  const seconds = Math.max(0, Math.round(value ?? 0));
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function formatMonitoringMs(value: number) {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${Math.round(value)}ms`;
}

function barPercent(value: number, max: number) {
  if (!max || value <= 0) {
    return 0;
  }
  return Math.max(8, Math.min(100, Math.round((value / max) * 100)));
}

function monitoringStatusClass(status: string) {
  if (status === "SUCCEEDED") return "bg-moss-50 text-moss-700";
  if (status === "FAILED") return "bg-red-50 text-red-700";
  if (status === "RUNNING" || status === "QUEUED") return "bg-amber-50 text-amber-700";
  return "bg-slate-100 text-slate-600";
}

function isOverdue(dueAt?: string) {
  return dueAt ? new Date(dueAt).getTime() < Date.now() : false;
}

function formatSize(size: number) {
  return size > 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MB` : `${(size / 1024).toFixed(1)} KB`;
}

function fileKind(filename: string) {
  return filename.toLowerCase().endsWith(".pdf") ? "PDF" : filename.toLowerCase().endsWith(".txt") ? "TXT" : "Markdown";
}

function overviewTitle(kind: "materials" | "reports" | "overdue") {
  const labels = {
    materials: "资料库",
    reports: "报告草稿",
    overdue: "过期作业"
  };
  return labels[kind];
}
