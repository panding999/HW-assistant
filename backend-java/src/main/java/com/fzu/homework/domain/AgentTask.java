package com.fzu.homework.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import java.time.LocalDateTime;

@TableName("agent_tasks")
public class AgentTask {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long assignmentId;
    private String type;
    private String status;
    private String currentStage;
    private String errorMessage;
    private String resolvedSkillId;
    private Double routingConfidence;
    private String routingReason;
    private String retrievedEvidenceJson;
    private String qualityMetricsJson;
    private String agentTraceJson;
    private String draftVersionReason;
    private LocalDateTime startedAt;
    private LocalDateTime finishedAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getAssignmentId() { return assignmentId; }
    public void setAssignmentId(Long assignmentId) { this.assignmentId = assignmentId; }
    public String getType() { return type; }
    public void setType(String type) { this.type = type; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getCurrentStage() { return currentStage; }
    public void setCurrentStage(String currentStage) { this.currentStage = currentStage; }
    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String errorMessage) { this.errorMessage = errorMessage; }
    public String getResolvedSkillId() { return resolvedSkillId; }
    public void setResolvedSkillId(String resolvedSkillId) { this.resolvedSkillId = resolvedSkillId; }
    public Double getRoutingConfidence() { return routingConfidence; }
    public void setRoutingConfidence(Double routingConfidence) { this.routingConfidence = routingConfidence; }
    public String getRoutingReason() { return routingReason; }
    public void setRoutingReason(String routingReason) { this.routingReason = routingReason; }
    public String getRetrievedEvidenceJson() { return retrievedEvidenceJson; }
    public void setRetrievedEvidenceJson(String retrievedEvidenceJson) { this.retrievedEvidenceJson = retrievedEvidenceJson; }
    public String getQualityMetricsJson() { return qualityMetricsJson; }
    public void setQualityMetricsJson(String qualityMetricsJson) { this.qualityMetricsJson = qualityMetricsJson; }
    public String getAgentTraceJson() { return agentTraceJson; }
    public void setAgentTraceJson(String agentTraceJson) { this.agentTraceJson = agentTraceJson; }
    public String getDraftVersionReason() { return draftVersionReason; }
    public void setDraftVersionReason(String draftVersionReason) { this.draftVersionReason = draftVersionReason; }
    public LocalDateTime getStartedAt() { return startedAt; }
    public void setStartedAt(LocalDateTime startedAt) { this.startedAt = startedAt; }
    public LocalDateTime getFinishedAt() { return finishedAt; }
    public void setFinishedAt(LocalDateTime finishedAt) { this.finishedAt = finishedAt; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
