package com.fzu.homework.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AgentStreamEventProcessorTest {

    private final AgentStreamEventProcessor processor = new AgentStreamEventProcessor(new ObjectMapper());

    @Test
    void readsStageEventsAndReturnsFinalPayload() {
        String ndjson = """
                {"type":"stage","stage":"retrieve","status":"SUCCEEDED","message":"retrieved=3"}
                {"type":"stage","stage":"quality","status":"SUCCEEDED","message":"score=90%"}
                {"type":"final","data":{"markdown":"# Report","retrieved_chunks":3}}
                """;
        List<AgentStreamEventProcessor.StageEvent> stages = new ArrayList<>();

        Map<?, ?> finalPayload = processor.readFinalResponse(
                new ByteArrayInputStream(ndjson.getBytes(StandardCharsets.UTF_8)),
                stages::add
        );

        assertThat(stages).extracting(AgentStreamEventProcessor.StageEvent::stage)
                .containsExactly("retrieve", "quality");
        assertThat(stages).extracting(AgentStreamEventProcessor.StageEvent::message)
                .containsExactly("retrieved=3", "score=90%");
        assertThat(finalPayload.get("markdown")).isEqualTo("# Report");
        assertThat(finalPayload.get("retrieved_chunks")).isEqualTo(3);
    }

    @Test
    void raisesAgentErrorAndDoesNotReturnFinalPayload() {
        String ndjson = """
                {"type":"stage","stage":"generate","status":"SUCCEEDED","message":"started"}
                {"type":"error","message":"boom","error_type":"RuntimeError"}
                """;
        List<AgentStreamEventProcessor.StageEvent> stages = new ArrayList<>();

        assertThatThrownBy(() -> processor.readFinalResponse(
                new ByteArrayInputStream(ndjson.getBytes(StandardCharsets.UTF_8)),
                stages::add
        )).isInstanceOf(IllegalStateException.class).hasMessageContaining("boom");

        assertThat(stages).hasSize(1);
        assertThat(stages.getFirst().stage()).isEqualTo("generate");
    }
}
