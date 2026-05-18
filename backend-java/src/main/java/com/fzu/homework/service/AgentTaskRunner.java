package com.fzu.homework.service;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AgentTaskRunner {
    private final AgentWorkflowService agentWorkflowService;

    public AgentTaskRunner(AgentWorkflowService agentWorkflowService) {
        this.agentWorkflowService = agentWorkflowService;
    }

    @Async
    public void runReportTask(Long taskId) {
        agentWorkflowService.runReportTask(taskId);
    }

    @Async
    public void runImproveReportTask(Long taskId) {
        agentWorkflowService.runImproveReportTask(taskId);
    }
}
