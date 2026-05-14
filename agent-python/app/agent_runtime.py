from __future__ import annotations

import json
import logging
import os
import re
from pathlib import PurePath
import time
from typing import Any, Callable

from pydantic import BaseModel, Field


QUALITY_DECISION_PASS = "PASS"
QUALITY_DECISION_REWRITE = "NEEDS_REWRITE"
QUALITY_DECISION_USER_INPUT = "NEEDS_USER_INPUT"


class RetrievedEvidence(BaseModel):
    chunk_id: str
    material_id: int | None = None
    filename: str = ""
    score: float | None = None
    excerpt: str = ""


class SearchQuery(BaseModel):
    name: str
    text: str


class SearchResult(BaseModel):
    evidence: list[RetrievedEvidence]
    query_count: int
    per_query_counts: dict[str, int] = {}
    raw_hits: int
    deduped_hits: int


class AgentTraceStep(BaseModel):
    step_index: int
    stage: str
    tool_name: str
    input_summary: str
    output_summary: str
    status: str
    duration_ms: int


class QualityMetrics(BaseModel):
    section_completeness: float = Field(ge=0, le=1)
    citation_coverage: float = Field(ge=0, le=1)
    retrieved_chunks: int
    rewrite_triggered: bool
    structure_score: float = Field(default=0.0, ge=0, le=1)
    grounding_score: float = Field(default=0.0, ge=0, le=1)
    specificity_score: float = Field(default=0.0, ge=0, le=1)
    readiness_score: float = Field(default=0.0, ge=0, le=1)
    risk_score: float = Field(default=0.0, ge=0, le=1)
    total_score: float = Field(default=0.0, ge=0, le=1)
    pass_score: float = Field(default=0.75, ge=0, le=1)
    decision: str = QUALITY_DECISION_REWRITE
    manual_review_reason: str = ""
    review_summary: str = ""
    issues: list[str] = []
    rewrite_focus: list[str] = []
    quality_note: str


class AgentRunResult(BaseModel):
    markdown: str
    retrieved_evidence: list[RetrievedEvidence]
    quality: QualityMetrics
    agent_trace: list[AgentTraceStep]
    draft_version_reason: str


class QualityReview(BaseModel):
    structure_score: float = Field(default=0.0, ge=0, le=1)
    grounding_score: float = Field(default=0.0, ge=0, le=1)
    specificity_score: float = Field(default=0.0, ge=0, le=1)
    readiness_score: float = Field(default=0.0, ge=0, le=1)
    risk_score: float = Field(default=0.0, ge=0, le=1)
    total_score: float = Field(default=0.0, ge=0, le=1)
    review_summary: str = ""
    issues: list[str] = []
    rewrite_focus: list[str] = []
    decision_hint: str = QUALITY_DECISION_REWRITE


