package com.fzu.homework.service;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.fzu.homework.domain.AgentTask;
import com.fzu.homework.domain.AgentTaskLog;
import com.fzu.homework.domain.Assignment;
import com.fzu.homework.domain.Material;
import com.fzu.homework.domain.Report;
import com.fzu.homework.dto.AssignmentRequest;
import com.fzu.homework.mapper.AgentTaskLogMapper;
import com.fzu.homework.mapper.AgentTaskMapper;
import com.fzu.homework.mapper.AssignmentMapper;
import com.fzu.homework.mapper.MaterialMapper;
import com.fzu.homework.mapper.ReportMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Service
public class AssignmentService {
    private static final Logger log = LoggerFactory.getLogger(AssignmentService.class);
    private static final String AUTO_SKILL = "AUTO";
    private static final Set<String> VALID_SKILLS = Set.of(
            AUTO_SKILL,
            "lab_report",
            "paper_summary",
            "course_qa_report"
    );

    private final AssignmentMapper assignmentMapper;
    private final MaterialMapper materialMapper;
    private final ReportMapper reportMapper;
    private final AgentTaskMapper taskMapper;
    private final AgentTaskLogMapper logMapper;
    private final FileStorageService fileStorageService;
    private final AgentWorkflowService agentWorkflowService;

    public AssignmentService(
            AssignmentMapper assignmentMapper,
            MaterialMapper materialMapper,
            ReportMapper reportMapper,
            AgentTaskMapper taskMapper,
            AgentTaskLogMapper logMapper,
            FileStorageService fileStorageService,
            AgentWorkflowService agentWorkflowService
    ) {
        this.assignmentMapper = assignmentMapper;
        this.materialMapper = materialMapper;
        this.reportMapper = reportMapper;
        this.taskMapper = taskMapper;
        this.logMapper = logMapper;
        this.fileStorageService = fileStorageService;
        this.agentWorkflowService = agentWorkflowService;
    }

    public Assignment create(AssignmentRequest request) {
        if (request.getTitle() == null || request.getTitle().isBlank()) {
            throw new IllegalArgumentException("Assignment title is required.");
        }
        Assignment assignment = new Assignment();
        assignment.setTitle(request.getTitle());
        assignment.setCourse(request.getCourse());
        assignment.setDescription(request.getDescription());
        assignment.setDueAt(request.getDueAt());
        assignment.setSkillId(normalizeSkillId(request.getSkillId()));
        assignment.setResolvedSkillId(null);
        assignment.setStatus("DRAFT");
        assignmentMapper.insert(assignment);
        log.info("assignment_created assignmentId={} skillId={}", assignment.getId(), assignment.getSkillId());
        return assignmentMapper.selectById(assignment.getId());
    }

    public Assignment update(Long id, AssignmentRequest request) {
        Assignment assignment = requireAssignment(id);
        if (request.getTitle() == null || request.getTitle().isBlank()) {
            throw new IllegalArgumentException("Assignment title is required.");
        }
        assignment.setTitle(request.getTitle());
        assignment.setCourse(request.getCourse());
        assignment.setDescription(request.getDescription());
        assignment.setDueAt(request.getDueAt());
        String nextSkillId = normalizeSkillId(request.getSkillId());
        if (!nextSkillId.equals(assignment.getSkillId())) {
            assignment.setResolvedSkillId(null);
        }
        assignment.setSkillId(nextSkillId);
        assignmentMapper.updateById(assignment);
        log.info("assignment_updated assignmentId={} skillId={}", id, assignment.getSkillId());
        return assignmentMapper.selectById(id);
    }

    public void deleteAssignment(Long id) {
        requireAssignment(id);
        materialsOf(id).forEach(material -> {
            fileStorageService.delete(material.getStoragePath());
            materialMapper.deleteById(material.getId());
        });
        List<AgentTask> tasks = taskMapper.selectList(
                Wrappers.<AgentTask>lambdaQuery().eq(AgentTask::getAssignmentId, id)
        );
        tasks.forEach(task -> logMapper.delete(
                Wrappers.<AgentTaskLog>lambdaQuery().eq(AgentTaskLog::getTaskId, task.getId())
        ));
        taskMapper.delete(Wrappers.<AgentTask>lambdaQuery().eq(AgentTask::getAssignmentId, id));
        reportMapper.delete(Wrappers.<Report>lambdaQuery().eq(Report::getAssignmentId, id));
        assignmentMapper.deleteById(id);
        agentWorkflowService.deleteAssignmentCollection(id);
        log.info("assignment_deleted assignmentId={}", id);
    }

