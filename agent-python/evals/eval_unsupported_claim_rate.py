from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from app.agent_runtime import RetrievedEvidence  # noqa: E402
from app.main import (  # noqa: E402
    AUTO_SKILL,
    IndexRequest,
    MaterialRef,
    ReportRequest,
    chroma_client,
    collection_name,
    evaluator_client,
    evaluator_model,
    generate_report,
    index_materials,
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


def report_request(case: dict[str, Any]) -> ReportRequest:
    return ReportRequest(
        assignment_id=int(case["assignment_id"]),
        title=str(case["title"]),
        course=case.get("course"),
        description=case.get("description"),
        skill_id=case.get("skill_id") or AUTO_SKILL,
        top_k=int(case.get("top_k") or 5),
    )


def evidence_block(evidence: list[RetrievedEvidence], *, limit: int = 8) -> str:
    blocks = []
    for index, item in enumerate(evidence[:limit], start=1):
        blocks.append(
            "\n".join(
                [
                    f"[证据 {index}]",
                    f"source: {item.filename}",
                    f"section: {item.section_title}",
                    f"chunk_id: {item.chunk_id}",
                    f"section_summary: {item.section_summary[:500]}",
                    f"excerpt: {item.excerpt[:1400]}",
                ]
            )
        )
    return "\n\n---\n\n".join(blocks)


def extract_json_object(text: str) -> dict[str, Any]:
    clean = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean, flags=re.DOTALL)
    if fenced:
        clean = fenced.group(1)
    else:
        start = clean.find("{")
        end = clean.rfind("}")
        if start >= 0 and end > start:
            clean = clean[start : end + 1]
    return json.loads(clean)


def judge_claims(
    *,
    case: dict[str, Any],
    markdown: str,
    evidence: list[RetrievedEvidence],
) -> tuple[list[dict[str, Any]], str]:
    prompt = f"""
你是 RAG 报告事实支撑评审器。请判断报告中的具体 claim 是否被给定检索证据支持。

只统计具体、可验证的 claim，例如实验步骤、数据结果、算法结论、定义解释、论文观点、因果判断、对比结论。
不要统计标题、过渡句、泛泛写作句、作业要求复述。

判定规则：
1. 只有能从检索证据中直接找到，或能由证据合理推出的 claim，才算 supported=true。
2. 如果报告写了具体数据、方法细节、结论或对比，但证据中没有，必须判 supported=false。
3. 如果证据只支持相近主题但不支持该具体说法，也必须判 supported=false。
4. 请严格输出 JSON 对象，不要输出 Markdown 代码块。

输出格式：
{{
  "claims": [
    {{
      "claim": "报告中的具体 claim",
      "supported": true,
      "evidence": "支持它的证据来源或空字符串",
      "reason": "一句中文理由"
    }}
  ]
}}

作业标题：{case.get("title", "")}
课程：{case.get("course", "")}
作业说明：{case.get("description", "")}

检索证据：
{evidence_block(evidence)}

报告正文：
{markdown[:9000]}
""".strip()
    response = evaluator_client().chat.completions.create(
        model=evaluator_model(),
        messages=[
            {
                "role": "system",
                "content": "你是严格的中文事实核查评审器，只输出合法 JSON。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    data = extract_json_object(raw)
    claims = data.get("claims") if isinstance(data, dict) else []
    if not isinstance(claims, list):
        claims = []
    normalized = []
    for item in claims:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        if not claim:
            continue
        normalized.append(
            {
                "claim": claim,
                "supported": item.get("supported") is True,
                "evidence": str(item.get("evidence") or "").strip(),
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    return normalized, raw


def evaluate_case(case: dict[str, Any], *, keep_collections: bool) -> dict[str, Any]:
    assignment_id = int(case["assignment_id"])
    if not keep_collections:
        delete_collection(assignment_id)
    chunks_indexed = index_case(case)
    report = generate_report(report_request(case))
    claims, raw_judge = judge_claims(
        case=case,
        markdown=report.markdown,
        evidence=report.retrieved_evidence,
    )
    total_claims = len(claims)
    unsupported_claims = sum(1 for item in claims if item.get("supported") is not True)
    return {
        "case_id": case["case_id"],
        "assignment_id": assignment_id,
        "requested_skill_id": case.get("skill_id"),
        "resolved_skill_id": report.resolved_skill_id,
        "routing_mode": report.routing_mode,
        "chunks_indexed": chunks_indexed,
        "retrieved_chunks": report.retrieved_chunks,
        "total_claims": total_claims,
        "unsupported_claims": unsupported_claims,
        "unsupported_claim_rate": unsupported_claims / total_claims if total_claims else 0.0,
        "quality_total_score": report.quality.total_score if report.quality else None,
        "quality_decision": report.quality.decision if report.quality else None,
        "claims": claims,
        "retrieved_evidence": [
            {
                "rank": index,
                "chunk_id": item.chunk_id,
                "filename": item.filename,
                "section_title": item.section_title,
                "hybrid_score": item.hybrid_score,
                "rerank_score": item.rerank_score,
                "rerank_model": item.rerank_model,
                "excerpt_preview": (item.excerpt or "")[:360],
            }
            for index, item in enumerate(report.retrieved_evidence, start=1)
        ],
        "markdown": report.markdown,
        "raw_judge_output": raw_judge,
    }


def write_results(results: dict[str, Any], out_dir: Path, label: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    stamped = out_dir / f"unsupported_claim_rate{suffix}_{timestamp}.json"
    latest = out_dir / f"unsupported_claim_rate{suffix}_latest.json"
    text = json.dumps(results, ensure_ascii=False, indent=2)
    stamped.write_text(text + "\n", encoding="utf-8")
    latest.write_text(text + "\n", encoding="utf-8")
    return stamped, latest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Unsupported Claim Rate evaluation.")
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

    total_claims = sum(item["total_claims"] for item in per_case)
    unsupported_claims = sum(item["unsupported_claims"] for item in per_case)
    results = {
        "metric": "Unsupported Claim Rate",
        "label": args.label,
        "rerank_enabled": os.getenv("RERANK_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"},
        "rerank_model": os.getenv("RERANK_MODEL", ""),
        "cases_path": str(args.cases),
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "total_cases": len(per_case),
        "total_claims": total_claims,
        "unsupported_claims": unsupported_claims,
        "unsupported_claim_rate": unsupported_claims / total_claims if total_claims else 0.0,
        "per_case": per_case,
    }
    stamped, latest = write_results(results, args.out, args.label)
    print(
        json.dumps(
            {
                "total_cases": results["total_cases"],
                "total_claims": total_claims,
                "unsupported_claims": unsupported_claims,
                "unsupported_claim_rate": results["unsupported_claim_rate"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"wrote: {stamped}")
    print(f"latest: {latest}")


if __name__ == "__main__":
    main()
