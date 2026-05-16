# Agent Skills

This directory contains **project-specific business skills** for the Python Agent runtime.

They are not Codex/Claude tool skills. A Codex/Claude-style skill may include folders such as `references/`, `scripts/`, or `assets/`; this project does not need that format for runtime report generation.

Each subdirectory is one lightweight business skill package:

```text
skills/
  course_qa_report/
    skill.json
    SKILL.md
```

`skill.json` is machine-readable metadata used by the registry and router:

- `id`: stable skill id used by API requests.
- `label`: human-readable name.
- `description`: short routing and UI description.
- `entry`: markdown instruction file, usually `SKILL.md`.
- `system_prompt`: model role for this skill.
- `query_hint`: retrieval query expansion hint.
- `required_sections`: expected Markdown sections.

`SKILL.md` is the human-readable skill instruction. It should describe:

- skill name
- applicable scenarios
- role setting
- core requirements
- output format

This structure supports progressive disclosure inside this project:

1. The registry reads lightweight metadata from `skill.json`.
2. The agent loads the full `SKILL.md` only for the selected skill.
3. The selected skill's `system_prompt`, `query_hint`, `required_sections`, and `SKILL.md` instructions are used to construct RAG queries and report-generation prompts.

Current built-in skills:

- `lab_report`: lab reports, programming practice, experiment analysis.
- `paper_summary`: paper reading, literature summary, classroom presentation.
- `course_qa_report`: course-material QA and presentation reports.
- `dynamic_planner`: open-ended assignments that need a report outline before writing.
