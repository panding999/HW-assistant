package com.fzu.homework.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record ParentChunkRecord(
        String id,
        @JsonProperty("assignment_id") Long assignmentId,
        @JsonProperty("material_id") Long materialId,
        String filename,
        @JsonProperty("parent_index") Integer parentIndex,
        @JsonProperty("section_title") String sectionTitle,
        String content
) {
}
