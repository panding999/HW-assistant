import type {
  AgentTask,
  AgentTaskLog,
  Assignment,
  AssignmentDetail,
  DashboardSummary,
  Material,
  Report
} from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? init.headers
        : {
            "Content-Type": "application/json",
            ...init?.headers
          },
    cache: "no-store"
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.message || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  summary: () => request<DashboardSummary>("/api/dashboard/summary"),
  assignments: (params?: { keyword?: string; status?: string; sort?: string }) => {
    const search = new URLSearchParams();
    if (params?.keyword) search.set("keyword", params.keyword);
    if (params?.status && params.status !== "ALL") search.set("status", params.status);
    if (params?.sort) search.set("sort", params.sort);
    const query = search.toString();
    return request<Assignment[]>(`/api/assignments${query ? `?${query}` : ""}`);
  },
  createAssignment: (body: {
    title: string;
    course?: string;
    description?: string;
    dueAt?: string;
    skillId?: string;
  }) =>
    request<Assignment>("/api/assignments", {
      method: "POST",
      body: JSON.stringify(body)
    }),
  updateAssignment: (
    id: number,
    body: {
      title: string;
      course?: string;
      description?: string;
      dueAt?: string;
      skillId?: string;
    }
  ) =>
    request<Assignment>(`/api/assignments/${id}`, {
      method: "PUT",
      body: JSON.stringify(body)
    }),
  deleteAssignment: (id: number) =>
    request<{ message: string }>(`/api/assignments/${id}`, {
      method: "DELETE"
    }),
  assignmentDetail: (id: number) =>
    request<AssignmentDetail>(`/api/assignments/${id}`),
  uploadMaterial: (assignmentId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Material>(`/api/assignments/${assignmentId}/materials`, {
      method: "POST",
      body: form
    });
  },
  deleteMaterial: (id: number) =>
    request<{ message: string }>(`/api/materials/${id}`, {
      method: "DELETE"
    }),
  generate: (assignmentId: number) =>
    request<AgentTask>(`/api/assignments/${assignmentId}/generate`, {
      method: "POST"
    }),
  task: (taskId: number) =>
    request<{ task: AgentTask; logs: AgentTaskLog[] }>(`/api/tasks/${taskId}`),
  assignmentTasks: (assignmentId: number) =>
    request<AgentTask[]>(`/api/assignments/${assignmentId}/tasks`),
  retryTask: (taskId: number) =>
    request<AgentTask>(`/api/tasks/${taskId}/retry`, {
      method: "POST"
    }),
  report: (assignmentId: number) =>
    request<Report>(`/api/reports/${assignmentId}`),
  updateReport: (reportId: number, markdown: string) =>
    request<Report>(`/api/reports/${reportId}`, {
      method: "PUT",
      body: JSON.stringify({ markdown })
    }),
  exportReportUrl: (assignmentId: number) =>
    `${API_BASE_URL}/api/reports/${assignmentId}/export`
};
