# Eval Harness

This folder contains a lightweight evaluation harness for the homework agent.
It is designed to make RAG retrieval, skill routing, and report structure quality measurable instead of relying only on manual impressions.

## Input Format

Each line in the JSONL file is one evaluated case:

```json
{
  "id": "case-001",
  "expected_skill_id": "paper_summary",
  "resolved_skill_id": "paper_summary",
  "relevant_chunk_ids": ["paper-2", "paper-3"],
  "retrieved_chunk_ids": ["paper-2", "note-1", "paper-3"],
  "required_sections": ["研究背景", "核心问题", "方法概述"],
  "markdown": "## 研究背景\n...\n## 核心问题\n...\n## 方法概述\n...",
  "grounding_claims": [
    {
      "claim": "The paper uses federated learning.",
      "supported": true
    }
  ]
}
```

## Metrics

- `recall_at_k`: whether any relevant chunk appears in the top-k retrieved chunks.
- `mrr`: reciprocal rank of the first relevant chunk.
- `skill_routing_accuracy`: whether the resolved skill matches the expected skill.
- `section_completeness`: whether required Markdown sections appear in the generated report.
- `groundedness`: ratio of supported grounding claims.
- `citation_coverage`: precomputed evidence coverage from real AgentTask quality metrics.
- `rewrite_trigger_rate`: share of tasks that needed automatic rewrite.

## Run

From `agent-python`:

```bash
python evals/eval_harness.py evals/sample_results.jsonl --k 5
```

## Export Real Task Data

After the Java backend has generated reports, you can export task JSON from the API
or database and convert it into JSONL:

```bash
python evals/export_task_results.py tasks.json evals/task_results.jsonl
python evals/eval_harness.py evals/task_results.jsonl --k 5
```

The exporter reads persisted fields such as `retrievedEvidenceJson`,
`qualityMetricsJson`, `resolvedSkillId`, and optional human labels like
`expectedSkillId` / `relevantChunkIds`.
