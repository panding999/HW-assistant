# Agent Skills

Each subdirectory is one portable skill package:

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

This structure supports progressive disclosure:

1. The registry reads lightweight metadata from `skill.json`.
2. The agent loads the full `SKILL.md` only for the selected skill.
3. A skill from another repository can be installed by copying its folder here.
