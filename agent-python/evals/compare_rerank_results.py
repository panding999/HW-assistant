from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def by_case(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["case_id"]): item for item in result.get("per_case", [])}


def hit_value(item: dict[str, Any] | None) -> bool:
    return bool(item and item.get("hit_at_5") is True)


def ucr_value(item: dict[str, Any] | None) -> float | None:
    if not item:
        return None
    value = item.get("unsupported_claim_rate")
    return float(value) if value is not None else None


def compare_cases(
    baseline_hit: dict[str, Any],
    rerank_hit: dict[str, Any],
    baseline_ucr: dict[str, Any],
    rerank_ucr: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_hit_cases = by_case(baseline_hit)
    rerank_hit_cases = by_case(rerank_hit)
    baseline_ucr_cases = by_case(baseline_ucr)
    rerank_ucr_cases = by_case(rerank_ucr)
    case_ids = sorted(set(baseline_hit_cases) | set(rerank_hit_cases) | set(baseline_ucr_cases) | set(rerank_ucr_cases))
    rows = []
    for case_id in case_ids:
        b_hit = hit_value(baseline_hit_cases.get(case_id))
        r_hit = hit_value(rerank_hit_cases.get(case_id))
        b_ucr = ucr_value(baseline_ucr_cases.get(case_id))
        r_ucr = ucr_value(rerank_ucr_cases.get(case_id))
        rows.append(
            {
                "case_id": case_id,
                "baseline_hit_at_5": b_hit,
                "rerank_hit_at_5": r_hit,
                "hit_changed": b_hit != r_hit,
                "miss_to_hit": (not b_hit) and r_hit,
                "hit_to_miss": b_hit and (not r_hit),
                "baseline_unsupported_claim_rate": b_ucr,
                "rerank_unsupported_claim_rate": r_ucr,
                "unsupported_claim_rate_delta": None if b_ucr is None or r_ucr is None else r_ucr - b_ucr,
                "baseline_resolved_skill_id": (baseline_hit_cases.get(case_id) or {}).get("resolved_skill_id"),
                "rerank_resolved_skill_id": (rerank_hit_cases.get(case_id) or {}).get("resolved_skill_id"),
            }
        )
    return rows


def write_results(results: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stamped = out_dir / f"rerank_comparison_{timestamp}.json"
    latest = out_dir / "rerank_comparison_latest.json"
    text = json.dumps(results, ensure_ascii=False, indent=2)
    stamped.write_text(text + "\n", encoding="utf-8")
    latest.write_text(text + "\n", encoding="utf-8")
    return stamped, latest


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare baseline and rerank evaluation results.")
    parser.add_argument("--out", type=Path, default=ROOT / "eval-results")
    parser.add_argument(
        "--baseline-hit",
        type=Path,
        default=first_existing(
            ROOT / "eval-results" / "rag_hit_rate_baseline_latest.json",
            ROOT / "eval-results" / "rag_hit_rate_latest.json",
        ),
    )
    parser.add_argument("--rerank-hit", type=Path, default=ROOT / "eval-results" / "rag_hit_rate_qwen3_rerank_latest.json")
    parser.add_argument(
        "--baseline-ucr",
        type=Path,
        default=first_existing(
            ROOT / "eval-results" / "unsupported_claim_rate_baseline_latest.json",
            ROOT / "eval-results" / "unsupported_claim_rate_latest.json",
        ),
    )
    parser.add_argument(
        "--rerank-ucr",
        type=Path,
        default=ROOT / "eval-results" / "unsupported_claim_rate_qwen3_rerank_latest.json",
    )
    args = parser.parse_args()

    baseline_hit = load_json(args.baseline_hit)
    rerank_hit = load_json(args.rerank_hit)
    baseline_ucr = load_json(args.baseline_ucr)
    rerank_ucr = load_json(args.rerank_ucr)
    per_case = compare_cases(baseline_hit, rerank_hit, baseline_ucr, rerank_ucr)

    results = {
        "metric": "Rerank Comparison",
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline": {
            "hit_rate_at_5": baseline_hit.get("hit_rate_at_5"),
            "unsupported_claim_rate": baseline_ucr.get("unsupported_claim_rate"),
            "hit_count": baseline_hit.get("hit_count"),
            "unsupported_claims": baseline_ucr.get("unsupported_claims"),
            "total_claims": baseline_ucr.get("total_claims"),
        },
        "rerank": {
            "hit_rate_at_5": rerank_hit.get("hit_rate_at_5"),
            "unsupported_claim_rate": rerank_ucr.get("unsupported_claim_rate"),
            "hit_count": rerank_hit.get("hit_count"),
            "unsupported_claims": rerank_ucr.get("unsupported_claims"),
            "total_claims": rerank_ucr.get("total_claims"),
        },
        "deltas": {
            "hit_rate_at_5": (rerank_hit.get("hit_rate_at_5") or 0) - (baseline_hit.get("hit_rate_at_5") or 0),
            "unsupported_claim_rate": (rerank_ucr.get("unsupported_claim_rate") or 0)
            - (baseline_ucr.get("unsupported_claim_rate") or 0),
            "miss_to_hit_cases": sum(1 for item in per_case if item["miss_to_hit"]),
            "hit_to_miss_cases": sum(1 for item in per_case if item["hit_to_miss"]),
        },
        "per_case": per_case,
    }
    stamped, latest = write_results(results, args.out)
    print(json.dumps(results["deltas"], ensure_ascii=False, indent=2))
    print(f"wrote: {stamped}")
    print(f"latest: {latest}")


if __name__ == "__main__":
    main()
