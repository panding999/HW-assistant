package com.fzu.homework.service;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.fzu.homework.domain.AgentParentChunk;
import com.fzu.homework.dto.ParentChunkRecord;
import com.fzu.homework.mapper.AgentParentChunkMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class ParentChunkService {
    private final AgentParentChunkMapper parentChunkMapper;

    public ParentChunkService(AgentParentChunkMapper parentChunkMapper) {
        this.parentChunkMapper = parentChunkMapper;
    }

    @Transactional
    public void replaceAssignmentParentChunks(Long assignmentId, List<ParentChunkRecord> records) {
        parentChunkMapper.delete(Wrappers.<AgentParentChunk>lambdaQuery()
                .eq(AgentParentChunk::getAssignmentId, assignmentId));
        for (ParentChunkRecord record : records) {
            if (record == null || record.id() == null || record.content() == null || record.content().isBlank()) {
                continue;
            }
            AgentParentChunk chunk = new AgentParentChunk();
            chunk.setAssignmentId(assignmentId);
            chunk.setMaterialId(record.materialId());
            chunk.setParentId(record.id());
            chunk.setFilename(record.filename());
            chunk.setParentIndex(record.parentIndex());
            chunk.setSectionTitle(record.sectionTitle());
            chunk.setContent(record.content());
            parentChunkMapper.insert(chunk);
        }
    }

    public Map<String, String> lookup(Long assignmentId, List<String> parentIds) {
        if (parentIds == null || parentIds.isEmpty()) {
            return Map.of();
        }
        List<AgentParentChunk> chunks = parentChunkMapper.selectList(
                Wrappers.<AgentParentChunk>lambdaQuery()
                        .eq(AgentParentChunk::getAssignmentId, assignmentId)
                        .in(AgentParentChunk::getParentId, parentIds)
        );
        Map<String, String> result = new LinkedHashMap<>();
        for (AgentParentChunk chunk : chunks) {
            result.put(chunk.getParentId(), chunk.getContent());
        }
        return result;
    }
}
