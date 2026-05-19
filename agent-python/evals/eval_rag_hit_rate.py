from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from app.agent_runtime import RetrievedEvidence, search_materials  # noqa: E402
from app.main import (  # noqa: E402
    AUTO_SKILL,
    IndexRequest,
    MaterialRef,
    ReportRequest,
    build_search_queries,
    chroma_client,
    collection_metadata,
    collection_name,
    embed_texts,
    index_materials,
    resolve_skill,
)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_cases(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def material_ref(item: dict[str, Any]) -> MaterialRef:
    raw_path = Path(item["path"])
    path = raw_path if raw_path.is_absolute() else REPO_ROOT / raw_path
    return MaterialRef(
        id=int(item["id"]),
        filename=str(item["filename"]),
        path=str(path),
        content_type=item.get("content_type"),
    )


def delete_collection(assignment_id: int) -> None:
    client = chroma_client()
    try:
        client.delete_collection(name=collection_name(assignment_id))
    except Exception as exc:
        text = str(exc).lower()
        if "does not exist" not in text and "not found" not in text:
            raise


def index_case(case: dict[str, Any]) -> int:
    payload = IndexRequest(
        assignment_id=int(case["assignment_id"]),
        title=str(case["title"]),
        description=case.get("description"),
        materials=[material_ref(item) for item in case.get("materials", [])],
    )
    return index_materials(payload).chunks_indexed


def retrieve_case(case: dict[str, Any]) -> tuple[str, str, list[RetrievedEvidence]]:
    payload = ReportRequest(
        assignment_id=int(case["assignment_id"]),
        title=str(case["title"]),
        course=case.get("course"),
        description=case.get("description"),
        skill_id=case.get("skill_id") or AUTO_SKILL,
        top_k=int(case.get("top_k") or 5),
    )
    skill, routing = resolve_skill(payload)
    collection = chroma_client().get_or_create_collection(
        name=collection_name(payload.assignment_id),
        metadata=collection_metadata(),
    )
    queries = build_search_queries(payload, skill)
    result = search_materials(collection, queries, payload.top_k, embed_texts)
    return skill.id, routing.mode, result.evidence


def evidence_haystack(item: RetrievedEvidence) -> str:
    return "\n".join(
        [
            item.filename or "",
            item.section_title or "",
            item.section_summary or "",
            item.excerpt or "",
            item.document_summary or "",
            item.key_terms or "",
        ]
    )


def gold_matches(item: RetrievedEvidence, gold: dict[str, Any]) -> bool:
    if gold.get("filename") and item.filename != gold["filename"]:
        return False
    if gold.get("section_title") and item.section_title != gold["section_title"]:
        return False
    haystack = evidence_haystack(item)
    return all(str(term) in haystack for term in gold.get("must_contain") or [])


def first_match(evidence: list[RetrievedEvidence], gold_items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for rank, item in enumerate(evidence, start=1):
        for gold in gold_items:
            if gold_matches(item, gold):
                return {
                    "rank": rank,
                    "chunk_id": item.chunk_id,
                    "filename": item.filename,
                    "section_title": item.section_title,
                    "matched_gold": gold,
                }
    return None


def compact_evidence(item: RetrievedEvidence, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "chunk_id": item.chunk_id,
        "filename": item.filename,
        "section_title": item.section_title,
        "parent_id": item.parent_id,
        "score": item.score,
        "vector_score": item.vector_score,
        "keyword_score": item.keyword_score,
        "hybrid_score": item.hybrid_score,
        "rerank_score": item.rerank_score,
        "rerank_model": item.rerank_model,
        "excerpt_preview": (item.excerpt or "")[:280],
    }


def evaluate_case(case: dict[str, Any], *, keep_collections: bool) -> dict[str, Any]:
    assignment_id = int(case["assignment_id"])
    if not keep_collections:
        delete_collection(assignment_id)
    chunks_indexed = index_case(case)
    resolved_skill_id, routing_mode, evidence = retrieve_case(case)
    top_k = int(case.get("top_k") or 5)
    top_evidence = evidence[:top_k]
    match = first_match(top_evidence, case.get("gold_evidence") or [])
    return {
        "case_id": case["case_id"],
        "assignment_id": assignment_id,
        "requested_skill_id": case.get("skill_id"),
        "resolved_skill_id": resolved_skill_id,
        "routing_mode": routing_mode,
        "chunks_indexed": chunks_indexed,
        f"hit_at_{top_k}": match is not None,
        "first_match": match,
        "gold_evidence": case.get("gold_evidence") or [],
        "top_evidence": [compact_evidence(item, rank) for rank, item in enumerate(top_evidence, start=1)],
    }


def write_results(results: dict[str, Any], out_dir: Path, label: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    stamped = out_dir / f"rag_hit_rate{suffix}_{timestamp}.json"
    latest = out_dir / f"rag_hit_rate{suffix}_latest.json"
    text = json.dumps(results, ensure_ascii=False, indent=2)
    stamped.write_text(text + "\n", encoding="utf-8")
    latest.write_text(text + "\n", encoding="utf-8")
    return stamped, latest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fixture-based RAG Hit Rate@K evaluation.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "rag_eval" / "cases.json",
        help="Path to rag_eval cases.json.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "eval-results",
        help="Directory for JSON evaluation results.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional number of cases to run.")
    parser.add_argument("--label", default="", help="Optional experiment label, for example baseline or qwen3_rerank.")
    parser.add_argument(
        "--keep-collections",
        action="store_true",
        help="Do not delete assignment collections before indexing.",
    )
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    cases = load_cases(args.cases)
    if args.limit > 0:
        cases = cases[: args.limit]

    per_case = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['case_id']} assignment_{case['assignment_id']}")
        per_case.append(evaluate_case(case, keep_collections=args.keep_collections))

    total = len(per_case)
    hit_count = sum(1 for item in per_case if item.get("hit_at_5") is True)
    results = {
        "metric": "Hit Rate@5",
        "label": args.label,
        "rerank_enabled": os.getenv("RERANK_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"},
        "rerank_model": os.getenv("RERANK_MODEL", ""),
        "cases_path": str(args.cases),
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "total_cases": total,
        "hit_count": hit_count,
        "miss_count": total - hit_count,
        "hit_rate_at_5": hit_count / total if total else 0.0,
        "per_case": per_case,
    }
    stamped, latest = write_results(results, args.out, args.label)
    print(json.dumps({k: results[k] for k in ("total_cases", "hit_count", "miss_count", "hit_rate_at_5")}, ensure_ascii=False, indent=2))
    print(f"wrote: {stamped}")
    print(f"latest: {latest}")


if __name__ == "__main__":
    main()
