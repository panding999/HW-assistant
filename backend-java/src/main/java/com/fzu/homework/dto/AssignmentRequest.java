package com.fzu.homework.dto;

import java.time.LocalDateTime;

public class AssignmentRequest {
    private String title;
    private String course;
    private String description;
    private LocalDateTime dueAt;

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getCourse() { return course; }
    public void setCourse(String course) { this.course = course; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }
    public LocalDateTime getDueAt() { return dueAt; }
    public void setDueAt(LocalDateTime dueAt) { this.dueAt = dueAt; }
}
