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

## Run Fixture RAG Hit Rate@5

From the repository root, start ChromaDB with Docker Compose and run the fixture evaluation:

```powershell
cd "D:\HW Assistant"
$env:DOCKER_CONFIG=(Resolve-Path .docker-config).Path
docker compose up -d chromadb

python -m venv agent-python\.venv
agent-python\.venv\Scripts\python.exe -m pip install -r agent-python\requirements.txt
agent-python\.venv\Scripts\python.exe agent-python\evals\eval_rag_hit_rate.py
```

The script reads:

```text
agent-python/tests/fixtures/rag_eval/cases.json
```

The fixture dataset is intentionally private and is not committed to the public repository. Keep `cases.json` and `materials/` locally when reproducing the hard eval numbers.

It writes:

```text
agent-python/eval-results/rag_hit_rate_latest.json
agent-python/eval-results/rag_hit_rate_YYYYMMDD_HHMMSS.json
```

## Run Fixture Unsupported Claim Rate

This evaluation generates reports first, then uses the configured evaluator model to extract concrete claims and judge whether each claim is supported by retrieved evidence.

From the repository root:

```powershell
cd "D:\HW Assistant"

agent-python\.venv\Scripts\python.exe agent-python\evals\eval_unsupported_claim_rate.py
```

To test one case first:

```powershell
agent-python\.venv\Scripts\python.exe agent-python\evals\eval_unsupported_claim_rate.py --limit 1
```

The script writes:

```text
agent-python/eval-results/unsupported_claim_rate_latest.json
agent-python/eval-results/unsupported_claim_rate_YYYYMMDD_HHMMSS.json
```

## Run Baseline vs Qwen3-Rerank Comparison

From the repository root:

```powershell
cd "D:\HW Assistant"

$env:RERANK_ENABLED="false"
agent-python\.venv\Scripts\python.exe agent-python\evals\eval_rag_hit_rate.py --label baseline
agent-python\.venv\Scripts\python.exe agent-python\evals\eval_unsupported_claim_rate.py --label baseline

$env:RERANK_ENABLED="true"
$env:RERANK_MODEL="qwen3-rerank"
agent-python\.venv\Scripts\python.exe agent-python\evals\eval_rag_hit_rate.py --label qwen3_rerank
agent-python\.venv\Scripts\python.exe agent-python\evals\eval_unsupported_claim_rate.py --label qwen3_rerank

agent-python\.venv\Scripts\python.exe agent-python\evals\compare_rerank_results.py
```

The comparison script writes:

```text
agent-python/eval-results/rerank_comparison_latest.json
agent-python/eval-results/rerank_comparison_YYYYMMDD_HHMMSS.json
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

Retrieval metrics such as `Hit Rate@5` require human-labeled gold data. For this project, a small set is enough for resume demonstration:

- Start with 20-50 real assignment queries.
- Label `expectedSkillId`, `relevantChunkIds`, `expectedSections`, and optionally `goldMaterialIds`.
- Use current top-10/top-20 retrieval results to speed up labeling, but allow manual additions when the right chunk was not retrieved.
- Compare vector-only retrieval with hybrid retrieval to show whether Multi-Query, Parent-Child context, and keyword signals improve recall.

The online quality gate is not a fully objective benchmark because the evaluator still uses an LLM. Treat it as runtime quality control, and use the manual gold set for more defensible offline evaluation.
