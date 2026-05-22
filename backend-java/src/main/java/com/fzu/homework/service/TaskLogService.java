package com.fzu.homework.service;

import com.fzu.homework.domain.AgentTask;
import com.fzu.homework.domain.AgentTaskLog;
import com.fzu.homework.dto.TaskLogMessage;
import com.fzu.homework.mapper.AgentTaskLogMapper;
import com.fzu.homework.mapper.AgentTaskMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

@Service
public class TaskLogService {
    private static final Logger log = LoggerFactory.getLogger(TaskLogService.class);
    private static final long SSE_TIMEOUT_MS = 10 * 60 * 1000L;
    private final AgentTaskMapper taskMapper;
    private final AgentTaskLogMapper logMapper;
    private final ConcurrentHashMap<Long, CopyOnWriteArrayList<SseEmitter>> emitters = new ConcurrentHashMap<>();

    public TaskLogService(
            AgentTaskMapper taskMapper,
            AgentTaskLogMapper logMapper
    ) {
        this.taskMapper = taskMapper;
        this.logMapper = logMapper;
    }

    public SseEmitter subscribe(Long taskId) {
        if (taskMapper.selectById(taskId) == null) {
            throw new IllegalArgumentException("Task not found: " + taskId);
        }

        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT_MS);
        emitters.computeIfAbsent(taskId, ignored -> new CopyOnWriteArrayList<>()).add(emitter);
        log.info("task_log_subscribe taskId={} subscribers={}", taskId, emitters.get(taskId).size());

        emitter.onCompletion(() -> removeEmitter(taskId, emitter));
        emitter.onTimeout(() -> removeEmitter(taskId, emitter));
        emitter.onError(ignored -> removeEmitter(taskId, emitter));

        try {
            emitter.send(SseEmitter.event().name("ready").data("connected"));
            List<AgentTaskLog> history = logMapper.selectList(
                    Wrappers.<AgentTaskLog>lambdaQuery()
                            .eq(AgentTaskLog::getTaskId, taskId)
                            .orderByAsc(AgentTaskLog::getCreatedAt)
            );
            for (AgentTaskLog log : history) {
                emitter.send(SseEmitter.event().name("log").data(toMessage(log)));
            }
        } catch (Exception ex) {
            log.debug("task_log_subscribe_send_failed taskId={}", taskId, ex);
            removeEmitter(taskId, emitter);
        }

        return emitter;
    }

    public void push(Long taskId, String stage, String status, String message) {
        AgentTaskLog log = new AgentTaskLog();
        log.setTaskId(taskId);
        log.setStage(stage);
        log.setStatus(status);
        log.setMessage(message);
        logMapper.insert(log);
        TaskLogService.log.info("task_log_push taskId={} stage={} status={} message={}", taskId, stage, status, message);

        AgentTask task = taskMapper.selectById(taskId);
        if (task != null) {
            task.setCurrentStage(stage);
            task.setStatus(toTaskStatus(stage, status));
            taskMapper.updateById(task);
        }

        TaskLogMessage event = new TaskLogMessage(
                taskId,
                stage,
                status,
                message,
                LocalDateTime.now()
        );
        for (SseEmitter emitter : emitters.getOrDefault(taskId, new CopyOnWriteArrayList<>())) {
            try {
                emitter.send(SseEmitter.event().name("log").data(event));
                if ("FAILED".equals(status) || ("done".equals(stage) && isTerminalStatus(status))) {
                    emitter.complete();
                }
            } catch (Exception ex) {
                TaskLogService.log.debug("task_log_push_send_failed taskId={} stage={} status={}", taskId, stage, status, ex);
                removeEmitter(taskId, emitter);
            }
        }
    }

    private TaskLogMessage toMessage(AgentTaskLog log) {
        return new TaskLogMessage(
                log.getTaskId(),
                log.getStage(),
                log.getStatus(),
                log.getMessage(),
                log.getCreatedAt()
        );
    }

    private String toTaskStatus(String stage, String status) {
        if ("FAILED".equals(status)) {
            return "FAILED";
        }
        if ("done".equals(stage) && isTerminalStatus(status)) {
            return status;
        }
        if ("queued".equals(stage) && "QUEUED".equals(status)) {
            return "QUEUED";
        }
        return "RUNNING";
    }

    private boolean isTerminalStatus(String status) {
        return "SUCCEEDED".equals(status)
                || "NEEDS_REWRITE".equals(status)
                || "NEEDS_USER_INPUT".equals(status);
    }

    private void removeEmitter(Long taskId, SseEmitter emitter) {
        CopyOnWriteArrayList<SseEmitter> taskEmitters = emitters.get(taskId);
        if (taskEmitters == null) {
            return;
        }
        taskEmitters.remove(emitter);
        if (taskEmitters.isEmpty()) {
            emitters.remove(taskId);
        }
    }
}
