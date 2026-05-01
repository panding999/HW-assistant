package com.fzu.homework.dto;

import java.time.LocalDateTime;

public class TaskLogMessage {
    private Long taskId;
    private String stage;
    private String status;
    private String message;
    private LocalDateTime createdAt;

    public TaskLogMessage() {
    }

    public TaskLogMessage(Long taskId, String stage, String status, String message, LocalDateTime createdAt) {
        this.taskId = taskId;
        this.stage = stage;
        this.status = status;
        this.message = message;
        this.createdAt = createdAt;
    }

    public Long getTaskId() { return taskId; }
    public void setTaskId(Long taskId) { this.taskId = taskId; }
    public String getStage() { return stage; }
    public void setStage(String stage) { this.stage = stage; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
