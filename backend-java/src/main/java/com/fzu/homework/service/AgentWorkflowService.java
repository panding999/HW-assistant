package com.fzu.homework.service;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.fzu.homework.domain.AgentTask;
import com.fzu.homework.domain.Assignment;
import com.fzu.homework.domain.Material;
import com.fzu.homework.domain.Report;
import com.fzu.homework.mapper.AgentTaskMapper;
import com.fzu.homework.mapper.AssignmentMapper;
import com.fzu.homework.mapper.MaterialMapper;
import com.fzu.homework.mapper.ReportMapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Service
public class AgentWorkflowService {
    private static final Logger log = LoggerFactory.getLogger(AgentWorkflowService.class);
    private static final String AUTO_SKILL = "AUTO";
    private static final Set<String> VALID_RESOLVED_SKILLS = Set.of(
            "lab_report",
            "paper_summary",
            "course_qa_report",
            "dynamic_planner"
    );

    private final AgentTaskMapper taskMapper;
    private final AssignmentMapper assignmentMapper;
    private final MaterialMapper materialMapper;
    private final ReportMapper reportMapper;
    private final RestClient restClient;
    private final TaskLogService taskLogService;
    private final ObjectMapper objectMapper;

    public AgentWorkflowService(
            AgentTaskMapper taskMapper,
            AssignmentMapper assignmentMapper,
            MaterialMapper materialMapper,
            ReportMapper reportMapper,
            RestClient.Builder restClientBuilder,
            TaskLogService taskLogService,
            ObjectMapper objectMapper,
            @Value("${agent.base-url}") String agentBaseUrl
    ) {
        this.taskMapper = taskMapper;
        this.assignmentMapper = assignmentMapper;
        this.materialMapper = materialMapper;
        this.reportMapper = reportMapper;
        this.restClient = restClientBuilder.baseUrl(agentBaseUrl).build();
        this.taskLogService = taskLogService;
        this.objectMapper = objectMapper;
    }

    public AgentTask createReportTask(Long assignmentId) {
        Long materialCount = materialMapper.selectCount(
                Wrappers.<Material>lambdaQuery().eq(Material::getAssignmentId, assignmentId)
        );
        if (materialCount == null || materialCount == 0) {
            throw new IllegalArgumentException("请先上传 PDF、Markdown 或 TXT 资料，再生成报告草稿。");
        }

        AgentTask task = new AgentTask();
        task.setAssignmentId(assignmentId);
        task.setType("GENERATE_REPORT");
        task.setStatus("QUEUED");
        task.setCurrentStage("queued");
        taskMapper.insert(task);
        log.info("report_task_created taskId={} assignmentId={} materials={}", task.getId(), assignmentId, materialCount);
        return taskMapper.selectById(task.getId());
    }

    public AgentTask retryTask(Long taskId) {
        AgentTask oldTask = taskMapper.selectById(taskId);
        if (oldTask == null) {
            throw new IllegalArgumentException("Task not found: " + taskId);
        }
        if (!"FAILED".equals(oldTask.getStatus())) {
            throw new IllegalArgumentException("Only failed tasks can be retried.");
        }
        AgentTask task = createReportTask(oldTask.getAssignmentId());
        runReportTask(task.getId());
        return task;
    }

