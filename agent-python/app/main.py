from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Iterable
import urllib.error
import urllib.request

import chromadb
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from openai import APIConnectionError, APIError, OpenAI
from pydantic import BaseModel, Field
from pypdf import PdfReader

from app.agent_runtime import AgentRunResult, AgentTraceStep, QualityMetrics, RetrievedEvidence, SearchQuery, extract_keywords, improve_report_agent, run_report_agent
from app.agent_streaming import stream_agent_events
from app.skill_registry import AUTO_SKILL, SKILLS, VALID_SKILLS, SkillSpec


ROUTING_THRESHOLD = 0.7
DYNAMIC_PLANNER_SKILL = "dynamic_planner"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("homework_agent")


class MaterialRef(BaseModel):
    id: int
    filename: str
    path: str
    content_type: str | None = None


class IndexRequest(BaseModel):
    assignment_id: int
    title: str
    description: str | None = None
    materials: list[MaterialRef]


class IndexResponse(BaseModel):
    assignment_id: int
    chunks_indexed: int
    parent_chunks: list["ParentChunkRecord"] = []


class DeleteCollectionResponse(BaseModel):
    assignment_id: int
    deleted: bool


class ReportRequest(BaseModel):
    assignment_id: int
    title: str
    course: str | None = None
    description: str | None = None
    skill_id: str | None = Field(default=AUTO_SKILL)
    top_k: int = Field(default=8, ge=1, le=20)


class ImproveReportRequest(ReportRequest):
    current_markdown: str = Field(min_length=1)
    current_quality: QualityMetrics | None = None


class ReportResponse(BaseModel):
    assignment_id: int
    markdown: str
    retrieved_chunks: int
    resolved_skill_id: str
    routing_mode: str
    routing_confidence: float
    routing_reason: str
    retrieved_evidence: list[RetrievedEvidence] = []
    quality: QualityMetrics | None = None
    agent_trace: list[AgentTraceStep] = []
    draft_version_reason: str = "初稿已生成。"


class RoutingResult(BaseModel):
    mode: str
    resolved_skill_id: str
    confidence: float = Field(ge=0, le=1)
    reason: str


class IndexedChunk(BaseModel):
    id: str
    document: str
    metadata: dict[str, str | int | float | bool]


class ParentChunkRecord(BaseModel):
    id: str
    assignment_id: int
    material_id: int
    filename: str
    parent_index: int
    section_title: str
    content: str


app = FastAPI(title="FZU Homework Agent", version="0.1.0")


def get_api_key() -> str:
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "")
    elif provider == "deepseek":
        key = os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    else:
        key = os.getenv("DASHSCOPE_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise HTTPException(
            status_code=500,
            detail="Missing model API key. Set DEEPSEEK_API_KEY, DASHSCOPE_API_KEY or OPENAI_API_KEY.",
        )
    return key


def llm_client() -> OpenAI:
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
    default_base_url = {
        "deepseek": "https://api.deepseek.com",
        "openai": None,
    }.get(provider, "https://dashscope.aliyuncs.com/compatible-mode/v1")
    base_url = os.getenv("LLM_BASE_URL") or default_base_url
    kwargs = {"api_key": get_api_key()}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(
        **kwargs,
    )


def evaluator_model() -> str:
    return os.getenv("EVALUATOR_MODEL") or os.getenv("LLM_MODEL", "deepseek-v4-flash")


def evaluator_mode() -> str:
    configured = any(
        os.getenv(name)
        for name in ("EVALUATOR_MODEL", "EVALUATOR_BASE_URL", "EVALUATOR_API_KEY")
    )
    return "independent" if configured else "fallback"


def evaluator_client() -> OpenAI:
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
    default_base_url = {
        "deepseek": "https://api.deepseek.com",
        "openai": None,
    }.get(provider, "https://dashscope.aliyuncs.com/compatible-mode/v1")
    base_url = os.getenv("EVALUATOR_BASE_URL") or os.getenv("LLM_BASE_URL") or default_base_url
    kwargs = {"api_key": os.getenv("EVALUATOR_API_KEY") or get_api_key()}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def embedding_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("EMBEDDING_API_KEY", "")
        or os.getenv("DASHSCOPE_API_KEY", "")
        or os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv(
            "EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
    )


