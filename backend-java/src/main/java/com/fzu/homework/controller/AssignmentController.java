package com.fzu.homework.controller;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.fzu.homework.domain.AgentTask;
import com.fzu.homework.domain.AgentTaskLog;
import com.fzu.homework.domain.Assignment;
import com.fzu.homework.domain.Material;
import com.fzu.homework.dto.AssignmentRequest;
import com.fzu.homework.mapper.AgentTaskLogMapper;
import com.fzu.homework.mapper.AgentTaskMapper;
import com.fzu.homework.service.AgentTaskRunner;
import com.fzu.homework.service.AgentWorkflowService;
import com.fzu.homework.service.AssignmentService;
import com.fzu.homework.service.TaskLogService;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class AssignmentController {
    private final AssignmentService assignmentService;
    private final AgentWorkflowService agentWorkflowService;
    private final AgentTaskRunner agentTaskRunner;
    private final AgentTaskMapper taskMapper;
    private final AgentTaskLogMapper logMapper;
    private final TaskLogService taskLogService;

    public AssignmentController(
            AssignmentService assignmentService,
            AgentWorkflowService agentWorkflowService,
            AgentTaskRunner agentTaskRunner,
            AgentTaskMapper taskMapper,
            AgentTaskLogMapper logMapper,
            TaskLogService taskLogService
    ) {
        this.assignmentService = assignmentService;
        this.agentWorkflowService = agentWorkflowService;
        this.agentTaskRunner = agentTaskRunner;
        this.taskMapper = taskMapper;
        this.logMapper = logMapper;
        this.taskLogService = taskLogService;
    }

    @GetMapping("/dashboard/summary")
    public Map<String, Object> dashboardSummary() {
        return assignmentService.dashboardSummary();
    }

    @GetMapping("/assignments")
    public List<Assignment> assignments(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String sort
    ) {
        return assignmentService.list(keyword, status, sort);
    }

    @PostMapping("/assignments")
    public Assignment createAssignment(@RequestBody AssignmentRequest request) {
        return assignmentService.create(request);
    }

    @PutMapping("/assignments/{id}")
    public Assignment updateAssignment(@PathVariable Long id, @RequestBody AssignmentRequest request) {
        return assignmentService.update(id, request);
    }

    @DeleteMapping("/assignments/{id}")
    public Map<String, String> deleteAssignment(@PathVariable Long id) {
        assignmentService.deleteAssignment(id);
        return Map.of("message", "deleted");
    }

    @GetMapping("/assignments/{id}")
    public Map<String, Object> assignmentDetail(@PathVariable Long id) {
        return assignmentService.detail(id);
    }

    @PostMapping("/assignments/{id}/materials")
    public Material uploadMaterial(@PathVariable Long id, @RequestParam("file") MultipartFile file) {
        return assignmentService.uploadMaterial(id, file);
    }

    @DeleteMapping("/materials/{id}")
    public Map<String, String> deleteMaterial(@PathVariable Long id) {
        assignmentService.deleteMaterial(id);
        return Map.of("message", "deleted");
    }

    @GetMapping("/materials")
    public List<Material> materials() {
        return assignmentService.allMaterials();
    }

    @PostMapping("/assignments/{id}/generate")
    public AgentTask generate(@PathVariable Long id) {
        assignmentService.requireAssignment(id);
        AgentTask task = agentWorkflowService.createReportTask(id);
        agentTaskRunner.runReportTask(task.getId());
        return task;
    }

    @GetMapping("/assignments/{id}/tasks")
    public List<AgentTask> assignmentTasks(@PathVariable Long id) {
        return assignmentService.tasksOf(id);
    }

    @PostMapping("/tasks/{taskId}/retry")
    public AgentTask retryTask(@PathVariable Long taskId) {
        AgentTask task = agentWorkflowService.retryTask(taskId);
        agentTaskRunner.runReportTask(task.getId());
        return task;
    }

    @GetMapping("/tasks/{taskId}")
    public Map<String, Object> task(@PathVariable Long taskId) {
        AgentTask task = taskMapper.selectById(taskId);
        if (task == null) {
            throw new IllegalArgumentException("Task not found: " + taskId);
        }
        List<AgentTaskLog> logs = logMapper.selectList(
                Wrappers.<AgentTaskLog>lambdaQuery()
                        .eq(AgentTaskLog::getTaskId, taskId)
                        .orderByAsc(AgentTaskLog::getCreatedAt)
        );
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("task", task);
        body.put("logs", logs);
        return body;
    }

    @GetMapping(value = "/tasks/{taskId}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter taskEvents(@PathVariable Long taskId) {
        return taskLogService.subscribe(taskId);
    }
}
