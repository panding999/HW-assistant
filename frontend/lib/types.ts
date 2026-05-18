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
  resolvedSkillId?: string;
  routingConfidence?: number;
  routingReason?: string;
  retrievedEvidenceJson?: string;
  qualityMetricsJson?: string;
  agentTraceJson?: string;
  draftVersionReason?: string;
  startedAt?: string;
  finishedAt?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type AgentQualityMetrics = {
  section_completeness?: number;
  citation_coverage?: number;
  retrieved_chunks?: number;
  rewrite_triggered?: boolean;
  structure_score?: number;
  grounding_score?: number;
  specificity_score?: number;
  readiness_score?: number;
  risk_score?: number;
  total_score?: number;
  pass_score?: number;
  decision?: "PASS" | "NEEDS_REWRITE" | "NEEDS_USER_INPUT" | string;
  manual_review_reason?: string;
  review_summary?: string;
  issues?: string[];
  rewrite_focus?: string[];
  quality_note?: string;
  evaluator_model?: string;
  evaluator_mode?: "independent" | "fallback" | string;
};

export type RetrievedEvidence = {
  chunk_id: string;
  material_id?: number;
  filename?: string;
  score?: number;
  excerpt?: string;
  parent_id?: string;
  section_title?: string;
  source_type?: string;
  vector_score?: number;
  keyword_score?: number;
  hybrid_score?: number;
  document_summary?: string;
  document_outline?: string;
  section_summary?: string;
  key_terms?: string;
};

export type AgentTraceStep = {
  step_index: number;
  stage: string;
  tool_name: string;
  input_summary: string;
  output_summary: string;
  status: string;
  duration_ms: number;
  details?: Record<string, unknown>;
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

export type MonitoringOverview = {
  kpis: {
    totalTasks: number;
    successRate: number;
    taskCompletionRate?: number;
    qualityPassRate?: number;
    avgDurationSeconds: number;
    p95DurationSeconds: number;
    dynamicPlannerRate: number;
    rewriteRate: number;
    rewriteTriggerRate?: number;
    rewriteAcceptRate?: number;
    avgRetrievedChunks?: number;
  };
  skillDistribution: Array<{
    skillId: string;
    label: string;
    count: number;
  }>;
  stageDurations: Array<{
    stage: string;
    label: string;
    avgDurationMs: number;
  }>;
  recentTasks: Array<{
    taskId: number;
    assignmentId: number;
    assignmentTitle: string;
    status: string;
    resolvedSkillId?: string;
    durationSeconds?: number | null;
    retrievedChunks?: number;
    rewriteTriggered?: boolean;
    createdAt?: string;
  }>;
  resourceStats: {
    assignments: number;
    materials: number;
    indexedMaterials: number;
    reports: number;
    avgMaterialsPerAssignment: number;
  };
};