def chroma_client() -> chromadb.HttpClient:
    return chromadb.HttpClient(
        host=os.getenv("CHROMA_HOST", "localhost"),
        port=int(os.getenv("CHROMA_PORT", "8001")),
    )


def collection_name(assignment_id: int) -> str:
    return f"assignment_{assignment_id}"


def collection_metadata() -> dict[str, str]:
    return {"hnsw:space": "cosine"}


def read_material_text(material: MaterialRef) -> str:
    path = Path(material.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Material not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n\n".join(
            f"[page:{index + 1}]\n{page.extract_text() or ''}"
            for index, page in enumerate(reader.pages)
        )

    if suffix in {".md", ".markdown", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported material type for {material.filename}. Upload PDF or Markdown.",
    )


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 160) -> list[str]:
    clean = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not clean:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(start + chunk_size, len(clean))
        chunks.append(clean[start:end])
        if end == len(clean):
            break
        start = max(0, end - overlap)
    return chunks


def build_index_chunks(assignment_id: int, material: MaterialRef, text: str) -> list[IndexedChunk]:
    sections = split_material_sections(material.filename, text)
    document_summary = framework_summary_for_index(material.filename, text, sections)
    key_terms = "、".join(extract_keywords(" ".join([material.filename, text]))[:18])
    chunks: list[IndexedChunk] = []
    for parent_index, section in enumerate(sections):
        section_title = section["title"]
        section_text = section["text"]
        parent_id = f"{material.id}-p{parent_index}"
        for chunk_index, chunk in enumerate(chunk_text(section_text)):
            chunks.append(
                IndexedChunk(
                    id=f"{material.id}-{parent_index}-{chunk_index}",
                    document=chunk,
                    metadata={
                        "assignment_id": assignment_id,
                        "material_id": material.id,
                        "filename": material.filename,
                        "section_title": section_title,
                        "parent_id": parent_id,
                        "chunk_index": chunk_index,
                        "parent_index": parent_index,
                        "source_type": "child",
                        "document_summary": document_summary,
                        "key_terms": key_terms,
                    },
                )
            )
    return chunks


def build_parent_chunks(assignment_id: int, material: MaterialRef, text: str) -> list[ParentChunkRecord]:
    records: list[ParentChunkRecord] = []
    for parent_index, section in enumerate(split_material_sections(material.filename, text)):
        section_text = section["text"].strip()
        if not section_text:
            continue
        records.append(
            ParentChunkRecord(
                id=f"{material.id}-p{parent_index}",
                assignment_id=assignment_id,
                material_id=material.id,
                filename=material.filename,
                parent_index=parent_index,
                section_title=section["title"],
                content=section_text,
            )
        )
    return records


def split_material_sections(filename: str, text: str) -> list[dict[str, str]]:
    suffix = Path(filename).suffix.lower()
    clean = text.strip()
    if not clean:
        return []
    if suffix in {".md", ".markdown"}:
        return split_markdown_sections(clean)
    if "[page:" in clean:
        return split_page_sections(clean)
    return split_paragraph_sections(clean)


def split_markdown_sections(text: str) -> list[dict[str, str]]:
    matches = list(re.finditer(r"^(#{1,6})\s+(.+?)\s*$", text, flags=re.MULTILINE))
    if not matches:
        return split_paragraph_sections(text)
    sections: list[dict[str, str]] = []
    preface = text[: matches[0].start()].strip()
    if preface:
        sections.append({"title": "文档开头", "text": preface})
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = match.group(2).strip()
        body = text[start:end].strip()
        section_text = f"{title}\n{body}".strip()
        if section_text:
            sections.append({"title": title, "text": section_text})
    return sections


def split_page_sections(text: str) -> list[dict[str, str]]:
    parts = re.split(r"^\[page:(\d+)\]\s*$", text, flags=re.MULTILINE)
    sections: list[dict[str, str]] = []
    for index in range(1, len(parts), 2):
        page = parts[index]
        body = parts[index + 1].strip() if index + 1 < len(parts) else ""
        if body:
            sections.append({"title": f"第 {page} 页", "text": body})
    return sections or split_paragraph_sections(text)


