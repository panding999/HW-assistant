package com.fzu.homework;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@EnableAsync
@MapperScan("com.fzu.homework.mapper")
@SpringBootApplication
public class HomeworkAssistantApplication {
    public static void main(String[] args) {
        SpringApplication.run(HomeworkAssistantApplication.class, args);
    }
}