    @Async
    public void runReportTask(Long taskId) {
        AgentTask task = taskMapper.selectById(taskId);
        if (task == null) {
            log.warn("report_task_missing taskId={}", taskId);
            return;
        }

        String currentStage = "queued";
        long workflowStarted = System.nanoTime();
        try {
            task.setStatus("RUNNING");
            task.setStartedAt(LocalDateTime.now());
            taskMapper.updateById(task);
            log.info("report_task_start taskId={} assignmentId={}", taskId, task.getAssignmentId());

            Assignment assignment = assignmentMapper.selectById(task.getAssignmentId());
            if (assignment == null) {
                throw new IllegalStateException("Assignment not found.");
            }

            List<Material> materials = materialMapper.selectList(
                    Wrappers.<Material>lambdaQuery().eq(Material::getAssignmentId, assignment.getId())
            );
            if (materials.isEmpty()) {
                throw new IllegalStateException("Please upload at least one material before generating a report.");
            }

            currentStage = "parse";
            taskLogService.push(taskId, currentStage, "RUNNING", "正在解析资料并准备向量化。");
            long stageStarted = System.nanoTime();
            materials.forEach(material -> {
                material.setIndexStatus("INDEXING");
                material.setErrorMessage(null);
                materialMapper.updateById(material);
            });

            Map<String, Object> indexPayload = new LinkedHashMap<>();
            indexPayload.put("assignment_id", assignment.getId());
            indexPayload.put("title", assignment.getTitle());
            indexPayload.put("description", assignment.getDescription());
            indexPayload.put("materials", materials.stream().map(this::materialPayload).toList());

            Map<?, ?> indexResponse = restClient.post()
                    .uri("/agent/index")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .body(toJson(indexPayload))
                    .retrieve()
                    .body(Map.class);
            Object chunkValue = indexResponse == null ? 0 : indexResponse.get("chunks_indexed");
            int chunks = chunkValue instanceof Number ? ((Number) chunkValue).intValue() : 0;
            if (chunks == 0) {
                throw new IllegalStateException("资料无法提取有效文本，请上传可复制文本的 PDF、Markdown 或 TXT 后重试。");
            }
            log.info(
                    "report_task_stage_done taskId={} assignmentId={} stage=parse chunks={} durationMs={}",
                    taskId,
                    assignment.getId(),
                    chunks,
                    elapsedMs(stageStarted)
            );

            materials.forEach(material -> {
                material.setIndexStatus("INDEXED");
                material.setErrorMessage(null);
                materialMapper.updateById(material);
            });
            taskLogService.push(taskId, currentStage, "SUCCEEDED", "资料解析完成，已向量化 " + chunks + " 个资料片段。");

            currentStage = "retrieve";
            taskLogService.push(taskId, currentStage, "RUNNING", "正在执行 RAG 检索。");

            Map<String, Object> reportPayload = new LinkedHashMap<>();
            reportPayload.put("assignment_id", assignment.getId());
            reportPayload.put("title", assignment.getTitle());
            reportPayload.put("course", assignment.getCourse());
            reportPayload.put("description", assignment.getDescription());
            reportPayload.put("skill_id", effectiveSkillId(assignment));
            reportPayload.put("top_k", 8);

            currentStage = "generate";
            taskLogService.push(taskId, currentStage, "RUNNING", "正在调用 Agent 生成报告草稿。");
            stageStarted = System.nanoTime();
            Map<?, ?> reportResponse = restClient.post()
                    .uri("/agent/generate-report")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .body(toJson(reportPayload))
                    .retrieve()
                    .body(Map.class);

            Object markdownValue = reportResponse == null ? "" : reportResponse.get("markdown");
            String markdown = markdownValue == null ? "" : String.valueOf(markdownValue);
            String resolvedSkillId = normalizeResolvedSkillId(valueOf(reportResponse, "resolved_skill_id", "lab_report"));
            String routingMode = valueOf(reportResponse, "routing_mode", "known_skill");
            double routingConfidence = doubleValue(reportResponse, "routing_confidence", 1.0);
            String routingReason = chineseReason(valueOf(reportResponse, "routing_reason", "未返回路由原因。"), "Agent 已完成任务类型识别。");
            Object retrievedEvidence = reportResponse == null ? null : reportResponse.get("retrieved_evidence");
            Object quality = reportResponse == null ? null : reportResponse.get("quality");
            Object agentTrace = reportResponse == null ? null : reportResponse.get("agent_trace");
            String draftVersionReason = valueOf(reportResponse, "draft_version_reason", "初稿已生成。");
            int retrievedCount = listSize(retrievedEvidence);
            String qualityNote = qualityNote(quality);
            boolean rewriteTriggered = rewriteTriggered(quality);
            String finalStatus = finalStatus(quality);
            log.info(
                    "report_task_stage_done taskId={} assignmentId={} stage=generate skill={} retrieved={} rewritten={} finalStatus={} durationMs={}",
                    taskId,
                    assignment.getId(),
                    resolvedSkillId,
                    retrievedCount,
                    rewriteTriggered,
                    finalStatus,
                    elapsedMs(stageStarted)
            );

            upsertReport(assignment, markdown);
            assignment.setResolvedSkillId(resolvedSkillId);
            assignment.setStatus("DONE");
            assignmentMapper.updateById(assignment);

            AgentTask completed = taskMapper.selectById(taskId);
            if (completed != null) {
                completed.setStatus(finalStatus);
                completed.setCurrentStage("done");
                completed.setFinishedAt(LocalDateTime.now());
                completed.setErrorMessage(null);
                completed.setResolvedSkillId(resolvedSkillId);
                completed.setRoutingConfidence(routingConfidence);
                completed.setRoutingReason(routingReason);
                completed.setRetrievedEvidenceJson(toJsonOrNull(retrievedEvidence));
                completed.setQualityMetricsJson(toJsonOrNull(quality));
                completed.setAgentTraceJson(toJsonOrNull(agentTrace));
                completed.setDraftVersionReason(draftVersionReason);
                taskMapper.updateById(completed);
            }

            taskLogService.push(taskId, "retrieve", "SUCCEEDED", "RAG 检索完成，命中 " + retrievedCount + " 个资料片段。");
            taskLogService.push(taskId, "skill", "SUCCEEDED", routingMessage(resolvedSkillId, routingMode, routingConfidence, routingReason));
            taskLogService.push(taskId, "quality", finalStatus, qualityNote);
            if (rewriteTriggered) {
                taskLogService.push(taskId, "rewrite", finalStatus, draftVersionReason);
            }
            taskLogService.push(taskId, currentStage, "SUCCEEDED", "已使用 " + skillLabel(resolvedSkillId) + " 生成草稿，可以开始编辑。");
            taskLogService.push(taskId, "done", finalStatus, finalMessage(finalStatus));
            log.info(
                    "report_task_done taskId={} assignmentId={} status={} durationMs={}",
                    taskId,
                    assignment.getId(),
                    finalStatus,
                    elapsedMs(workflowStarted)
            );
        } catch (Exception ex) {
            String friendlyMessage = friendlyError(ex.getMessage());
            log.error("report_task_failed taskId={} stage={} message={}", taskId, currentStage, friendlyMessage, ex);
            Assignment assignment = task == null ? null : assignmentMapper.selectById(task.getAssignmentId());
            if ("parse".equals(currentStage) && assignment != null) {
                materialMapper.selectList(
                        Wrappers.<Material>lambdaQuery().eq(Material::getAssignmentId, assignment.getId())
                ).forEach(material -> {
                    material.setIndexStatus("FAILED");
                    material.setErrorMessage(friendlyMessage);
                    materialMapper.updateById(material);
                });
            }
            AgentTask failed = taskMapper.selectById(taskId);
            if (failed != null) {
                failed.setStatus("FAILED");
                failed.setCurrentStage(currentStage);
                failed.setErrorMessage(friendlyMessage);
                failed.setFinishedAt(LocalDateTime.now());
                taskMapper.updateById(failed);
            }
            taskLogService.push(taskId, currentStage, "FAILED", friendlyMessage);
        }
    }

