export type Assignment = {
  id: number;
  title: string;
  course?: string;
  description?: string;
  dueAt?: string;
  skillId?: string;
  resolvedSkillId?: string;
  status: "DRAFT" | "READY" | "DONE" | string;
  createdAt?: string;
};

export type Material = {
  id: number;
  assignmentId: number;
  filename: string;
  contentType?: string;
  sizeBytes: number;
  storagePath: string;
  indexStatus: string;
  errorMessage?: string;
};

export type Report = {
  id: number;
  assignmentId: number;
  title: string;
  markdown: string;
  version: number;
  createdAt?: string;
  updatedAt?: string;
};

export type AgentTask = {
  id: number;
  assignmentId: number;
  type: string;
  status: string;
  currentStage?: string;
  errorMessage?: string;
  startedAt?: string;
  finishedAt?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type AgentTaskLog = {
  id?: number;
  taskId: number;
  stage: string;
  status: string;
  message: string;
  createdAt?: string;
};

export type AssignmentDetail = {
  assignment: Assignment;
  materials: Material[];
  report?: Report | null;
};

export type DashboardSummary = {
  assignments: number;
  materials: number;
  reports: number;
  overdue: number;
};
