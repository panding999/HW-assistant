package com.fzu.homework.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

public record ParentChunkLookupRequest(
        @JsonProperty("parent_ids") List<String> parentIds
) {
}