    public List<Assignment> list(String keyword, String status, String sort) {
        LambdaQueryWrapper<Assignment> query = Wrappers.lambdaQuery();
        if (keyword != null && !keyword.isBlank()) {
            String like = keyword.trim();
            query.and(wrapper -> wrapper
                    .like(Assignment::getTitle, like)
                    .or()
                    .like(Assignment::getCourse, like)
                    .or()
                    .like(Assignment::getDescription, like)
            );
        }
        if (status != null && !status.isBlank() && !"ALL".equalsIgnoreCase(status)) {
            query.eq(Assignment::getStatus, status);
        }
        switch (sort == null ? "createdDesc" : sort) {
            case "createdAsc" -> query.orderByAsc(Assignment::getCreatedAt);
            case "dueAsc" -> query.orderByAsc(Assignment::getDueAt).orderByDesc(Assignment::getCreatedAt);
            case "dueDesc" -> query.orderByDesc(Assignment::getDueAt).orderByDesc(Assignment::getCreatedAt);
            default -> query.orderByDesc(Assignment::getCreatedAt);
        }
        return assignmentMapper.selectList(query);
    }

    public Assignment requireAssignment(Long id) {
        Assignment assignment = assignmentMapper.selectById(id);
        if (assignment == null) {
            throw new IllegalArgumentException("Assignment not found: " + id);
        }
        return assignment;
    }

    public Material uploadMaterial(Long assignmentId, MultipartFile file) {
        requireAssignment(assignmentId);
        FileStorageService.StoredFile stored = fileStorageService.store(assignmentId, file);

        Material material = new Material();
        material.setAssignmentId(assignmentId);
        material.setFilename(stored.filename());
        material.setContentType(stored.contentType());
        material.setSizeBytes(stored.sizeBytes());
        material.setStoragePath(stored.path());
        material.setIndexStatus("PENDING");
        material.setErrorMessage(null);
        materialMapper.insert(material);
        log.info(
                "material_uploaded assignmentId={} materialId={} filename={} sizeBytes={}",
                assignmentId,
                material.getId(),
                material.getFilename(),
                material.getSizeBytes()
        );

        Assignment assignment = requireAssignment(assignmentId);
        assignment.setStatus("READY");
        assignmentMapper.updateById(assignment);
        return materialMapper.selectById(material.getId());
    }

    public void deleteMaterial(Long materialId) {
        Material material = materialMapper.selectById(materialId);
        if (material == null) {
            throw new IllegalArgumentException("Material not found: " + materialId);
        }
        fileStorageService.delete(material.getStoragePath());
        materialMapper.deleteById(materialId);
        log.info("material_deleted assignmentId={} materialId={}", material.getAssignmentId(), materialId);
    }

    public Map<String, Object> detail(Long assignmentId) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("assignment", requireAssignment(assignmentId));
        body.put("materials", materialsOf(assignmentId));
        body.put("report", reportMapper.selectOne(
                Wrappers.<com.fzu.homework.domain.Report>lambdaQuery()
                        .eq(com.fzu.homework.domain.Report::getAssignmentId, assignmentId)
        ));
        return body;
    }

    public List<Material> materialsOf(Long assignmentId) {
        return materialMapper.selectList(
                Wrappers.<Material>lambdaQuery()
                        .eq(Material::getAssignmentId, assignmentId)
                        .orderByDesc(Material::getCreatedAt)
        );
    }

    public List<Material> allMaterials() {
        return materialMapper.selectList(
                Wrappers.<Material>lambdaQuery().orderByDesc(Material::getCreatedAt)
        );
    }

    public Map<String, Object> dashboardSummary() {
        long assignments = assignmentMapper.selectCount(null);
        long materials = materialMapper.selectCount(null);
        long reports = reportMapper.selectCount(null);
        long overdue = assignmentMapper.selectCount(
                Wrappers.<Assignment>lambdaQuery()
                        .lt(Assignment::getDueAt, LocalDateTime.now())
        );
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("assignments", assignments);
        body.put("materials", materials);
        body.put("reports", reports);
        body.put("overdue", overdue);
        return body;
    }

    public void markMaterials(Long assignmentId, String status, String errorMessage) {
        LambdaUpdateWrapper<Material> update = Wrappers.<Material>lambdaUpdate()
                .eq(Material::getAssignmentId, assignmentId)
                .set(Material::getIndexStatus, status)
                .set(Material::getErrorMessage, errorMessage);
        materialMapper.update(null, update);
    }

    public List<AgentTask> tasksOf(Long assignmentId) {
        requireAssignment(assignmentId);
        return taskMapper.selectList(
                Wrappers.<AgentTask>lambdaQuery()
                        .eq(AgentTask::getAssignmentId, assignmentId)
                        .orderByDesc(AgentTask::getCreatedAt)
        );
    }

    private String normalizeSkillId(String skillId) {
        String value = skillId == null || skillId.isBlank() ? AUTO_SKILL : skillId.trim();
        if (!VALID_SKILLS.contains(value)) {
            throw new IllegalArgumentException("Unsupported skillId: " + value);
        }
        return value;
    }
}