def split_paragraph_sections(text: str) -> list[dict[str, str]]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return []
    sections: list[dict[str, str]] = []
    buffer: list[str] = []
    section_index = 1
    for paragraph in paragraphs:
        buffer.append(paragraph)
        if sum(len(item) for item in buffer) >= 1800:
            sections.append({"title": f"资料片段 {section_index}", "text": "\n\n".join(buffer)})
            section_index += 1
            buffer = []
    if buffer:
        sections.append({"title": f"资料片段 {section_index}", "text": "\n\n".join(buffer)})
    return sections


def outline_for_sections(sections: list[dict[str, str]]) -> str:
    if not sections:
        return ""
    lines = []
    for index, section in enumerate(sections[:12], start=1):
        lines.append(f"{index}. {section['title']}：{summarize_for_index(section['text'], 120)}")
    return "\n".join(lines)


def framework_summary_for_index(filename: str, text: str, sections: list[dict[str, str]], max_chars: int = 900) -> str:
    clean = " ".join((text or "").split())
    headings = [section["title"].strip() for section in sections if section.get("title", "").strip()]
    representative: list[str] = []
    if sections:
        selected = [sections[0]]
        if len(sections) > 2:
            selected.append(sections[len(sections) // 2])
        if len(sections) > 1:
            selected.append(sections[-1])
        seen_titles: set[str] = set()
        for section in selected:
            title = section["title"].strip()
            if title in seen_titles:
                continue
            seen_titles.add(title)
            sentence = first_representative_sentence(section["text"])
            if sentence:
                representative.append(f"{title}：{sentence}")
    else:
        representative.extend(extract_representative_sentences(clean, 3))

    terms = extract_keywords(" ".join([filename, clean]))[:12]
    parts = [
        f"文档：{filename}",
        "框架：" + " / ".join(headings[:10]) if headings else "",
        "要点：" + "；".join(representative[:5]) if representative else "",
        "关键词：" + "、".join(terms) if terms else "",
    ]
    summary = "\n".join(part for part in parts if part.strip())
    if len(summary) <= max_chars:
        return summary
    lines: list[str] = []
    total = 0
    for line in summary.splitlines():
        if total + len(line) + 1 > max_chars:
            break
        lines.append(line)
        total += len(line) + 1
    return "\n".join(lines) or summary[:max_chars].rstrip()


def first_representative_sentence(text: str) -> str:
    sentences = extract_representative_sentences(text, 1)
    return sentences[0] if sentences else ""


def extract_representative_sentences(text: str, limit: int) -> list[str]:
    clean = " ".join((text or "").split())
    pieces = [part.strip() for part in re.split(r"(?<=[。！？.!?])\s*", clean) if part.strip()]
    if not pieces and clean:
        pieces = [clean]
    result: list[str] = []
    for piece in pieces:
        if len(piece) < 8 and len(pieces) > 1:
            continue
        result.append(summarize_for_index(piece, 180))
        if len(result) >= limit:
            break
    return result


def summarize_for_index(text: str, max_chars: int) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_chars:
        return clean
    sentence_end = max(clean.rfind("。", 0, max_chars), clean.rfind(".", 0, max_chars))
    if sentence_end > max_chars * 0.45:
        return clean[: sentence_end + 1]
    return clean[: max_chars - 1].rstrip() + "..."


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    text_list = list(texts)
    if not text_list:
        return []

    embeddings: list[list[float]] = []
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-v2")
    client = embedding_client()
    batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "25"))
    max_retries = int(os.getenv("EMBEDDING_MAX_RETRIES", "3"))
    for start in range(0, len(text_list), batch_size):
        batch = text_list[start : start + batch_size]
        response = create_embeddings_with_retry(
            client=client,
            model=model,
            batch=batch,
            batch_index=start // batch_size,
            max_retries=max_retries,
        )
        embeddings.extend(item.embedding for item in response.data)
    return embeddings


