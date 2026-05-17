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

## Manual Gold Set Guidance

Retrieval metrics such as `Hit Rate@5` and `Recall@5` require human-labeled gold data. For this project, a small set is enough for resume demonstration:

- Start with 20-50 real assignment queries.
- Label `expectedSkillId`, `relevantChunkIds`, `expectedSections`, and optionally `goldMaterialIds`.
- Use current top-10/top-20 retrieval results to speed up labeling, but allow manual additions when the right chunk was not retrieved.
- Compare vector-only retrieval with hybrid retrieval to show whether Multi-Query, Parent-Child context, and keyword signals improve recall.

The online quality gate is not a fully objective benchmark because the evaluator still uses an LLM. Treat it as runtime quality control, and use the manual gold set for more defensible offline evaluation.
