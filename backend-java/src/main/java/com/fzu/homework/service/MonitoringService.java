package com.fzu.homework.service;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fzu.homework.domain.AgentTask;
import com.fzu.homework.domain.Assignment;
import com.fzu.homework.domain.Material;
import com.fzu.homework.domain.Report;
import com.fzu.homework.mapper.AgentTaskMapper;
import com.fzu.homework.mapper.AssignmentMapper;
import com.fzu.homework.mapper.MaterialMapper;
import com.fzu.homework.mapper.ReportMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

@Service
public class MonitoringService {
    private static final Logger log = LoggerFactory.getLogger(MonitoringService.class);
    private static final String GENERATE_REPORT = "GENERATE_REPORT";

    private final AssignmentMapper assignmentMapper;
    private final MaterialMapper materialMapper;
    private final ReportMapper reportMapper;
    private final AgentTaskMapper taskMapper;
    private final ObjectMapper objectMapper;

    public MonitoringService(
            AssignmentMapper assignmentMapper,
            MaterialMapper materialMapper,
            ReportMapper reportMapper,
            AgentTaskMapper taskMapper,
            ObjectMapper objectMapper
    ) {
        this.assignmentMapper = assignmentMapper;
        this.materialMapper = materialMapper;
        this.reportMapper = reportMapper;
        this.taskMapper = taskMapper;
        this.objectMapper = objectMapper;
    }

    public Map<String, Object> overview() {
        long started = System.nanoTime();
        List<Assignment> assignments = assignmentMapper.selectList(null);
        List<Material> materials = materialMapper.selectList(null);
        List<Report> reports = reportMapper.selectList(null);
        List<AgentTask> tasks = taskMapper.selectList(
                Wrappers.<AgentTask>lambdaQuery()
                        .eq(AgentTask::getType, GENERATE_REPORT)
                        .orderByDesc(AgentTask::getCreatedAt)
        );

        Map<Long, String> assignmentTitles = assignments.stream()
                .collect(Collectors.toMap(Assignment::getId, Assignment::getTitle, (left, right) -> left));
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("kpis", buildKpis(tasks));
        body.put("skillDistribution", buildSkillDistribution(tasks));
        body.put("stageDurations", buildStageDurations(tasks));
        body.put("recentTasks", buildRecentTasks(tasks, assignmentTitles));
        body.put("resourceStats", buildResourceStats(assignments, materials, reports));

        long durationMs = Duration.ofNanos(System.nanoTime() - started).toMillis();
        log.info(
                "monitoring_overview assignments={} materials={} reports={} tasks={} durationMs={}",
                assignments.size(),
                materials.size(),
                reports.size(),
                tasks.size(),
                durationMs
        );
        return body;
    }

    private Map<String, Object> buildKpis(List<AgentTask> tasks) {
        int totalTasks = tasks.size();
        long succeeded = tasks.stream().filter(task -> "SUCCEEDED".equals(task.getStatus())).count();
        long completed = tasks.stream().filter(this::hasReportOutput).count();
        List<Long> durations = taskDurationsSeconds(tasks);
        long dynamicPlanner = tasks.stream()
                .filter(task -> "dynamic_planner".equals(task.getResolvedSkillId()))
                .count();
        long rewriteTriggered = tasks.stream()
                .filter(task -> qualityFlag(task, "rewrite_triggered"))
                .count();
        long rewriteAccepted = tasks.stream()
                .filter(this::rewriteAccepted)
                .count();
        double avgRetrievedChunks = tasks.stream()
                .mapToDouble(this::retrievedChunks)
                .average()
                .orElse(0);

        Map<String, Object> kpis = new LinkedHashMap<>();
        kpis.put("totalTasks", totalTasks);
        kpis.put("taskCompletionRate", ratio(completed, totalTasks));
        kpis.put("qualityPassRate", ratio(succeeded, totalTasks));
        kpis.put("successRate", ratio(succeeded, totalTasks));
        kpis.put("avgDurationSeconds", roundOne(durations.stream().mapToLong(Long::longValue).average().orElse(0)));
        kpis.put("p95DurationSeconds", p95(durations));
        kpis.put("dynamicPlannerRate", ratio(dynamicPlanner, totalTasks));
        kpis.put("rewriteTriggerRate", ratio(rewriteTriggered, totalTasks));
        kpis.put("rewriteAcceptRate", ratio(rewriteAccepted, rewriteTriggered));
        kpis.put("rewriteRate", ratio(rewriteTriggered, totalTasks));
        kpis.put("avgRetrievedChunks", roundOne(avgRetrievedChunks));
        return kpis;
    }

