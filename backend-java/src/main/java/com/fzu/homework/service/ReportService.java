package com.fzu.homework.service;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.fzu.homework.domain.Report;
import com.fzu.homework.dto.ReportUpdateRequest;
import com.fzu.homework.mapper.ReportMapper;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ReportMapper reportMapper;

    public ReportService(ReportMapper reportMapper) {
        this.reportMapper = reportMapper;
    }

    public Report findByAssignment(Long assignmentId) {
        return reportMapper.selectOne(
                Wrappers.<Report>lambdaQuery().eq(Report::getAssignmentId, assignmentId)
        );
    }

    public Report update(Long reportId, ReportUpdateRequest request) {
        Report report = reportMapper.selectById(reportId);
        if (report == null) {
            throw new IllegalArgumentException("Report not found: " + reportId);
        }
        report.setMarkdown(request.getMarkdown() == null ? "" : request.getMarkdown());
        report.setVersion(report.getVersion() == null ? 1 : report.getVersion() + 1);
        reportMapper.updateById(report);
        return reportMapper.selectById(reportId);
    }
}
