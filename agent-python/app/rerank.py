from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


DEFAULT_RERANK_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def rerank_enabled() -> bool:
    return env_flag("RERANK_ENABLED", False)


def rerank_model() -> str:
    return os.getenv("RERANK_MODEL", "qwen3-rerank")


def rerank_candidate_multiplier() -> int:
    raw = os.getenv("RERANK_CANDIDATE_MULTIPLIER", "6")
    try:
        return max(1, int(raw))
    except ValueError:
        return 6


def rerank_endpoint() -> str:
    return os.getenv("RERANK_BASE_URL") or DEFAULT_RERANK_ENDPOINT


def rerank_api_key() -> str:
    return os.getenv("RERANK_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""


def rerank_document(item: Any) -> str:
    return "\n".join(
        part
        for part in [
            f"文件：{getattr(item, 'filename', '')}",
            f"章节：{getattr(item, 'section_title', '')}",
            f"章节摘要：{getattr(item, 'section_summary', '')}",
            f"证据片段：{getattr(item, 'excerpt', '')}",
        ]
        if part.strip("：")
    )


def parse_rerank_results(data: dict[str, Any]) -> list[tuple[int, float]]:
    output = data.get("output") if isinstance(data, dict) else {}
    results = output.get("results") if isinstance(output, dict) else data.get("results", [])
    parsed: list[tuple[int, float]] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        score = item.get("relevance_score", item.get("score"))
        if index is None or score is None:
            continue
        parsed.append((int(index), float(score)))
    return parsed


def call_qwen_rerank(query_text: str, documents: list[str]) -> list[tuple[int, float]]:
    api_key = rerank_api_key()
    if not api_key:
        raise RuntimeError("Missing rerank API key. Set RERANK_API_KEY or DASHSCOPE_API_KEY.")
    payload = {
        "model": rerank_model(),
        "input": {
            "query": query_text,
            "documents": documents,
        },
        "parameters": {
            "top_n": len(documents),
            "return_documents": False,
        },
    }
    request = urllib.request.Request(
        rerank_endpoint(),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(os.getenv("RERANK_TIMEOUT_SECONDS", "30"))) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Rerank API failed with HTTP {exc.code}: {body[:300]}") from exc
    return parse_rerank_results(data)


def rerank_evidence(query_text: str, evidence: list[Any]) -> list[Any]:
    if not evidence:
        return []
    documents = [rerank_document(item) for item in evidence]
    scores = call_qwen_rerank(query_text, documents)
    by_index = {index: score for index, score in scores}
    for index, item in enumerate(evidence):
        score = by_index.get(index)
        if score is not None:
            item.rerank_score = round(score, 6)
            item.rerank_model = rerank_model()
    return sorted(
        evidence,
        key=lambda item: (
            getattr(item, "rerank_score", None) is not None,
            getattr(item, "rerank_score", -1.0) or -1.0,
            getattr(item, "hybrid_score", -1.0) or -1.0,
        ),
        reverse=True,
    )