def run_report_agent(
    *,
    payload: Any,
    skill: Any,
    collection: Any,
    query: str | list[SearchQuery],
    embed_texts: Callable[[list[str]], list[list[float]]],
    llm_client: Callable[[], Any],
    build_prompt: Callable[[Any, Any, str], str],
    normalize_markdown: Callable[[str], str],
    logger: logging.Logger,
    max_steps: int = 4,
) -> AgentRunResult:
    trace: list[AgentTraceStep] = []

    def record(
        *,
        stage: str,
        tool_name: str,
        input_summary: str,
        started: float,
        output_summary: str,
        status: str = "SUCCEEDED",
    ) -> None:
        trace.append(
            AgentTraceStep(
                step_index=len(trace) + 1,
                stage=stage,
                tool_name=tool_name,
                input_summary=input_summary,
                output_summary=output_summary,
                status=status,
                duration_ms=max(1, int((time.perf_counter() - started) * 1000)),
            )
        )

    logger.info(
        "agent_loop_start assignment_id=%s skill=%s max_steps=%s",
        payload.assignment_id,
        skill.id,
        max_steps,
    )

    started = time.perf_counter()
    search_result = search_materials(collection, query, payload.top_k, embed_texts)
    evidence = search_result.evidence
    context_text = evidence_context(evidence)
    record(
        stage="retrieve",
        tool_name="search_materials",
        input_summary=f"top_k={payload.top_k} query_count={search_result.query_count}",
        output_summary=(
            f"raw_hits={search_result.raw_hits}; deduped={search_result.deduped_hits}; "
            f"retrieved={len(evidence)}; per_query={search_result.per_query_counts}"
        ),
        started=started,
    )
    logger.info(
        "tool_done assignment_id=%s tool=search_materials retrieved=%s",
        payload.assignment_id,
        len(evidence),
    )

    started = time.perf_counter()
    markdown = build_report_draft(payload, skill, context_text, llm_client, build_prompt, normalize_markdown)
    record(
        stage="generate",
        tool_name="build_report_draft",
        input_summary=f"skill={skill.id} evidence={len(evidence)}",
        output_summary=f"markdown_chars={len(markdown)}",
        started=started,
    )
    logger.info(
        "tool_done assignment_id=%s tool=build_report_draft chars=%s",
        payload.assignment_id,
        len(markdown),
    )

    pass_score = quality_pass_score()
    started = time.perf_counter()
    quality = evaluate_quality(
        markdown,
        skill.required_sections,
        evidence,
        rewrite_triggered=False,
        llm_client=llm_client,
        payload=payload,
        skill=skill,
        pass_score=pass_score,
    )
    record(
        stage="quality",
        tool_name="check_report_quality",
        input_summary=f"sections={len(skill.required_sections)} evidence={len(evidence)}",
        output_summary=quality.quality_note,
        started=started,
    )
    logger.info(
        "tool_done assignment_id=%s tool=check_report_quality decision=%s total_score=%.2f pass_score=%.2f",
        payload.assignment_id,
        quality.decision,
        quality.total_score,
        quality.pass_score,
    )

    rewrite_needed = len(trace) < max_steps and should_rewrite(markdown, quality, evidence)
    draft_version_reason = (
        f"模型质量门控通过，评分 {quality.total_score:.0%}。"
        if quality.decision == QUALITY_DECISION_PASS
        else f"模型质量门控判定为 {quality.decision}，评分 {quality.total_score:.0%}。"
    )
    if rewrite_needed:
        started = time.perf_counter()
        original_markdown = markdown
        original_quality = quality
        rewritten_markdown = rewrite_report(payload, skill, original_markdown, context_text, original_quality, llm_client, normalize_markdown)
        rewritten_quality = evaluate_quality(
            rewritten_markdown,
            skill.required_sections,
            evidence,
            rewrite_triggered=True,
            llm_client=llm_client,
            payload=payload,
            skill=skill,
            pass_score=pass_score,
        )
        if rewritten_quality.total_score >= original_quality.total_score:
            markdown = rewritten_markdown
            quality = rewritten_quality
            draft_version_reason = f"模型质量门控触发自动改写一次，当前评分 {quality.total_score:.0%}。"
            rewrite_summary = f"accepted_rewrite=true; markdown_chars={len(markdown)}; {quality.quality_note}"
        else:
            quality = original_quality.copy(update={"rewrite_triggered": True})
            markdown = original_markdown
            draft_version_reason = (
                f"模型质量门控触发自动改写一次，但改写评分 {rewritten_quality.total_score:.0%} "
                f"低于初稿 {original_quality.total_score:.0%}，已保留初稿。"
            )
            rewrite_summary = (
                f"accepted_rewrite=false; original_score={original_quality.total_score:.0%}; "
                f"rewrite_score={rewritten_quality.total_score:.0%}; kept_original=true"
            )
        record(
            stage="rewrite",
            tool_name="rewrite_report",
            input_summary="model quality gate requested rewrite",
            output_summary=rewrite_summary,
            started=started,
        )
        logger.info(
            "tool_done assignment_id=%s tool=rewrite_report chars=%s decision=%s total_score=%.2f",
            payload.assignment_id,
            len(markdown),
            quality.decision,
            quality.total_score,
        )

    logger.info(
        "agent_loop_done assignment_id=%s steps=%s rewritten=%s decision=%s total_score=%.2f",
        payload.assignment_id,
        len(trace),
        quality.rewrite_triggered,
        quality.decision,
        quality.total_score,
    )
    return AgentRunResult(
        markdown=markdown.strip(),
        retrieved_evidence=evidence,
        quality=quality,
        agent_trace=trace,
        draft_version_reason=draft_version_reason,
    )


