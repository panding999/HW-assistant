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
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.time.LocalDateTime;

@Service
public class AgentWorkflowService {
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
            return;
        }

        String currentStage = "queued";
        try {
            task.setStatus("RUNNING");
            task.setStartedAt(LocalDateTime.now());
            taskMapper.updateById(task);

            Assignment assignment = assignmentMapper.selectById(task.getAssignmentId());
            if (assignment == null) {
                throw new IllegalStateException("Assignment not found.");
            }

            List<Material> materials = materialMapper.selectList(
                    Wrappers.<Material>lambdaQuery()
                            .eq(Material::getAssignmentId, assignment.getId())
            );
            if (materials.isEmpty()) {
                throw new IllegalStateException("Please upload at least one material before generating a report.");
            }

            currentStage = "parse";
            taskLogService.push(taskId, currentStage, "RUNNING", "正在解析资料并准备向量化。");
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

            materials.forEach(material -> {
                material.setIndexStatus("INDEXED");
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
            reportPayload.put("top_k", 8);

            taskLogService.push(taskId, currentStage, "SUCCEEDED", "已检索到相关资料，准备生成报告。");
            currentStage = "generate";
            taskLogService.push(taskId, currentStage, "RUNNING", "正在调用 Qwen 生成实验报告草稿。");
            Map<?, ?> reportResponse = restClient.post()
                    .uri("/agent/generate-report")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .body(toJson(reportPayload))
                    .retrieve()
                    .body(Map.class);
            Object markdownValue = reportResponse == null ? "" : reportResponse.get("markdown");
            String markdown = markdownValue == null ? "" : String.valueOf(markdownValue);

            upsertReport(assignment, markdown);
            assignment.setStatus("DONE");
            assignmentMapper.updateById(assignment);
            AgentTask completed = taskMapper.selectById(taskId);
            if (completed != null) {
                completed.setStatus("SUCCEEDED");
                completed.setCurrentStage("done");
                completed.setFinishedAt(LocalDateTime.now());
                completed.setErrorMessage(null);
                taskMapper.updateById(completed);
            }
            taskLogService.push(taskId, currentStage, "SUCCEEDED", "报告草稿已生成，可以开始编辑。");
            taskLogService.push(taskId, "done", "SUCCEEDED", "任务完成。");
        } catch (Exception ex) {
            String friendlyMessage = friendlyError(ex.getMessage());
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
        if (message.contains("500 Internal Server Error")) {
            return "Agent 服务执行失败，请查看 agent-python 日志。";
        }
        return message;
    }

    private Map<String, Object> materialPayload(Material material) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("id", material.getId());
        payload.put("filename", material.getFilename());
        payload.put("path", material.getStoragePath());
        payload.put("content_type", material.getContentType());
        return payload;
    }

    private void upsertReport(Assignment assignment, String markdown) {
        Report report = reportMapper.selectOne(
                Wrappers.<Report>lambdaQuery().eq(Report::getAssignmentId, assignment.getId())
        );
        if (report == null) {
            report = new Report();
            report.setAssignmentId(assignment.getId());
            report.setTitle(assignment.getTitle() + " 实验报告");
            report.setMarkdown(markdown);
            report.setVersion(1);
            reportMapper.insert(report);
        } else {
            report.setMarkdown(markdown);
            report.setVersion(report.getVersion() == null ? 1 : report.getVersion() + 1);
            reportMapper.updateById(report);
        }
    }
}