    private String toJson(Map<String, Object> payload) {
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Failed to serialize Agent request.", ex);
        }
    }

    private String toJsonOrNull(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            log.warn("agent_response_json_serialize_failed type={}", value.getClass().getName(), ex);
            return null;
        }
    }

    private int listSize(Object value) {
        return value instanceof List<?> list ? list.size() : 0;
    }

    private String qualityNote(Object quality) {
        if (quality instanceof Map<?, ?> qualityMap) {
            Object note = qualityMap.get("quality_note");
            if (note != null) {
                return String.valueOf(note);
            }
            double sectionCompleteness = doubleValue(qualityMap, "section_completeness", 0);
            double citationCoverage = doubleValue(qualityMap, "citation_coverage", 0);
            int retrievedChunks = (int) doubleValue(qualityMap, "retrieved_chunks", 0);
            return "质量检查完成：章节完整率 " + String.format("%.0f%%", sectionCompleteness * 100)
                    + "，引用覆盖率 " + String.format("%.0f%%", citationCoverage * 100)
                    + "，检索片段 " + retrievedChunks + " 个。";
        }
        return "质量检查完成。";
    }

    private boolean rewriteTriggered(Object quality) {
        if (quality instanceof Map<?, ?> qualityMap) {
            Object value = qualityMap.get("rewrite_triggered");
            return value instanceof Boolean bool && bool;
        }
        return false;
    }

    private String finalStatus(Object quality) {
        if (quality instanceof Map<?, ?> qualityMap) {
            Object decision = qualityMap.get("decision");
            if (decision != null) {
                String value = String.valueOf(decision);
                if ("NEEDS_REWRITE".equals(value) || "NEEDS_USER_INPUT".equals(value)) {
                    return value;
                }
            }
        }
        return "SUCCEEDED";
    }

    private String finalMessage(String finalStatus) {
        return switch (finalStatus) {
            case "NEEDS_REWRITE" -> "草稿已保存，但模型质量门控建议继续完善。";
            case "NEEDS_USER_INPUT" -> "草稿已保存，但模型判断资料或任务信息不足，建议补充资料后再生成。";
            default -> "任务完成。";
        };
    }

    private long elapsedMs(long startedNanos) {
        return (System.nanoTime() - startedNanos) / 1_000_000;
    }

    private String friendlyError(String message) {
        if (message == null || message.isBlank()) {
            return "任务执行失败，请查看后端日志。";
        }
        if (message.contains("422 Unprocessable Entity")) {
            return "Agent 服务没有正确收到任务参数，请稍后重试。";
        }
        if (message.contains("Missing model API key")) {
            return "缺少 Qwen/DashScope API Key，请检查 .env 中的 DASHSCOPE_API_KEY。";
        }
        if (message.contains("batch size is invalid")) {
            return "向量化批次过大，请降低 EMBEDDING_BATCH_SIZE 后重试。";
        }
        if (message.contains("资料无法提取有效文本")) {
            return "资料无法提取有效文本，请上传可复制文本的 PDF、Markdown 或 TXT 后重试。";
        }
        if (message.contains("500 Internal Server Error")) {
            return "Agent 服务执行失败，请查看 agent-python 日志。";
        }
        if (message.contains("502 Bad Gateway") || message.contains("Embedding service connection failed")) {
            return "Embedding 服务连接失败，可能是 DashScope/OpenAI-compatible 网络临时中断，请稍后重试。";
        }
        return message;
    }

    public void deleteAssignmentCollection(Long assignmentId) {
        try {
            restClient.delete()
                    .uri("/agent/collections/{assignmentId}", assignmentId)
                    .retrieve()
                    .toBodilessEntity();
            log.info("agent_collection_delete_requested assignmentId={}", assignmentId);
        } catch (Exception ex) {
            log.warn("agent_collection_delete_failed assignmentId={} errorType={}", assignmentId, ex.getClass().getSimpleName());
        }
    }

    private Map<String, Object> materialPayload(Material material) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("id", material.getId());
        payload.put("filename", material.getFilename());
        payload.put("path", material.getStoragePath());
        payload.put("content_type", material.getContentType());
        return payload;
    }

    private String effectiveSkillId(Assignment assignment) {
        String requested = assignment.getSkillId();
        return requested == null || requested.isBlank() ? AUTO_SKILL : requested;
    }

    private String valueOf(Map<?, ?> body, String key, String fallback) {
        Object value = body == null ? null : body.get(key);
        return value == null ? fallback : String.valueOf(value);
    }

    private double doubleValue(Map<?, ?> body, String key, double fallback) {
        Object value = body == null ? null : body.get(key);
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        if (value != null) {
            try {
                return Double.parseDouble(String.valueOf(value));
            } catch (NumberFormatException ignored) {
                return fallback;
            }
        }
        return fallback;
    }

    private String normalizeResolvedSkillId(String value) {
        return VALID_RESOLVED_SKILLS.contains(value) ? value : "lab_report";
    }

    private String routingMessage(String skillId, String mode, double confidence, String reason) {
        String percent = String.format("%.0f%%", confidence * 100);
        String safeReason = chineseReason(reason, "Agent 已完成任务类型识别。");
        if ("dynamic_plan".equals(mode)) {
            return "任务类型识别：未高置信命中固定 Skill，进入动态任务规划。置信度 " + percent + "。原因：" + safeReason;
        }
        return "任务类型识别：命中 " + skillLabel(skillId) + "，置信度 " + percent + "。原因：" + safeReason;
    }

    private String skillLabel(String skillId) {
        return switch (skillId == null ? AUTO_SKILL : skillId) {
            case "paper_summary" -> "论文总结";
            case "course_qa_report" -> "课程问答汇报";
            case "lab_report" -> "实验报告";
            case "dynamic_planner" -> "动态任务规划";
            default -> "智能识别";
        };
    }

    private String chineseReason(String reason, String fallback) {
        if (reason == null || reason.isBlank()) {
            return fallback;
        }
        long asciiLetters = reason.chars()
                .filter(ch -> (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z'))
                .count();
        long chineseChars = reason.chars()
                .filter(ch -> ch >= 0x4e00 && ch <= 0x9fff)
                .count();
        return asciiLetters > chineseChars * 2 ? fallback : reason;
    }

    private void upsertReport(Assignment assignment, String markdown) {
        Report report = reportMapper.selectOne(
                Wrappers.<Report>lambdaQuery().eq(Report::getAssignmentId, assignment.getId())
        );
        if (report == null) {
            report = new Report();
            report.setAssignmentId(assignment.getId());
            report.setTitle(assignment.getTitle() + " 报告");
            report.setMarkdown(markdown);
            report.setVersion(1);
            reportMapper.insert(report);
            log.info("report_created assignmentId={} reportId={} version=1", assignment.getId(), report.getId());
        } else {
            report.setMarkdown(markdown);
            report.setVersion(report.getVersion() == null ? 1 : report.getVersion() + 1);
            reportMapper.updateById(report);
            log.info("report_upserted assignmentId={} reportId={} version={}", assignment.getId(), report.getId(), report.getVersion());
        }
    }
}