def create_embeddings_with_retry(
    client: OpenAI,
    model: str,
    batch: list[str],
    batch_index: int,
    max_retries: int,
):
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "embedding_request_start model=%s batch_index=%s batch_size=%s attempt=%s",
                model,
                batch_index,
                len(batch),
                attempt,
            )
            return client.embeddings.create(model=model, input=batch)
        except APIConnectionError as exc:
            logger.warning(
                "embedding_connection_failed model=%s batch_index=%s attempt=%s/%s error_type=%s",
                model,
                batch_index,
                attempt,
                max_retries,
                exc.__class__.__name__,
            )
            if attempt >= max_retries:
                raise HTTPException(
                    status_code=502,
                    detail="Embedding service connection failed. Please retry later or check DashScope network access.",
                ) from exc
        except APIError as exc:
            logger.warning(
                "embedding_api_failed model=%s batch_index=%s attempt=%s/%s status=%s error_type=%s",
                model,
                batch_index,
                attempt,
                max_retries,
                getattr(exc, "status_code", None),
                exc.__class__.__name__,
            )
            if attempt >= max_retries:
                raise HTTPException(
                    status_code=502,
                    detail="Embedding service request failed. Please check model configuration and retry.",
                ) from exc
        time.sleep(min(2 ** (attempt - 1), 6))

    raise HTTPException(status_code=502, detail="Embedding service request failed.")


def normalize_markdown(markdown: str) -> str:
    text = markdown.strip()
    fenced = re.fullmatch(
        r"```(?:markdown|md)?\s*\n(?P<body>[\s\S]*?)\n```",
        text,
        re.IGNORECASE,
    )
    if fenced:
        text = fenced.group("body").strip()
    return strip_meta_preface(text)


def strip_meta_preface(markdown: str) -> str:
    lines = markdown.strip().splitlines()
    if not lines:
        return ""
    first = lines[0].strip()
    meta_words = ("以下是", "下面是", "修补版", "改写版", "报告草稿", "最小必要修补")
    if any(word in first for word in meta_words):
        for index, line in enumerate(lines[1:], start=1):
            if re.match(r"^#{1,6}\s+\S+", line.strip()):
                return "\n".join(lines[index:]).strip()
    return markdown.strip()


def normalize_skill_id(skill_id: str | None) -> str:
    value = (skill_id or AUTO_SKILL).strip()
    if value.upper() == AUTO_SKILL:
        return AUTO_SKILL
    if value not in VALID_SKILLS:
        raise HTTPException(status_code=400, detail=f"Unsupported skill_id: {value}")
    return value


def route_skill_by_rules(title: str, course: str | None, description: str | None) -> RoutingResult | None:
    text = " ".join(part for part in [title, course or "", description or ""] if part).lower()
    keyword_groups = {
        "paper_summary": [
            "论文", "paper", "article", "摘要", "创新点", "related work", "methodology",
            "实验结果", "contribution", "survey", "研究背景", "文献", "阅读",
        ],
        "course_qa_report": [
            "问题", "解答", "回答", "根据材料", "课程材料", "汇报", "讲解", "说明",
            "为什么", "如何", "怎么", "分析以下", "请结合", "问答",
        ],
        "lab_report": [
            "实验", "代码", "程序", "实现", "仿真", "训练", "数据集", "结果分析",
            "实验报告", "步骤", "算法实现", "编程", "模型",
        ],
    }
    scores = {
        skill_id: sum(1 for keyword in keywords if keyword in text)
        for skill_id, keywords in keyword_groups.items()
    }
    best_skill, best_score = max(scores.items(), key=lambda item: item[1])
    ordered_scores = sorted(scores.values(), reverse=True)
    if best_score == 0 or best_score <= ordered_scores[1]:
        return None

    confidence = min(0.95, 0.45 + best_score * 0.18)
    if confidence >= ROUTING_THRESHOLD:
        return RoutingResult(
            mode="known_skill",
            resolved_skill_id=best_skill,
            confidence=confidence,
            reason=f"规则路由命中 {best_score} 个{skill_label(best_skill)}关键词。",
        )
    return RoutingResult(
        mode="dynamic_plan",
        resolved_skill_id=DYNAMIC_PLANNER_SKILL,
        confidence=confidence,
        reason=f"规则路由仅弱命中{skill_label(best_skill)}，置信度低于阈值，转入动态任务规划。",
    )


