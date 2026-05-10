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

const skillOptions = [
  { value: "lab_report", label: "实验报告" },
  { value: "paper_summary", label: "论文总结" },
  { value: "course_qa_report", label: "课程问答" }
];

export default function HomePage() {
  const fileInput = useRef<HTMLInputElement | null>(null);
  const refreshInFlight = useRef(false);

  const [summary, setSummary] = useState<DashboardSummary>(initialSummary);
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
      await refresh();
      setSelectedId(saved.id);
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
          {[Home, Folder, FileText, BarChart3, Settings].map((Icon, index) => (
            <button
              key={index}
              className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                index === 0 ? "bg-moss-700 text-white" : "text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              }`}
            >
              <Icon size={19} />
            </button>
          ))}
        </nav>
        <Button variant="ghost" size="icon" title="用户">
          <UserRound size={18} />
        </Button>
      </aside>

      <section className="px-4 py-3 sm:px-6 xl:ml-16 xl:h-screen xl:overflow-hidden xl:px-6 xl:pb-5">
        <header className="mb-2 flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">FZU HOMEWORK ASSISTANT</p>
            <h1 className="mt-0.5 text-2xl font-bold tracking-normal text-slate-950">作业资料工作台</h1>
          </div>
          <div className="flex w-full flex-wrap items-center gap-2 lg:w-auto lg:flex-nowrap lg:justify-end">
            <div className="flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <div className={`flex items-center gap-2 font-medium ${refreshStatus === "failed" ? "text-red-600 dark:text-red-400" : "text-moss-700 dark:text-emerald-300"}`}>
                {isRefreshing ? <Loader2 size={16} className="animate-spin" /> : refreshStatus === "failed" ? <Circle size={16} /> : <CheckCircle2 size={16} />}
                {isRefreshing ? "同步中" : refreshStatus === "failed" ? "同步失败" : "数据已刷新"}
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">{formatRefreshTime(lastRefreshAt)}</p>
            </div>
            <Button className="h-9 px-3 text-xs" onClick={() => void refresh()} disabled={isRefreshing}>
              <RefreshCw size={15} className={isRefreshing ? "animate-spin" : undefined} />
              {isRefreshing ? "同步中" : "同步"}
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
            <input ref={fileInput} hidden type="file" accept=".pdf,.md,.markdown,.txt" onChange={uploadMaterial} />
            <Button className="h-9 w-9" variant="ghost" size="icon" onClick={toggleTheme} title={theme === "dark" ? "切换浅色" : "切换深色"}>
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </Button>
          </div>
        </header>

        <section className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-4">
          <Metric icon={BookOpen} value={summary.assignments} label="作业总数" hint="全部作业" />
          <Metric icon={Folder} value={summary.materials} label="匹配资料" hint="资源库" />
          <Metric icon={FileText} value={summary.reports} label="报告草稿" hint="已生成" tone="blue" />
          <Metric icon={Clock3} value={summary.overdue} label="已过期" hint="需要处理" tone="red" />
        </section>

        {error && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">{error}</div>}

        <section className="mt-2.5 grid gap-3 border-b border-slate-200 pb-3 xl:h-[calc(100vh-162px)] xl:min-h-0 xl:grid-cols-[300px_minmax(520px,1.08fr)_minmax(460px,0.92fr)]">
          <Card className="flex min-h-[660px] flex-col p-3 xl:min-h-0 xl:overflow-hidden">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <Folder size={16} />
                作业队列
              </h2>
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-600">{assignments.length}</span>
            </div>
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
              {assignments.map((assignment) => (
                <button
                  key={assignment.id}
                  onClick={() => setSelectedId(assignment.id)}
                  className={`w-full rounded-lg border p-3 text-left transition ${
                    selected?.id === assignment.id ? "border-moss-600 bg-moss-50 dark:bg-moss-800/30" : "border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-950">{assignment.title}</h3>
                      <p className="mt-1.5 text-xs text-slate-500">{assignment.course || "未设置课程"}</p>
                    </div>
                    <StatusBadge status={assignment.status} />
                  </div>
                  <div className="mt-2.5 flex items-center justify-between text-xs text-slate-500">
                    <span>截止：{formatDue(assignment.dueAt)}</span>
                    <ChevronRight size={17} className="text-slate-900" />
                  </div>
                </button>
              ))}
            </div>

            <div className="mt-2.5 border-t border-slate-100 pt-2.5">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">{formMode === "edit" ? "编辑作业" : "新建作业"}</h3>
                {formMode === "edit" && (
                  <button className="text-xs text-slate-500 hover:text-slate-900" onClick={() => {
                    setFormMode("create");
                    setDraft({ title: "", course: "", description: "", dueAt: "", skillId: "AUTO" });
                  }}>
                    取消
                  </button>
                )}
              </div>
              <div className="space-y-1.5">
                <input className="field" placeholder="作业标题" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
                <input className="field" placeholder="课程名称" value={draft.course} onChange={(event) => setDraft({ ...draft, course: event.target.value })} />
                <div>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="block text-xs font-medium text-slate-600">任务类型</span>
                    <span className="rounded-full bg-moss-50 px-2 py-0.5 text-[10px] font-medium text-moss-700">可自动路由</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setDraft({ ...draft, skillId: "AUTO" })}
                    className={`flex h-9 w-full items-center justify-between rounded-lg border px-2.5 text-left text-xs transition ${
                      draft.skillId === "AUTO"
                        ? "border-moss-700 bg-moss-50 text-moss-800 shadow-sm"
                        : "border-slate-200 bg-white text-slate-600 hover:border-moss-300 hover:bg-moss-50/60 dark:border-slate-700 dark:bg-slate-900"
                    }`}
                  >
                    <span className="flex min-w-0 items-center gap-2 font-semibold">
                      <Sparkles size={14} className="shrink-0" />
                      智能识别
                    </span>
                    <span className="rounded-full bg-white/80 px-2 py-0.5 text-[10px] text-moss-700 shadow-sm">推荐</span>
                  </button>
                  <div className="mt-1 grid grid-cols-3 gap-1">
                    {skillOptions.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setDraft({ ...draft, skillId: option.value })}
                        className={`h-7 rounded-md border px-1.5 text-[11px] font-medium transition ${
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
                <textarea className="field min-h-16 resize-none" placeholder="作业说明" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} />
                <Button className="h-9 w-full text-xs" variant="primary" onClick={submitAssignment} disabled={isBusy}>
                  {formMode === "edit" ? <Save size={17} /> : <Plus size={17} />}
                  {formMode === "edit" ? "保存修改" : "创建作业"}
                </Button>
              </div>
            </div>
          </Card>

          <Card className="flex min-h-[700px] flex-col overflow-hidden xl:min-h-0">
            <div className="border-b border-slate-100 p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold text-moss-700">{selected?.course || "课程概览"}</p>
                  <h2 className="mt-1 text-xl font-bold text-slate-950">{selected?.title}</h2>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={activeTask?.status || selected?.status || "DRAFT"} />
                  <Button size="icon" variant="ghost" onClick={startEditAssignment} disabled={!selected || isDemo}>
                    <Pencil size={17} />
                  </Button>
                  <Button size="icon" variant="ghost" onClick={deleteAssignment} disabled={!selected || isDemo || isBusy}>
                    <Trash2 size={17} />
                  </Button>
                </div>
              </div>
              <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3.5 dark:border-slate-800 dark:bg-slate-900">
                <div className="mb-3 grid gap-3 border-b border-slate-100 pb-3 sm:grid-cols-2 xl:grid-cols-5">
                  <InfoItem label="课程" value={selected?.course || "未设置"} />
                  <InfoItem label="截止时间" value={formatDue(selected?.dueAt)} tone={isOverdue(selected?.dueAt) ? "red" : "default"} />
                  <InfoItem label="资料数量" value={`${materials.length} 条`} />
                  <InfoItem label="选择类型" value={skillLabel(selected?.skillId)} />
                  <InfoItem label="实际执行" value={skillLabel(selected?.resolvedSkillId)} />
                </div>
                <h3 className="mb-1.5 text-sm font-semibold text-moss-700">作业说明</h3>
                <p className="whitespace-pre-line text-sm leading-6 text-slate-600">{selected?.description || "暂无作业说明。"}</p>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              <h3 className="mb-3 text-lg font-semibold">AI 工作流程</h3>
              <div className="space-y-3.5 rounded-lg border border-slate-100 bg-white/60 p-3 dark:border-slate-800 dark:bg-slate-900/60">
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

              <div className="mt-4">
                <Button className="h-9 px-3 text-xs" variant="primary" onClick={generateReport} disabled={isBusy}>
                  <FileText size={17} />
                  生成当前报告草稿
                </Button>
              </div>

              <div className="mt-5 border-t border-slate-100 pt-4">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="font-semibold">任务历史</h3>
                  <span className="text-sm text-slate-500">{taskHistory.length} 条</span>
                </div>
                {taskHistory.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">还没有生成任务。</p>
                ) : (
                  <div className="space-y-2">
                    {taskHistory.slice(0, 5).map((task) => (
                      <div key={task.id} className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-900">
                        <div>
                          <div className="flex items-center gap-2">
                            <StatusBadge status={task.status} />
                            <span className="text-slate-700">{formatDateTime(task.createdAt)}</span>
                          </div>
                          <p className="mt-1 text-xs text-slate-500">
                            阶段：{stageLabel(task.currentStage || "queued")} · 耗时：{formatDuration(task.startedAt, task.finishedAt)}
                          </p>
                        </div>
                        {task.status === "FAILED" && (
                          <Button size="sm" onClick={() => void retryTask(task.id)} disabled={isBusy}>
                            <RotateCcw size={15} />
                            重试
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="mt-5">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold">相关资料</h3>
                    <p className="mt-1 text-xs text-slate-500">上传论文、实验要求、课件或往年报告，AI 将基于这些资料生成草稿。</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-slate-500">{materials.length} 条</span>
                    <Button size="sm" onClick={() => fileInput.current?.click()} disabled={!selected || isDemo || isBusy}>
                      <Upload size={15} />
                      上传
                    </Button>
                  </div>
                </div>
                {materials.length === 0 ? (
                  <button
                    onClick={() => fileInput.current?.click()}
                    disabled={!selected || isDemo || isBusy}
                    className="flex min-h-[150px] w-full flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50/70 px-6 py-8 text-center transition hover:border-moss-600 hover:bg-moss-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900"
                  >
                    <Upload size={22} className="mb-3 text-moss-700" />
                    <p className="font-medium text-slate-900">上传资料后再生成报告</p>
                    <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">支持 PDF、Markdown、TXT。</p>
                  </button>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
                    {materials.map((material) => (
                      <div key={material.id} className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
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
                            {material.errorMessage && <p className="mt-2 text-xs leading-5 text-red-600">{material.errorMessage}</p>}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </Card>

          <Card className="flex min-h-[700px] flex-col overflow-hidden xl:min-h-0">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <FileText size={16} />
                报告草稿
              </h2>
              <div className="flex items-center gap-2">
                {report && (
                  <div className="hidden text-right text-xs text-slate-500 xl:block">
                    <p>v{report.version}</p>
                    <p>{formatDateTime(report.updatedAt)}</p>
                  </div>
                )}
                <Button className="h-8 px-2.5 text-xs" size="sm" variant={reportMode === "preview" ? "primary" : "outline"} onClick={() => setReportMode("preview")}>预览</Button>
                <Button className="h-8 px-2.5 text-xs" size="sm" variant={reportMode === "edit" ? "primary" : "outline"} onClick={() => setReportMode("edit")}>编辑</Button>
                <Button size="sm" variant="primary" onClick={saveReport} disabled={!report || report.id < 0 || isBusy}>
                  <Save size={15} />
                  保存
                </Button>
                <Button size="sm" onClick={exportReport} disabled={!report || report.id < 0}>
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
      </section>
    </main>
  );
}

function Metric({ icon: Icon, value, label, hint, tone = "green" }: { icon: LucideIcon; value: number; label: string; hint: string; tone?: "green" | "blue" | "red" }) {
  const toneClass =
    tone === "red" ? "bg-red-50 text-red-700" : tone === "blue" ? "bg-sky-50 text-sky-700" : "bg-moss-50 text-moss-700";
  return (
    <Card className="flex min-h-[64px] items-center justify-between p-3">
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
  const className =
    normalized === "DONE" || normalized === "SUCCEEDED" || normalized === "INDEXED"
      ? "bg-moss-50 text-moss-700"
      : normalized === "FAILED"
        ? "bg-red-50 text-red-700"
        : normalized === "RUNNING" || normalized === "READY" || normalized === "INDEXING"
          ? "bg-emerald-50 text-emerald-700"
          : "bg-slate-100 text-slate-600";
  return <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>{statusText(normalized)}</span>;
}

function StepIcon({ status }: { status: string }) {
  if (status === "SUCCEEDED") return <CheckCircle2 size={19} className="text-moss-700" />;
  if (status === "FAILED") return <Circle size={19} className="text-red-600" />;
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
    PENDING: "未索引",
    INDEXING: "索引中",
    INDEXED: "已索引"
  };
  return labels[status] || status;
}

function stageLabel(stage: string) {
  const labels: Record<string, string> = {
    queued: "任务排队",
    skill: "Skill 路由",
    parse: "资料解析",
    retrieve: "RAG 检索",
    generate: "生成报告草稿",
    done: "完成",
    failed: "失败"
  };
  return labels[stage] || stage;
}

function latestStageLogs(logs: AgentTaskLog[]) {
  const byStage = new Map<string, AgentTaskLog>();
  for (const log of logs) byStage.set(log.stage, log);
  return ["queued", "skill", "parse", "retrieve", "generate", "done", "failed"]
    .map((stage) => byStage.get(stage))
    .filter((log): log is AgentTaskLog => Boolean(log));
}

function skillLabel(skillId?: string) {
  const labels: Record<string, string> = {
    AUTO: "智能识别",
    lab_report: "实验报告",
    paper_summary: "论文总结",
    course_qa_report: "课程问答汇报",
    dynamic_planner: "动态规划"
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

function isOverdue(dueAt?: string) {
  return dueAt ? new Date(dueAt).getTime() < Date.now() : false;
}

function formatSize(size: number) {
  return size > 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MB` : `${(size / 1024).toFixed(1)} KB`;
}

function fileKind(filename: string) {
  return filename.toLowerCase().endsWith(".pdf") ? "PDF" : filename.toLowerCase().endsWith(".txt") ? "TXT" : "Markdown";
}
