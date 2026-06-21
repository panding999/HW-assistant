# Private RAG Eval Dataset

This directory is reserved for local offline RAG evaluation data.

The real hard eval cases and source materials are intentionally not committed to the public repository. Keep them local when running:

```text
agent-python/tests/fixtures/rag_eval/cases.json
agent-python/tests/fixtures/rag_eval/materials/
```

The evaluation scripts still support this path by default, but the dataset should be maintained privately. Commit only the harness, metric definitions, and aggregate interview-safe numbers.

Recommended local layout:

```text
rag_eval/
  cases.json
  materials/
    case_001/
      material.md
```

`cases.json` should contain assignment metadata, material references, and manually labeled gold evidence for metrics such as `Hit Rate@5`.