def route_skill_with_llm(title: str, course: str | None, description: str | None) -> RoutingResult:
    prompt = f"""
请为当前作业选择最合适的生成策略。
只返回严格 JSON 对象，字段为：mode, resolved_skill_id, confidence, reason。

可选固定 Skill：
- lab_report：实验报告、编程实践、算法实现、结果分析
- paper_summary：论文阅读、文献总结、创新点分析、论文汇报
- course_qa_report：课程资料问答、知识讲解、汇报总结

如果固定 Skill 都不够匹配，请返回：
{{"mode":"dynamic_plan","resolved_skill_id":"dynamic_planner","confidence":0.4,"reason":"中文原因"}}

- 只有 confidence >= 0.7 时才使用 mode="known_skill"。
- 开放型、混合型、描述不清或不属于固定 Skill 的任务，使用 mode="dynamic_plan"。
- confidence 必须是 0 到 1 的数字。
- reason 必须使用中文，说明为什么选择该策略，不要输出英文。

作业标题：{title}
课程：{course or "未提供"}
作业描述：{description or "未提供"}
""".strip()
    try:
        logger.info("routing_llm_start title_chars=%s course_present=%s", len(title), bool(course))
        response = llm_client().chat.completions.create(
            model=os.getenv("LLM_MODEL", "deepseek-v4-flash"),
            messages=[
                {"role": "system", "content": "你是严格的中文作业类型识别器，只输出可解析 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        content = (response.choices[0].message.content or "").strip()
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            data = json.loads(json_match.group(0))
            skill_id = str(data.get("resolved_skill_id", DYNAMIC_PLANNER_SKILL))
            confidence = max(0.0, min(float(data.get("confidence", 0)), 1.0))
            reason = chinese_reason(str(data.get("reason", "")), f"模型判断该任务更适合{skill_label(skill_id)}。")
            if skill_id not in VALID_SKILLS or skill_id == DYNAMIC_PLANNER_SKILL or confidence < ROUTING_THRESHOLD:
                logger.info("routing_llm_dynamic skill=%s confidence=%.2f", skill_id, confidence)
                return RoutingResult(
                    mode="dynamic_plan",
                    resolved_skill_id=DYNAMIC_PLANNER_SKILL,
                    confidence=confidence,
                    reason=reason,
                )
            logger.info("routing_llm_known skill=%s confidence=%.2f", skill_id, confidence)
            return RoutingResult(
                mode="known_skill",
                resolved_skill_id=skill_id,
                confidence=confidence,
                reason=reason,
            )

        match = re.search(r"(lab_report|paper_summary|course_qa_report)", content)
        if match:
            return RoutingResult(
                mode="known_skill",
                resolved_skill_id=match.group(1),
                confidence=ROUTING_THRESHOLD,
                reason=f"模型返回了已知 Skill：{skill_label(match.group(1))}。",
            )
    except Exception:
        logger.exception("routing_llm_failed")

    return RoutingResult(
        mode="dynamic_plan",
        resolved_skill_id=DYNAMIC_PLANNER_SKILL,
        confidence=0.0,
        reason="模型路由失败，已回退到动态任务规划。",
    )


def resolve_skill(payload: ReportRequest) -> tuple[SkillSpec, RoutingResult]:
    requested = normalize_skill_id(payload.skill_id)
    if requested != AUTO_SKILL:
        logger.info(
            "routing_manual assignment_id=%s skill=%s",
            payload.assignment_id,
            requested,
        )
        return SKILLS[requested], RoutingResult(
            mode="known_skill",
            resolved_skill_id=requested,
            confidence=1.0,
            reason=f"用户手动选择了{skill_label(requested)}。",
        )

    rule_result = route_skill_by_rules(payload.title, payload.course, payload.description)
    if rule_result and rule_result.mode == "known_skill":
        logger.info(
            "routing_rule_known assignment_id=%s skill=%s confidence=%.2f",
            payload.assignment_id,
            rule_result.resolved_skill_id,
            rule_result.confidence,
        )
        return SKILLS[rule_result.resolved_skill_id], rule_result

    llm_result = route_skill_with_llm(payload.title, payload.course, payload.description)
    if llm_result.mode == "known_skill" and llm_result.confidence >= ROUTING_THRESHOLD:
        logger.info(
            "routing_llm_selected assignment_id=%s skill=%s confidence=%.2f",
            payload.assignment_id,
            llm_result.resolved_skill_id,
            llm_result.confidence,
        )
        return SKILLS[llm_result.resolved_skill_id], llm_result

    dynamic_result = RoutingResult(
        mode="dynamic_plan",
        resolved_skill_id=DYNAMIC_PLANNER_SKILL,
        confidence=max(rule_result.confidence if rule_result else 0.0, llm_result.confidence),
        reason=(
            llm_result.reason
            if llm_result.confidence > 0
            else (rule_result.reason if rule_result else "没有高置信命中固定 Skill，进入动态任务规划。")
        ),
    )
    logger.info(
        "routing_dynamic assignment_id=%s confidence=%.2f reason=%s",
        payload.assignment_id,
        dynamic_result.confidence,
        dynamic_result.reason,
    )
    return SKILLS[DYNAMIC_PLANNER_SKILL], dynamic_result


def build_prompt(payload: ReportRequest, skill: SkillSpec, context_text: str, report_plan: str = "") -> str:
    sections = ", ".join(skill.required_sections)
    dynamic_note = ""
    if skill.id == DYNAMIC_PLANNER_SKILL:
        dynamic_note = """
动态任务规划流程：
1. 分析作业目标、交付物和评价维度。
2. 根据任务特点设计合适的报告结构。
3. 使用检索证据填充主体内容。
4. 输出连贯完整的最终草稿，避免未完成占位符。
""".strip()

    if report_plan.strip():
        dynamic_note = f"{dynamic_note}\n\n动态报告计划：\n{report_plan.strip()}".strip()

    return f"""
请使用所选生成策略“{skill.label}”为当前作业撰写中文 Markdown 报告。
这份内容会作为用户拿到的报告版本，请在证据允许范围内尽量接近可提交状态。
必须基于给定资料摘录和作业要求组织内容。

作业标题：{payload.title}
课程：{payload.course or "未提供"}
作业说明或问题：{payload.description or "未提供"}

带来源标签的资料摘录：
{context_text or "未检索到相关资料。请基于作业说明生成连贯草稿，不要添加占位符。"}

必要或建议章节：{sections}

Skill 说明：
{skill.instructions or "请遵循 Skill 元数据和必要章节。"}

{dynamic_note}

额外输出要求：
- 只输出 Markdown 正文，不要用代码块包裹全文。
- 不要输出“以下是”“改写版”“最小必要修补”等元说明，也不要解释你如何修改草稿。
- 不要输出“待补充”“资料不足”“TODO”“TBD”等未完成占位符。
- 如果证据有限，请使用保守表述，用正常正文说明必要假设或限制，并保持报告连贯。
- 使用检索证据时添加简洁来源标注，例如 `[来源: filename]`。
""".strip()


def build_search_queries(payload: ReportRequest, skill: SkillSpec) -> list[SearchQuery]:
    assignment_parts = [
        f"作业标题：{payload.title}",
        f"课程：{payload.course or ''}",
        f"作业描述：{payload.description or ''}",
    ]
    structure_parts = [
        f"生成类型：{skill.label}",
        f"必要章节：{'、'.join(skill.required_sections)}",
        f"检索提示：{skill.query_hint}",
    ]
    section_parts = [
        f"围绕这些章节检索资料：{'、'.join(skill.required_sections)}",
        f"作业要求：{payload.description or payload.title}",
    ]
    return [
        SearchQuery(name="assignment_query", text="\n".join(part for part in assignment_parts if part.strip())),
        SearchQuery(
            name="structure_query",
            text="\n".join(part for part in [*structure_parts, *section_parts] if part.strip()),
        ),
    ]


def skill_label(skill_id: str) -> str:
    return {
        "lab_report": "实验报告",
        "paper_summary": "论文总结",
        "course_qa_report": "课程问答汇报",
        "dynamic_planner": "动态任务规划",
        AUTO_SKILL: "智能识别",
    }.get(skill_id, skill_id)


def chinese_reason(reason: str, fallback: str) -> str:
    text = (reason or "").strip()
    if not text:
        return fallback
    ascii_letters = sum(1 for char in text if ("a" <= char.lower() <= "z"))
    chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    if ascii_letters > chinese_chars * 2:
        return fallback
    return text


def reset_assignment_collection(assignment_id: int):
    client = chroma_client()
    name = collection_name(assignment_id)
    try:
        client.delete_collection(name=name)
        logger.info("collection_deleted assignment_id=%s name=%s", assignment_id, name)
    except Exception as exc:
        if "does not exist" not in str(exc).lower() and "not found" not in str(exc).lower():
            logger.warning("collection_delete_skipped assignment_id=%s error=%s", assignment_id, exc.__class__.__name__)
    return client.get_or_create_collection(name=name, metadata=collection_metadata())


def backend_base_url() -> str:
    return os.getenv("BACKEND_BASE_URL", "http://localhost:8080").rstrip("/")


def fetch_parent_chunks(assignment_id: int, parent_ids: list[str]) -> dict[str, str]:
    ids = [parent_id for parent_id in parent_ids if parent_id]
    if not ids:
        return {}
    payload = json.dumps({"parent_ids": ids}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{backend_base_url()}/api/internal/assignments/{assignment_id}/parent-chunks/lookup",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(os.getenv("BACKEND_PARENT_CHUNK_TIMEOUT_SECONDS", "10"))) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        logger.warning("parent_chunk_lookup_failed assignment_id=%s parent_count=%s", assignment_id, len(ids))
        return {}
    chunks = data.get("chunks") if isinstance(data, dict) else {}
    if not isinstance(chunks, dict):
        return {}
    return {str(key): str(value) for key, value in chunks.items() if value is not None}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/agent/skills")
def list_skills() -> list[dict[str, str]]:
    return [
        {
            "id": skill.id,
            "label": skill.label,
            "description": skill.description,
        }
        for skill in SKILLS.values()
    ]


@app.post("/agent/index", response_model=IndexResponse)
def index_materials(payload: IndexRequest) -> IndexResponse:
    logger.info(
        "index_start assignment_id=%s materials=%s",
        payload.assignment_id,
        len(payload.materials),
    )
    collection = reset_assignment_collection(payload.assignment_id)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str | int | float | bool]] = []
    parent_chunks: list[ParentChunkRecord] = []

    for material in payload.materials:
        text = read_material_text(material)
        parent_chunks.extend(build_parent_chunks(payload.assignment_id, material, text))
        for chunk in build_index_chunks(payload.assignment_id, material, text):
            ids.append(chunk.id)
            documents.append(chunk.document)
            metadatas.append(chunk.metadata)

    if not documents:
        logger.info("index_done assignment_id=%s chunks=0", payload.assignment_id)
        return IndexResponse(assignment_id=payload.assignment_id, chunks_indexed=0, parent_chunks=[])

    embeddings = embed_texts(documents)
    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    logger.info(
        "index_done assignment_id=%s chunks=%s",
        payload.assignment_id,
        len(documents),
    )
    return IndexResponse(
        assignment_id=payload.assignment_id,
        chunks_indexed=len(documents),
        parent_chunks=parent_chunks,
    )


@app.delete("/agent/collections/{assignment_id}", response_model=DeleteCollectionResponse)
def delete_assignment_collection(assignment_id: int) -> DeleteCollectionResponse:
    client = chroma_client()
    name = collection_name(assignment_id)
    try:
        client.delete_collection(name=name)
        logger.info("collection_deleted assignment_id=%s name=%s", assignment_id, name)
        return DeleteCollectionResponse(assignment_id=assignment_id, deleted=True)
    except Exception as exc:
        if "does not exist" in str(exc).lower() or "not found" in str(exc).lower():
            return DeleteCollectionResponse(assignment_id=assignment_id, deleted=False)
        raise HTTPException(status_code=502, detail="删除向量集合失败，请检查 ChromaDB 服务。") from exc


@app.post("/agent/generate-report", response_model=ReportResponse)
def generate_report(payload: ReportRequest) -> ReportResponse:
    return execute_generate_report(payload)


@app.post("/agent/generate-report-stream")
def generate_report_stream(payload: ReportRequest) -> StreamingResponse:
    return StreamingResponse(
        stream_agent_events(lambda event_sink: execute_generate_report(payload, event_sink=event_sink)),
        media_type="application/x-ndjson",
    )


def execute_generate_report(payload: ReportRequest, event_sink=None) -> ReportResponse:
    logger.info(
        "generate_start assignment_id=%s requested_skill=%s top_k=%s",
        payload.assignment_id,
        payload.skill_id,
        payload.top_k,
    )
    collection = chroma_client().get_or_create_collection(
        name=collection_name(payload.assignment_id),
        metadata=collection_metadata(),
    )
    skill, routing = resolve_skill(payload)

    queries = build_search_queries(payload, skill)
    run: AgentRunResult = run_report_agent(
        payload=payload,
        skill=skill,
        collection=collection,
        query=queries,
        embed_texts=embed_texts,
        parent_chunk_loader=lambda parent_ids: fetch_parent_chunks(payload.assignment_id, parent_ids),
        llm_client=llm_client,
        quality_llm_client=evaluator_client,
        evaluator_model=evaluator_model(),
        evaluator_mode=evaluator_mode(),
        build_prompt=build_prompt,
        normalize_markdown=normalize_markdown,
        logger=logger,
        event_sink=event_sink,
    )
    logger.info(
        "generate_done assignment_id=%s skill=%s retrieved=%s rewritten=%s",
        payload.assignment_id,
        skill.id,
        len(run.retrieved_evidence),
        run.quality.rewrite_triggered,
    )
    return ReportResponse(
        assignment_id=payload.assignment_id,
        markdown=run.markdown.strip(),
        retrieved_chunks=len(run.retrieved_evidence),
        resolved_skill_id=skill.id,
        routing_mode=routing.mode,
        routing_confidence=routing.confidence,
        routing_reason=routing.reason,
        retrieved_evidence=run.retrieved_evidence,
        quality=run.quality,
        agent_trace=run.agent_trace,
        draft_version_reason=run.draft_version_reason,
    )


@app.post("/agent/improve-report", response_model=ReportResponse)
def improve_report(payload: ImproveReportRequest) -> ReportResponse:
    return execute_improve_report(payload)


@app.post("/agent/improve-report-stream")
def improve_report_stream(payload: ImproveReportRequest) -> StreamingResponse:
    return StreamingResponse(
        stream_agent_events(lambda event_sink: execute_improve_report(payload, event_sink=event_sink)),
        media_type="application/x-ndjson",
    )


def execute_improve_report(payload: ImproveReportRequest, event_sink=None) -> ReportResponse:
    logger.info(
        "improve_start assignment_id=%s requested_skill=%s top_k=%s current_chars=%s",
        payload.assignment_id,
        payload.skill_id,
        payload.top_k,
        len(payload.current_markdown),
    )
    collection = chroma_client().get_or_create_collection(
        name=collection_name(payload.assignment_id),
        metadata=collection_metadata(),
    )
    skill, routing = resolve_skill(payload)

    queries = build_search_queries(payload, skill)
    run: AgentRunResult = improve_report_agent(
        payload=payload,
        skill=skill,
        collection=collection,
        query=queries,
        current_markdown=payload.current_markdown,
        current_quality=payload.current_quality,
        embed_texts=embed_texts,
        parent_chunk_loader=lambda parent_ids: fetch_parent_chunks(payload.assignment_id, parent_ids),
        llm_client=llm_client,
        quality_llm_client=evaluator_client,
        evaluator_model=evaluator_model(),
        evaluator_mode=evaluator_mode(),
        normalize_markdown=normalize_markdown,
        logger=logger,
        event_sink=event_sink,
    )
    logger.info(
        "improve_done assignment_id=%s skill=%s retrieved=%s rewritten=%s reason=%s",
        payload.assignment_id,
        skill.id,
        len(run.retrieved_evidence),
        run.quality.rewrite_triggered,
        run.draft_version_reason,
    )
    return ReportResponse(
        assignment_id=payload.assignment_id,
        markdown=run.markdown.strip(),
        retrieved_chunks=len(run.retrieved_evidence),
        resolved_skill_id=skill.id,
        routing_mode=routing.mode,
        routing_confidence=routing.confidence,
        routing_reason=routing.reason,
        retrieved_evidence=run.retrieved_evidence,
        quality=run.quality,
        agent_trace=run.agent_trace,
        draft_version_reason=run.draft_version_reason,
    )
