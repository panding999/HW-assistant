package com.fzu.homework.controller;

import com.fzu.homework.dto.ParentChunkLookupRequest;
import com.fzu.homework.service.ParentChunkService;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/internal")
public class InternalParentChunkController {
    private final ParentChunkService parentChunkService;

    public InternalParentChunkController(ParentChunkService parentChunkService) {
        this.parentChunkService = parentChunkService;
    }

    @PostMapping("/assignments/{assignmentId}/parent-chunks/lookup")
    public Map<String, Map<String, String>> lookup(
            @PathVariable Long assignmentId,
            @RequestBody ParentChunkLookupRequest request
    ) {
        return Map.of("chunks", parentChunkService.lookup(assignmentId, request.parentIds()));
    }
}
