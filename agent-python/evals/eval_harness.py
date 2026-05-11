from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from statistics import mean
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def recall_at_k(case: dict[str, Any], k: int) -> float:
    relevant = set(case.get("relevant_chunk_ids") or [])
    retrieved = case.get("retrieved_chunk_ids") or []
    if "recall_at_k" in case:
        return float(case["recall_at_k"])
    if not relevant:
        return 0.0
    return 1.0 if relevant.intersection(retrieved[:k]) else 0.0


def reciprocal_rank(case: dict[str, Any]) -> float:
    relevant = set(case.get("relevant_chunk_ids") or [])
    if not relevant:
        return 0.0
    for index, chunk_id in enumerate(case.get("retrieved_chunk_ids") or [], start=1):
        if chunk_id in relevant:
            return 1.0 / index
    return 0.0


def routing_accuracy(case: dict[str, Any]) -> float:
    expected = case.get("expected_skill_id")
    resolved = case.get("resolved_skill_id")
    if not expected:
        return 0.0
    return 1.0 if expected == resolved else 0.0


def markdown_headings(markdown: str) -> set[str]:
    headings = set()
    for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", markdown or "", re.MULTILINE):
        headings.add(match.group(1).strip())
    return headings


def section_completeness(case: dict[str, Any]) -> float:
    if "section_completeness" in case:
        return float(case["section_completeness"])
    required = case.get("required_sections") or []
    if not required:
        return 0.0
    headings = markdown_headings(case.get("markdown") or "")
    hits = sum(1 for section in required if section in headings)
    return hits / len(required)


def groundedness(case: dict[str, Any]) -> float:
    if "citation_coverage" in case:
        return float(case["citation_coverage"])
    claims = case.get("grounding_claims") or []
    if not claims:
        return 0.0
    supported = sum(1 for claim in claims if claim.get("supported") is True)
    return supported / len(claims)


def evaluate(cases: list[dict[str, Any]], k: int) -> dict[str, float]:
    if not cases:
        return {}
    return {
        f"recall_at_{k}": mean(recall_at_k(case, k) for case in cases),
        "mrr": mean(reciprocal_rank(case) for case in cases),
        "skill_routing_accuracy": mean(routing_accuracy(case) for case in cases),
        "section_completeness": mean(section_completeness(case) for case in cases),
        "groundedness": mean(groundedness(case) for case in cases),
        "citation_coverage": mean(float(case.get("citation_coverage", groundedness(case))) for case in cases),
        "rewrite_trigger_rate": mean(1.0 if case.get("rewrite_triggered") else 0.0 for case in cases),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate homework agent JSONL results.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    metrics = evaluate(load_jsonl(args.input), args.k)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
