package com.fzu.homework.controller;

import com.fzu.homework.domain.Report;
import com.fzu.homework.dto.ReportUpdateRequest;
import com.fzu.homework.service.ReportService;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.List;

@RestController
@RequestMapping("/api/reports")
public class ReportController {
    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/{assignmentId}")
    public Report reportByAssignment(@PathVariable Long assignmentId) {
        Report report = reportService.findByAssignment(assignmentId);
        if (report == null) {
            throw new IllegalArgumentException("Report not found for assignment: " + assignmentId);
        }
        return report;
    }

    @GetMapping
    public List<Report> reports() {
        return reportService.listAll();
    }

    @PutMapping("/{reportId}")
    public Report updateReport(@PathVariable Long reportId, @RequestBody ReportUpdateRequest request) {
        return reportService.update(reportId, request);
    }

    @GetMapping("/{assignmentId}/export")
    public ResponseEntity<byte[]> exportMarkdown(@PathVariable Long assignmentId) {
        Report report = reportService.findByAssignment(assignmentId);
        if (report == null) {
            throw new IllegalArgumentException("Report not found for assignment: " + assignmentId);
        }
        String filename = safeFilename(report.getTitle()) + ".md";
        String encoded = URLEncoder.encode(filename, StandardCharsets.UTF_8).replace("+", "%20");
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("text/markdown; charset=UTF-8"))
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename*=UTF-8''" + encoded)
                .body(report.getMarkdown().getBytes(StandardCharsets.UTF_8));
    }

    private String safeFilename(String value) {
        String cleaned = value == null || value.isBlank() ? "report" : value;
        return cleaned.replaceAll("[\\\\/:*?\"<>|]", "_");
    }
}
