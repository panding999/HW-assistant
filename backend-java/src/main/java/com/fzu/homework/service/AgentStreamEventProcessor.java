package com.fzu.homework.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.function.Consumer;

@Component
public class AgentStreamEventProcessor {
    private final ObjectMapper objectMapper;

    public AgentStreamEventProcessor(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public Map<?, ?> readFinalResponse(InputStream body, Consumer<StageEvent> stageConsumer) {
        Map<?, ?> finalPayload = null;
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(body, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }
                Map<String, Object> event = objectMapper.readValue(line, new TypeReference<>() {});
                String type = stringValue(event.get("type"));
                if ("stage".equals(type)) {
                    stageConsumer.accept(new StageEvent(
                            stringValue(event.get("stage")),
                            stringValueOrDefault(event.get("status"), "SUCCEEDED"),
                            stringValueOrDefault(event.get("message"), "Agent stage completed.")
                    ));
                } else if ("final".equals(type)) {
                    Object data = event.get("data");
                    if (data instanceof Map<?, ?> map) {
                        finalPayload = map;
                    }
                } else if ("error".equals(type)) {
                    throw new IllegalStateException(stringValueOrDefault(event.get("message"), "Agent stream failed."));
                }
            }
        } catch (IOException ex) {
            throw new IllegalStateException("Failed to read Agent stream.", ex);
        }
        if (finalPayload == null) {
            throw new IllegalStateException("Agent stream ended without final response.");
        }
        return finalPayload;
    }

    private String stringValue(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private String stringValueOrDefault(Object value, String fallback) {
        String text = stringValue(value);
        return text.isBlank() ? fallback : text;
    }

    public record StageEvent(String stage, String status, String message) {
    }
}
