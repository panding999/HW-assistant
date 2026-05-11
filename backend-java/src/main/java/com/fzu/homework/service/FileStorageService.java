package com.fzu.homework.service;

import org.springframework.beans.factory.annotation.Value;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.UUID;

@Service
public class FileStorageService {
    private static final Logger log = LoggerFactory.getLogger(FileStorageService.class);
    private final Path uploadDir;

    public FileStorageService(@Value("${storage.upload-dir}") String uploadDir) {
        this.uploadDir = Path.of(uploadDir).toAbsolutePath().normalize();
    }

    public StoredFile store(Long assignmentId, MultipartFile file) {
        String original = file.getOriginalFilename() == null ? "material" : file.getOriginalFilename();
        String normalized = original.replace('\\', '/');
        String filename = normalized.substring(normalized.lastIndexOf('/') + 1);
        String lower = filename.toLowerCase(Locale.ROOT);
        if (!(lower.endsWith(".pdf") || lower.endsWith(".md") || lower.endsWith(".markdown") || lower.endsWith(".txt"))) {
            throw new IllegalArgumentException("Only PDF, Markdown, and TXT files are supported.");
        }

        try {
            Path assignmentDir = uploadDir.resolve(String.valueOf(assignmentId));
            Files.createDirectories(assignmentDir);
            Path target = assignmentDir.resolve(UUID.randomUUID() + "-" + filename).normalize();
            file.transferTo(target);
            log.info("file_stored assignmentId={} filename={} sizeBytes={} path={}", assignmentId, filename, file.getSize(), target);
            return new StoredFile(filename, target.toAbsolutePath().toString(), file.getContentType(), file.getSize());
        } catch (IOException ex) {
            throw new IllegalStateException("Failed to store uploaded file.", ex);
        }
    }

    public void delete(String storagePath) {
        if (storagePath == null || storagePath.isBlank()) {
            return;
        }
        try {
            Path target = Path.of(storagePath).toAbsolutePath().normalize();
            if (target.startsWith(uploadDir)) {
                Files.deleteIfExists(target);
                log.info("file_deleted path={}", target);
            }
        } catch (IOException ignored) {
            // File cleanup should not block metadata deletion.
        }
    }

    public record StoredFile(String filename, String path, String contentType, long sizeBytes) {
    }
}