def search_materials(
    collection: Any,
    query: str | list[SearchQuery],
    top_k: int,
    embed_texts: Callable[[list[str]], list[list[float]]],
) -> SearchResult:
    queries = normalize_search_queries(query)
    query_embeddings = embed_texts([item.text for item in queries])
    if not query_embeddings:
        return SearchResult(evidence=[], query_count=0, raw_hits=0, deduped_hits=0)
    results = collection.query(
        query_embeddings=query_embeddings,
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    documents_by_query = normalize_result_lists(results.get("documents"), len(queries))
    metadatas_by_query = normalize_result_lists(results.get("metadatas"), len(queries))
    distances_by_query = normalize_result_lists(results.get("distances"), len(queries))
    ids_by_query = normalize_result_lists(results.get("ids"), len(queries))

    by_chunk_id: dict[str, RetrievedEvidence] = {}
    per_query_counts: dict[str, int] = {}
    raw_hits = 0
    for query_index, query_item in enumerate(queries):
        documents = documents_by_query[query_index]
        metadatas = metadatas_by_query[query_index]
        distances = distances_by_query[query_index]
        ids = ids_by_query[query_index]
        per_query_counts[query_item.name] = len(documents)
        raw_hits += len(documents)
        for index, document in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
            distance = distances[index] if index < len(distances) else None
            score = None if distance is None else round(1 / (1 + max(float(distance), 0.0)), 4)
            chunk_id = str(ids[index]) if index < len(ids) else f"{query_index}-{index}"
            candidate = RetrievedEvidence(
                chunk_id=chunk_id,
                material_id=int(metadata["material_id"]) if metadata.get("material_id") is not None else None,
                filename=str(metadata.get("filename") or ""),
                score=score,
                excerpt=summarize(str(document), 900),
            )
            existing = by_chunk_id.get(chunk_id)
            existing_score = -1.0 if existing is None or existing.score is None else existing.score
            candidate_score = -1.0 if candidate.score is None else candidate.score
            if existing is None or candidate_score > existing_score:
                by_chunk_id[chunk_id] = candidate

    evidence = sorted(
        by_chunk_id.values(),
        key=lambda item: item.score if item.score is not None else -1.0,
        reverse=True,
    )[:top_k]
    return SearchResult(
        evidence=evidence,
        query_count=len(queries),
        per_query_counts=per_query_counts,
        raw_hits=raw_hits,
        deduped_hits=len(by_chunk_id),
    )


def normalize_search_queries(query: str | list[SearchQuery]) -> list[SearchQuery]:
    if isinstance(query, str):
        text = query.strip()
        return [SearchQuery(name="assignment_query", text=text)] if text else []
    normalized: list[SearchQuery] = []
    seen: set[str] = set()
    for index, item in enumerate(query):
        text = item.text.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(SearchQuery(name=item.name or f"query_{index + 1}", text=text))
    return normalized


def normalize_result_lists(value: Any, query_count: int) -> list[list[Any]]:
    if not isinstance(value, list) or not value:
        return [[] for _ in range(query_count)]
    if query_count == 1 and (not value or not isinstance(value[0], list)):
        return [value]
    lists = [item if isinstance(item, list) else [] for item in value]
    while len(lists) < query_count:
        lists.append([])
    return lists[:query_count]


def evidence_context(evidence: list[RetrievedEvidence]) -> str:
    if not evidence:
        return ""
    blocks = []
    for item in evidence:
        source = f"[chunk_id: {item.chunk_id} | source: {item.filename or 'unknown'}]"
        blocks.append(f"{source}\n{item.excerpt}")
    return "\n\n---\n\n".join(blocks)


def build_report_draft(
    payload: Any,
    skill: Any,
    context_text: str,
    llm_client: Callable[[], Any],
    build_prompt: Callable[[Any, Any, str], str],
    normalize_markdown: Callable[[str], str],
) -> str:
    response = llm_client().chat.completions.create(
        model=os.getenv("LLM_MODEL", "deepseek-v4-flash"),
        messages=[
            {"role": "system", "content": skill.system_prompt},
            {"role": "user", "content": build_prompt(payload, skill, context_text)},
        ],
        temperature=0.3,
    )
    return normalize_markdown(response.choices[0].message.content or "")


def rewrite_report(
    payload: Any,
    skill: Any,
    markdown: str,
    context_text: str,
    quality: QualityMetrics,
    llm_client: Callable[[], Any],
    normalize_markdown: Callable[[str], str],
) -> str:
    focus = "\n".join(f"- {item}" for item in quality.rewrite_focus[:5]) or "- 补足结构、依据和可交付表达。"
    issues = "\n".join(f"- {item}" for item in quality.issues[:5]) or "- 当前草稿仍需增强。"
    prompt = f"""
请对下面的中文 Markdown 报告草稿做一次“最小必要修补”，目标是提高结构完整度、证据贴合度和表达具体性。
这份输出会直接展示给用户，请输出可提交的完整报告正文，不要输出修改说明。

质量审稿结论：
{quality.review_summary or quality.quality_note}

主要问题：
{issues}

改写重点：
{focus}

硬性要求：
- 必须覆盖这些必要章节：{", ".join(skill.required_sections)}
- 优先保留原稿中的有效内容、具体步骤、数据、来源标注和结论，不要为了润色而删减证据。
- 来自资料的关键判断必须尽量沿用或补充 `[来源: 文件名]` 标注。
- 不要编造资料中没有的信息；如果缺少资料，不要用泛泛描述填充。
- 不要主动新增“待补充”“资料不足”“TODO”“TBD”等未完成标记；如果原稿已有这类标记，只保留确实需要用户确认的最小范围。
- 输出应比原稿更可提交；如果无法可靠改进，就尽量保持原稿主体，仅做小幅结构整理。
- 正文必须直接从标题或章节开始，不要写“以下是”“改写版”“最小必要修补版”等元说明。
- 只输出 Markdown 正文，不要输出代码块。

资料证据：
{summarize(context_text, 5000) or "没有检索到资料证据。"}

待改写草稿：
{markdown}
""".strip()
    response = llm_client().chat.completions.create(
        model=os.getenv("LLM_MODEL", "deepseek-v4-flash"),
        messages=[
            {"role": "system", "content": skill.system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return normalize_markdown(response.choices[0].message.content or markdown)


def evaluate_quality(
    markdown: str,
    required_sections: list[str],
    evidence: list[RetrievedEvidence],
    *,
    rewrite_triggered: bool,
    llm_client: Callable[[], Any] | None = None,
    payload: Any | None = None,
    skill: Any | None = None,
    pass_score: float | None = None,
) -> QualityMetrics:
    pass_score = quality_pass_score() if pass_score is None else clamp01(pass_score)
    section_completeness = calculate_section_completeness(markdown, required_sections)
    citation_coverage = calculate_citation_coverage(markdown, evidence)

    review = review_quality_with_llm(
        markdown=markdown,
        required_sections=required_sections,
        evidence=evidence,
        llm_client=llm_client,
        payload=payload,
        skill=skill,
        section_completeness=section_completeness,
        citation_coverage=citation_coverage,
    )
    manual_review_reason = manual_review_reason_for(markdown)
    total_score = model_quality_score(review)
    decision = decide_quality(
        markdown=markdown,
        evidence=evidence,
        section_completeness=section_completeness,
        total_score=total_score,
        pass_score=pass_score,
        decision_hint=review.decision_hint,
        manual_review_reason=manual_review_reason,
    )
    note_reason = f"需人工审核原因：{manual_review_reason}。" if manual_review_reason else review.review_summary
    note = (
        f"模型评分 {total_score:.0%}（通过阈值 {pass_score:.0%}），"
        f"决策 {decision}；章节完整率 {section_completeness:.0%}，"
        f"检索片段 {len(evidence)} 个。{note_reason}"
    )
    return QualityMetrics(
        section_completeness=round(section_completeness, 4),
        citation_coverage=round(citation_coverage, 4),
        retrieved_chunks=len(evidence),
        rewrite_triggered=rewrite_triggered,
        structure_score=round(review.structure_score, 4),
        grounding_score=round(review.grounding_score, 4),
        specificity_score=round(review.specificity_score, 4),
        readiness_score=round(review.readiness_score, 4),
        risk_score=round(review.risk_score, 4),
        total_score=round(total_score, 4),
        pass_score=round(pass_score, 4),
        decision=decision,
        manual_review_reason=manual_review_reason,
        review_summary=review.review_summary,
        issues=review.issues[:8],
        rewrite_focus=review.rewrite_focus[:8],
        quality_note=note,
    )


def review_quality_with_llm(
    *,
    markdown: str,
    required_sections: list[str],
    evidence: list[RetrievedEvidence],
    llm_client: Callable[[], Any] | None,
    payload: Any | None,
    skill: Any | None,
    section_completeness: float,
    citation_coverage: float,
) -> QualityReview:
    if llm_client is None:
        return fallback_quality_review(markdown, evidence, section_completeness, citation_coverage)

    evidence_summary = [
        {
            "chunk_id": item.chunk_id,
            "filename": item.filename,
            "score": item.score,
            "excerpt": summarize(item.excerpt, 260),
        }
        for item in evidence[:6]
    ]
    prompt_payload = {
        "assignment_id": getattr(payload, "assignment_id", None),
        "skill_id": getattr(skill, "id", None),
        "required_sections": required_sections,
        "local_signals": {
            "section_completeness": round(section_completeness, 4),
            "citation_coverage": round(citation_coverage, 4),
            "retrieved_chunks": len(evidence),
            "draft_chars": len(markdown or ""),
        },
        "evidence_summary": evidence_summary,
        "draft_markdown": summarize(markdown, 7000),
    }
    prompt = f"""
你是作业报告质量审稿器。请只基于给定草稿和检索证据评价，不要补写正文。
按 0 到 1 给分：
- structure: 是否覆盖必要章节、层次是否清楚
- grounding: 是否忠实使用证据，缺证据时不要给高分
- specificity: 是否有具体实现建议、指标、步骤，而不是泛泛而谈
- readiness: 是否接近可提交草稿
- risk: 幻觉、无依据断言、任务跑偏、资料不足等风险，风险越高分越高

返回严格 JSON，不要 Markdown，不要代码块：
{{
  "scores": {{
    "structure": 0.0,
    "grounding": 0.0,
    "specificity": 0.0,
    "readiness": 0.0,
    "risk": 0.0
  }},
  "total_score": 0.0,
  "review_summary": "一句中文评价",
  "issues": ["问题1", "问题2"],
  "rewrite_focus": ["改写重点1", "改写重点2"],
  "decision_hint": "PASS 或 NEEDS_REWRITE 或 NEEDS_USER_INPUT"
}}

待评价数据：
{json.dumps(prompt_payload, ensure_ascii=False)}
""".strip()
    try:
        response = llm_client().chat.completions.create(
            model=os.getenv("LLM_MODEL", "deepseek-v4-flash"),
            messages=[
                {"role": "system", "content": "你只输出可解析 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        return parse_quality_review(response.choices[0].message.content or "")
    except Exception:
        return fallback_quality_review(markdown, evidence, section_completeness, citation_coverage)


def parse_quality_review(content: str) -> QualityReview:
    raw = extract_json_object(content)
    data = json.loads(raw)
    scores = data.get("scores") if isinstance(data.get("scores"), dict) else {}
    return QualityReview(
        structure_score=score_value(scores, "structure"),
        grounding_score=score_value(scores, "grounding"),
        specificity_score=score_value(scores, "specificity"),
        readiness_score=score_value(scores, "readiness"),
        risk_score=score_value(scores, "risk"),
        total_score=score_value(data, "total_score"),
        review_summary=str(data.get("review_summary") or "").strip(),
        issues=string_list(data.get("issues")),
        rewrite_focus=string_list(data.get("rewrite_focus")),
        decision_hint=normalize_decision(str(data.get("decision_hint") or "")),
    )


def fallback_quality_review(
    markdown: str,
    evidence: list[RetrievedEvidence],
    section_completeness: float,
    citation_coverage: float,
) -> QualityReview:
    text = markdown.strip()
    weak_marker = has_weak_draft_marker(text)
    specificity = 0.75 if len(text) >= 1200 else 0.45 if len(text) >= 500 else 0.25
    readiness = min(section_completeness, specificity)
    grounding = citation_coverage if evidence else 0.35
    risk = 0.65 if weak_marker or not evidence else 0.25
    decision_hint = QUALITY_DECISION_REWRITE
    if not evidence and len(text) < 500:
        decision_hint = QUALITY_DECISION_USER_INPUT
    elif section_completeness >= 1.0 and grounding >= 0.6 and specificity >= 0.75 and not weak_marker:
        decision_hint = QUALITY_DECISION_PASS
    return QualityReview(
        structure_score=section_completeness,
        grounding_score=grounding,
        specificity_score=specificity,
        readiness_score=readiness,
        risk_score=risk,
        total_score=weighted_quality_score(
            structure_score=section_completeness,
            grounding_score=grounding,
            specificity_score=specificity,
            readiness_score=readiness,
            risk_score=risk,
        ),
        review_summary="模型审稿不可用，已使用本地质量信号兜底评分。",
        issues=["草稿偏短或存在待补充内容"] if weak_marker else [],
        rewrite_focus=["补充具体依据、实现步骤和可交付结论"] if decision_hint != QUALITY_DECISION_PASS else [],
        decision_hint=decision_hint,
    )


def should_rewrite(
    markdown: str,
    quality: QualityMetrics,
    evidence: list[RetrievedEvidence],
) -> bool:
    if not markdown.strip():
        return False
    if quality.decision == QUALITY_DECISION_USER_INPUT:
        return False
    if quality.manual_review_reason:
        return False
    if quality.decision == QUALITY_DECISION_REWRITE:
        return True
    return False


def decide_quality(
    *,
    markdown: str,
    evidence: list[RetrievedEvidence],
    section_completeness: float,
    total_score: float,
    pass_score: float,
    decision_hint: str,
    manual_review_reason: str = "",
) -> str:
    text = markdown.strip()
    if decision_hint == QUALITY_DECISION_USER_INPUT:
        return QUALITY_DECISION_USER_INPUT
    if not evidence and (total_score < 0.55 or len(text) < 600):
        return QUALITY_DECISION_USER_INPUT
    if section_completeness < 1.0:
        return QUALITY_DECISION_REWRITE
    if manual_review_reason:
        return QUALITY_DECISION_REWRITE
    if total_score >= pass_score:
        return QUALITY_DECISION_PASS
    return QUALITY_DECISION_REWRITE


def model_quality_score(review: QualityReview) -> float:
    return weighted_quality_score(
        structure_score=review.structure_score,
        grounding_score=review.grounding_score,
        specificity_score=review.specificity_score,
        readiness_score=review.readiness_score,
        risk_score=review.risk_score,
    )


def weighted_quality_score(
    *,
    structure_score: float,
    grounding_score: float,
    specificity_score: float,
    readiness_score: float,
    risk_score: float,
) -> float:
    return clamp01(
        structure_score * 0.25
        + grounding_score * 0.25
        + specificity_score * 0.20
        + readiness_score * 0.15
        + (1 - risk_score) * 0.15
    )


def manual_review_reason_for(markdown: str) -> str:
    if has_weak_draft_marker(markdown):
        return "草稿包含 TODO/TBD 或明显占位符"
    return ""


def calculate_section_completeness(markdown: str, required_sections: list[str]) -> float:
    headings = markdown_headings(markdown)
    if not required_sections:
        return 1.0
    section_hits = sum(1 for section in required_sections if section in headings)
    return section_hits / len(required_sections)


def calculate_citation_coverage(markdown: str, evidence: list[RetrievedEvidence]) -> float:
    if not evidence:
        return 0.0
    citations = extract_citations(markdown)
    hits = 0
    for item in evidence:
        if evidence_is_cited(item, citations):
            hits += 1
    return min(1.0, hits / max(len(evidence), 1))


def quality_pass_score() -> float:
    try:
        return clamp01(float(os.getenv("QUALITY_PASS_SCORE", "0.70")))
    except ValueError:
        return 0.70


def extract_citations(markdown: str) -> set[str]:
    text = markdown or ""
    citations: set[str] = set()
    for match in re.finditer(r"\[(?:来源|source)\s*:\s*([^\]]+)\]", text, flags=re.IGNORECASE):
        citations.add(match.group(1).strip())
    for match in re.finditer(r"\[chunk_id\s*:\s*([^\]\|]+)(?:\|[^\]]*)?\]", text, flags=re.IGNORECASE):
        citations.add(match.group(1).strip())
    return citations


def evidence_is_cited(item: RetrievedEvidence, citations: set[str]) -> bool:
    if not citations:
        return False
    chunk_id = (item.chunk_id or "").strip()
    filename = (item.filename or "").strip()
    basename = PurePath(filename).name if filename else ""
    for citation in citations:
        normalized = citation.strip()
        if chunk_id and normalized == chunk_id:
            return True
        if chunk_id and normalized.endswith(f"#{chunk_id}"):
            return True
        if filename and (normalized == filename or normalized.startswith(f"{filename}#")):
            return True
        if basename and (normalized == basename or normalized.startswith(f"{basename}#")):
            return True
    return False


def has_weak_draft_marker(text: str) -> bool:
    return weak_draft_marker_count(text) > 0


def weak_draft_marker_count(text: str) -> int:
    if not text:
        return 0
    count = len(re.findall(r"\b(?:TODO|TBD)\b", text, flags=re.IGNORECASE))
    placeholder_line = re.compile(
        r"^\s*(?:#{1,6}\s*)?(?:待填写|待完善|待确认|待用户补充|请补充|待补充[:：。]?|资料不足[:：。]?|缺少资料[:：。]?)\s*$"
    )
    count += sum(1 for line in text.splitlines() if placeholder_line.match(line.strip()))
    return count


def normalize_decision(value: str) -> str:
    decision = value.strip().upper()
    if decision in {QUALITY_DECISION_PASS, QUALITY_DECISION_REWRITE, QUALITY_DECISION_USER_INPUT}:
        return decision
    return QUALITY_DECISION_REWRITE


def score_value(scores: dict[str, Any], key: str) -> float:
    try:
        return clamp01(float(scores.get(key, 0.0)))
    except (TypeError, ValueError):
        return 0.0


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def extract_json_object(content: str) -> str:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("quality review did not contain a JSON object")
    return text[start : end + 1]


def markdown_headings(markdown: str) -> set[str]:
    return {
        match.group(1).strip()
        for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", markdown or "", re.MULTILINE)
    }


def summarize(text: str, max_chars: int) -> str:
    clean = " ".join((text or "").split())
    return clean if len(clean) <= max_chars else clean[: max_chars - 1].rstrip() + "..."


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
