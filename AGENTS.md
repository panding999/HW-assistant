# AGENTS.md

This file is for coding agents and contributors working on this repository. It is not part of the runtime Agent product.

## Project Shape

FZU Homework Assistant is a multi-module project:

- `frontend/`: Next.js 14 workspace UI, report editor, task trace display, monitoring dashboard.
- `backend-java/`: Spring Boot orchestration, MySQL persistence, file upload, SSE task logs.
- `agent-python/`: FastAPI Agent runtime, assignment-scoped RAG, skill routing, quality gate, repair retrieval, rewrite.
- `docs/`: project notes and GitHub assets.

Runtime data flow:

```text
Next.js -> Spring Boot -> FastAPI Agent -> ChromaDB / LLM / Embedding
```

## Important Invariants

- Do not mix uploaded materials across assignments. RAG must stay assignment-scoped.
- ChromaDB collections are named `assignment_{assignment_id}`.
- When rebuilding an assignment index, use cosine space: `metadata={"hnsw:space": "cosine"}`.
- Do not introduce MySQL schema changes unless explicitly requested.
- Keep Agent trace, retrieved evidence, and quality metrics backward compatible because they are stored as JSON text.
- Do not log API keys, full prompts, or full uploaded document bodies.

## Prompt And Skill Locations

Business skills live under:

```text
agent-python/app/skills/{skill_id}/
  skill.json
  SKILL.md
```

These are project-specific business skills, not Codex or Claude tool skills.

- `skill.json`: machine-readable metadata, including `system_prompt`, `query_hint`, and `required_sections`.
- `SKILL.md`: detailed generation instructions loaded into `skill.instructions`.

Prompt construction lives mainly in:

- `agent-python/app/main.py`
  - `route_skill_with_llm`
  - `build_search_queries`
  - `build_prompt`
- `agent-python/app/agent_runtime.py`
  - `plan_report_outline`
  - `build_report_draft`
  - `review_quality_with_llm`
  - `rewrite_report`

## RAG Design

The project uses assignment-scoped RAG:

```text
assignment_1 -> Chroma collection assignment_1
assignment_2 -> Chroma collection assignment_2
```

Generation for one assignment should only search that assignment's collection.

Current retrieval stack:

- structured chunking for Markdown headings, PDF pages, and paragraph blocks
- document summary, section summary, key terms metadata
- cosine vector search in ChromaDB
- multi-query retrieval: assignment, skill, section, plan, keyword
- parent-child context merge
- lightweight hybrid score using vector and keyword/section/file signals
- quality-feedback repair retrieval: at most one supplemental retrieval round when grounding is low, required sections are missing, or quality issues point to insufficient evidence

## Agent Loop

Normal fixed skills:

```text
search_materials -> build_report_draft -> check_report_quality
-> retrieve_repair/regenerate(optional) -> rewrite_report(optional)
```

Dynamic planner:

```text
plan_report_outline -> search_materials -> build_report_draft -> check_report_quality
-> retrieve_repair/regenerate(optional) -> rewrite_report(optional)
```

Streaming endpoints:

- Prefer `/agent/generate-report-stream` and `/agent/improve-report-stream` from Java when available.
- Stream format is NDJSON with `stage`, `final`, and `error` events.
- Non-streaming endpoints remain required as fallback.

Improve/version protection:

- When improving an existing draft, use the previously saved quality score as the baseline if available.
- Do not re-score the current draft just to establish the baseline, because evaluator scores can fluctuate across runs.

Keep loop bounds explicit. Do not add open-ended autonomous loops.

## Verification

Use these commands before claiming a change is done:

```powershell
python -m unittest discover agent-python\tests
cd frontend
npm.cmd run typecheck
cd ..\backend-java
mvn -q -DskipTests package
```

For Docker smoke test:

```powershell
$env:DOCKER_CONFIG=(Resolve-Path .docker-config).Path
docker compose up --build -d
docker compose ps
```

Expected local endpoints:

- Frontend: http://localhost:3000
- Backend: http://localhost:8080
- Agent docs: http://localhost:8000/docs
- ChromaDB: http://localhost:8001