    private List<Map<String, Object>> buildSkillDistribution(List<AgentTask> tasks) {
        Map<String, Long> counts = tasks.stream()
                .collect(Collectors.groupingBy(task -> normalizeKey(task.getResolvedSkillId(), "pending"), LinkedHashMap::new, Collectors.counting()));
        return counts.entrySet().stream()
                .sorted(Map.Entry.<String, Long>comparingByValue().reversed())
                .map(entry -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("skillId", entry.getKey());
                    item.put("label", skillLabel(entry.getKey()));
                    item.put("count", entry.getValue());
                    return item;
                })
                .toList();
    }

    private List<Map<String, Object>> buildStageDurations(List<AgentTask> tasks) {
        Map<String, List<Long>> durations = new LinkedHashMap<>();
        for (AgentTask task : tasks) {
            for (Map<String, Object> traceStep : parseList(task.getAgentTraceJson())) {
                String stage = normalizeKey(stringValue(traceStep.get("stage")), stringValue(traceStep.get("tool_name")));
                Long durationMs = longValue(traceStep.get("duration_ms"));
                if (stage == null || durationMs == null || durationMs < 0) {
                    continue;
                }
                if (durationMs == 0) {
                    durationMs = 1L;
                }
                durations.computeIfAbsent(stage, ignored -> new ArrayList<>()).add(durationMs);
            }
        }
        return durations.entrySet().stream()
                .map(entry -> {
                    double avg = entry.getValue().stream().mapToLong(Long::longValue).average().orElse(0);
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("stage", entry.getKey());
                    item.put("label", stageLabel(entry.getKey()));
                    item.put("avgDurationMs", Math.round(avg));
                    return item;
                })
                .sorted(Comparator.comparingLong(item -> -((Number) item.get("avgDurationMs")).longValue()))
                .toList();
    }

    private List<Map<String, Object>> buildRecentTasks(List<AgentTask> tasks, Map<Long, String> assignmentTitles) {
        return tasks.stream()
                .limit(10)
                .map(task -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("taskId", task.getId());
                    item.put("assignmentId", task.getAssignmentId());
                    item.put("assignmentTitle", assignmentTitles.getOrDefault(task.getAssignmentId(), "未命名作业"));
                    item.put("status", task.getStatus());
                    item.put("resolvedSkillId", task.getResolvedSkillId());
                    item.put("durationSeconds", taskDurationSeconds(task));
                    item.put("retrievedChunks", retrievedChunks(task));
                    item.put("rewriteTriggered", qualityFlag(task, "rewrite_triggered"));
                    item.put("createdAt", task.getCreatedAt());
                    return item;
                })
                .toList();
    }

    private Map<String, Object> buildResourceStats(List<Assignment> assignments, List<Material> materials, List<Report> reports) {
        long indexedMaterials = materials.stream().filter(material -> "INDEXED".equals(material.getIndexStatus())).count();
        Map<String, Object> stats = new LinkedHashMap<>();
        stats.put("assignments", assignments.size());
        stats.put("materials", materials.size());
        stats.put("indexedMaterials", indexedMaterials);
        stats.put("reports", reports.size());
        stats.put("avgMaterialsPerAssignment", roundOne(assignments.isEmpty() ? 0 : (double) materials.size() / assignments.size()));
        return stats;
    }

    private List<Long> taskDurationsSeconds(List<AgentTask> tasks) {
        return tasks.stream()
                .map(this::taskDurationSeconds)
                .filter(Objects::nonNull)
                .sorted()
                .toList();
    }

    private Long taskDurationSeconds(AgentTask task) {
        LocalDateTime startedAt = task.getStartedAt();
        LocalDateTime finishedAt = task.getFinishedAt();
        if (startedAt == null || finishedAt == null || finishedAt.isBefore(startedAt)) {
            return null;
        }
        return Math.max(0, Duration.between(startedAt, finishedAt).toSeconds());
    }

    private long p95(List<Long> sortedDurations) {
        if (sortedDurations.isEmpty()) {
            return 0;
        }
        int index = (int) Math.ceil(sortedDurations.size() * 0.95) - 1;
        return sortedDurations.get(Math.max(0, Math.min(index, sortedDurations.size() - 1)));
    }

    private boolean qualityFlag(AgentTask task, String key) {
        Object value = parseObject(task.getQualityMetricsJson()).get(key);
        return Boolean.TRUE.equals(value) || "true".equalsIgnoreCase(String.valueOf(value));
    }

    private boolean hasReportOutput(AgentTask task) {
        return "SUCCEEDED".equals(task.getStatus())
                || "NEEDS_REWRITE".equals(task.getStatus())
                || "NEEDS_USER_INPUT".equals(task.getStatus());
    }

    private boolean rewriteAccepted(AgentTask task) {
        for (Map<String, Object> traceStep : parseList(task.getAgentTraceJson())) {
            String stage = normalizeKey(stringValue(traceStep.get("stage")), "");
            String output = stringValue(traceStep.get("output_summary"));
            if ("rewrite".equals(stage) && output != null && output.contains("accepted_rewrite=true")) {
                return true;
            }
        }
        return false;
    }

    private long retrievedChunks(AgentTask task) {
        Object value = parseObject(task.getQualityMetricsJson()).get("retrieved_chunks");
        Long count = longValue(value);
        return count == null ? 0 : count;
    }

    private double ratio(long numerator, long denominator) {
        return denominator <= 0 ? 0 : roundTwo((double) numerator / denominator);
    }

    private double roundOne(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    private double roundTwo(double value) {
        return Math.round(value * 100.0) / 100.0;
    }

    private Map<String, Object> parseObject(String json) {
        if (json == null || json.isBlank()) {
            return Map.of();
        }
        try {
            return objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {});
        } catch (Exception ex) {
            log.warn("monitoring_json_parse_failed type=object errorType={}", ex.getClass().getSimpleName());
            return Map.of();
        }
    }

    private List<Map<String, Object>> parseList(String json) {
        if (json == null || json.isBlank()) {
            return List.of();
        }
        try {
            return objectMapper.readValue(json, new TypeReference<List<Map<String, Object>>>() {});
        } catch (Exception ex) {
            log.warn("monitoring_json_parse_failed type=list errorType={}", ex.getClass().getSimpleName());
            return List.of();
        }
    }

    private Long longValue(Object value) {
        if (value instanceof Number number) {
            return number.longValue();
        }
        if (value instanceof String text && !text.isBlank()) {
            try {
                return Long.parseLong(text);
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }

    private String stringValue(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private String normalizeKey(String value, String fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return value.trim().toLowerCase(Locale.ROOT);
    }

    private String skillLabel(String skillId) {
        return switch (skillId) {
            case "lab_report" -> "实验报告";
            case "paper_summary" -> "论文总结";
            case "course_qa_report" -> "课程问答";
            case "dynamic_planner" -> "动态任务规划";
            case "pending" -> "待识别";
            default -> skillId;
        };
    }

    private String stageLabel(String stage) {
        return switch (stage) {
            case "skill" -> "任务类型识别";
            case "parse" -> "资料解析";
            case "retrieve", "search_materials" -> "RAG 检索";
            case "generate", "build_report_draft" -> "生成草稿";
            case "quality", "check_sections", "check_grounding" -> "质量检查";
            case "rewrite", "rewrite_report" -> "自动改写";
            case "done" -> "完成";
            case "failed" -> "失败";
            default -> stage;
        };
    }
}
