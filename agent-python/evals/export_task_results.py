from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_json_field(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return fallback


def iter_tasks(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("tasks"), list):
            return [item for item in payload["tasks"] if isinstance(item, dict)]
        if isinstance(payload.get("task"), dict):
            return [payload["task"]]
    return []


def convert_task(task: dict[str, Any]) -> dict[str, Any]:
    evidence = parse_json_field(task.get("retrievedEvidenceJson") or task.get("retrieved_evidence_json"), [])
    quality = parse_json_field(task.get("qualityMetricsJson") or task.get("quality_metrics_json"), {})
    retrieved_chunk_ids = [
        str(item.get("chunk_id") or item.get("chunkId"))
        for item in evidence
        if isinstance(item, dict) and (item.get("chunk_id") or item.get("chunkId"))
    ]
    resolved_skill = task.get("resolvedSkillId") or task.get("resolved_skill_id")
    expected_skill = task.get("expectedSkillId") or task.get("expected_skill_id") or resolved_skill
    return {
        "task_id": task.get("id"),
        "assignment_id": task.get("assignmentId") or task.get("assignment_id"),
        "expected_skill_id": expected_skill,
        "resolved_skill_id": resolved_skill,
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "relevant_chunk_ids": task.get("relevantChunkIds") or task.get("relevant_chunk_ids") or [],
        "section_completeness": float(quality.get("section_completeness", 0.0)) if isinstance(quality, dict) else 0.0,
        "citation_coverage": float(quality.get("citation_coverage", 0.0)) if isinstance(quality, dict) else 0.0,
        "rewrite_triggered": bool(quality.get("rewrite_triggered", False)) if isinstance(quality, dict) else False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export persisted AgentTask JSON into eval JSONL.")
    parser.add_argument("input", type=Path, help="JSON exported from backend task APIs.")
    parser.add_argument("output", type=Path, help="Output JSONL path.")
    args = parser.parse_args()

    cases = [convert_task(task) for task in iter_tasks(load_json(args.input))]
    args.output.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + ("\n" if cases else ""),
        encoding="utf-8",
    )
    print(json.dumps({"cases": len(cases), "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
