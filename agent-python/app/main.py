from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Iterable

import chromadb
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field
from pypdf import PdfReader

from app.skill_registry import AUTO_SKILL, SKILLS, VALID_SKILLS, SkillSpec


ROUTING_THRESHOLD = 0.7
DYNAMIC_PLANNER_SKILL = "dynamic_planner"


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


class ReportRequest(BaseModel):
    assignment_id: int
    title: str
    course: str | None = None
    description: str | None = None
    skill_id: str | None = Field(default=AUTO_SKILL)
    top_k: int = Field(default=8, ge=1, le=20)


class ReportResponse(BaseModel):
    assignment_id: int
    markdown: str
    retrieved_chunks: int
    resolved_skill_id: str
    routing_mode: str
    routing_confidence: float
    routing_reason: str


class RoutingResult(BaseModel):
    mode: str
    resolved_skill_id: str
    confidence: float = Field(ge=0, le=1)
    reason: str


app = FastAPI(title="FZU Homework Agent", version="0.1.0")


def get_api_key() -> str:
    provider = os.getenv("LLM_PROVIDER", "qwen").lower()
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "")
    else:
        key = os.getenv("DASHSCOPE_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise HTTPException(
            status_code=500,
            detail="Missing model API key. Set DASHSCOPE_API_KEY or OPENAI_API_KEY.",
        )
    return key


def llm_client() -> OpenAI:
    return OpenAI(
        api_key=get_api_key(),
        base_url=os.getenv(
            "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
    )


def chroma_client() -> chromadb.HttpClient:
    return chromadb.HttpClient(
        host=os.getenv("CHROMA_HOST", "localhost"),
        port=int(os.getenv("CHROMA_PORT", "8000")),
    )


def collection_name(assignment_id: int) -> str:
    return f"assignment_{assignment_id}"


def read_material_text(material: MaterialRef) -> str:
    path = Path(material.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Material not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

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


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    text_list = list(texts)
    if not text_list:
        return []

    embeddings: list[list[float]] = []
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-v2")
    client = llm_client()
    batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "25"))
    for start in range(0, len(text_list), batch_size):
        batch = text_list[start : start + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        embeddings.extend(item.embedding for item in response.data)
    return embeddings


def normalize_markdown(markdown: str) -> str:
    text = markdown.strip()
    fenced = re.fullmatch(
        r"```(?:markdown|md)?\s*\n(?P<body>[\s\S]*?)\n```",
        text,
        re.IGNORECASE,
    )
    if fenced:
        return fenced.group("body").strip()
    return text


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
            reason=f"Rule router matched {best_score} keyword(s) for {best_skill}.",
        )
    return RoutingResult(
        mode="dynamic_plan",
        resolved_skill_id=DYNAMIC_PLANNER_SKILL,
        confidence=confidence,
        reason=f"Rule router weakly matched {best_skill}; confidence below threshold.",
    )


def route_skill_with_llm(title: str, course: str | None, description: str | None) -> RoutingResult:
    prompt = f"""
Choose the best generation strategy for this assignment.
Return a strict JSON object with keys: mode, resolved_skill_id, confidence, reason.

Allowed known skill ids:
- lab_report: lab report, programming experiment, algorithm implementation, result analysis
- paper_summary: paper reading, literature summary, contribution analysis, paper presentation
- course_qa_report: answer course-material questions, explain course content, presentation report

If none of the known skills fits confidently, return:
{{"mode":"dynamic_plan","resolved_skill_id":"dynamic_planner","confidence":0.4,"reason":"..."}}

Rules:
- Use mode "known_skill" only when confidence is at least 0.7.
- Use mode "dynamic_plan" when the task is open-ended, mixed, unclear, or not covered by known skills.
- confidence must be a number from 0 to 1.

Title: {title}
Course: {course or "not provided"}
Description: {description or "not provided"}
""".strip()
    try:
        response = llm_client().chat.completions.create(
            model=os.getenv("LLM_MODEL", "qwen-plus"),
            messages=[
                {"role": "system", "content": "You are a strict assignment skill router."},
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
            reason = str(data.get("reason", "LLM router produced a routing decision."))
            if skill_id not in VALID_SKILLS or skill_id == DYNAMIC_PLANNER_SKILL or confidence < ROUTING_THRESHOLD:
                return RoutingResult(
                    mode="dynamic_plan",
                    resolved_skill_id=DYNAMIC_PLANNER_SKILL,
                    confidence=confidence,
                    reason=reason,
                )
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
                reason="LLM router returned a known skill id without JSON.",
            )
    except Exception:
        pass

    return RoutingResult(
        mode="dynamic_plan",
        resolved_skill_id=DYNAMIC_PLANNER_SKILL,
        confidence=0.0,
        reason="LLM router failed; falling back to dynamic planning.",
    )


def resolve_skill(payload: ReportRequest) -> tuple[SkillSpec, RoutingResult]:
    requested = normalize_skill_id(payload.skill_id)
    if requested != AUTO_SKILL:
        return SKILLS[requested], RoutingResult(
            mode="known_skill",
            resolved_skill_id=requested,
            confidence=1.0,
            reason="User manually selected this skill.",
        )

    rule_result = route_skill_by_rules(payload.title, payload.course, payload.description)
    if rule_result and rule_result.mode == "known_skill":
        return SKILLS[rule_result.resolved_skill_id], rule_result

    llm_result = route_skill_with_llm(payload.title, payload.course, payload.description)
    if llm_result.mode == "known_skill" and llm_result.confidence >= ROUTING_THRESHOLD:
        return SKILLS[llm_result.resolved_skill_id], llm_result

    dynamic_result = RoutingResult(
        mode="dynamic_plan",
        resolved_skill_id=DYNAMIC_PLANNER_SKILL,
        confidence=max(rule_result.confidence if rule_result else 0.0, llm_result.confidence),
        reason=(
            llm_result.reason
            if llm_result.confidence > 0
            else (rule_result.reason if rule_result else "No known skill matched confidently.")
        ),
    )
    return SKILLS[DYNAMIC_PLANNER_SKILL], dynamic_result


def build_prompt(payload: ReportRequest, skill: SkillSpec, context_text: str) -> str:
    sections = ", ".join(skill.required_sections)
    dynamic_note = ""
    if skill.id == DYNAMIC_PLANNER_SKILL:
        dynamic_note = """
Dynamic planning workflow:
1. Analyze the assignment goal.
2. Propose an appropriate report structure.
3. Use the retrieved evidence to fill the structure.
4. Mark missing evidence explicitly.
""".strip()

    return f"""
Write a Chinese Markdown draft for the current assignment using the selected skill: {skill.label}.
Strictly ground the answer in the provided material excerpts.

Assignment title: {payload.title}
Course: {payload.course or "not provided"}
Assignment instructions or questions: {payload.description or "not provided"}

Material excerpts:
{context_text or "No relevant material was retrieved. Produce an editable draft from the assignment instructions and mark missing evidence as pending."}

Required or suggested sections: {sections}

Skill instructions:
{skill.instructions or "Follow the skill metadata and required sections."}

{dynamic_note}

Additional output requirements:
- Output Markdown body only. Do not wrap the whole answer in a code fence.
- If evidence is missing, mark it clearly instead of inventing details.
""".strip()


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
    collection = chroma_client().get_or_create_collection(
        name=collection_name(payload.assignment_id)
    )

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str | int]] = []

    for material in payload.materials:
        text = read_material_text(material)
        for index, chunk in enumerate(chunk_text(text)):
            ids.append(f"{material.id}-{index}")
            documents.append(chunk)
            metadatas.append(
                {
                    "assignment_id": payload.assignment_id,
                    "material_id": material.id,
                    "filename": material.filename,
                }
            )

    if not documents:
        return IndexResponse(assignment_id=payload.assignment_id, chunks_indexed=0)

    embeddings = embed_texts(documents)
    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    return IndexResponse(
        assignment_id=payload.assignment_id, chunks_indexed=len(documents)
    )


@app.post("/agent/generate-report", response_model=ReportResponse)
def generate_report(payload: ReportRequest) -> ReportResponse:
    collection = chroma_client().get_or_create_collection(
        name=collection_name(payload.assignment_id)
    )
    skill, routing = resolve_skill(payload)

    query = "\n".join(
        part
        for part in [
            f"Assignment title: {payload.title}",
            f"Course: {payload.course or ''}",
            f"Description: {payload.description or ''}",
            skill.query_hint,
        ]
        if part.strip()
    )
    query_embedding = embed_texts([query])[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=payload.top_k,
    )
    contexts = results.get("documents", [[]])[0] if results else []
    context_text = "\n\n---\n\n".join(contexts)

    response = llm_client().chat.completions.create(
        model=os.getenv("LLM_MODEL", "qwen-plus"),
        messages=[
            {"role": "system", "content": skill.system_prompt},
            {"role": "user", "content": build_prompt(payload, skill, context_text)},
        ],
        temperature=0.3,
    )
    markdown = normalize_markdown(response.choices[0].message.content or "")
    return ReportResponse(
        assignment_id=payload.assignment_id,
        markdown=markdown.strip(),
        retrieved_chunks=len(contexts),
        resolved_skill_id=skill.id,
        routing_mode=routing.mode,
        routing_confidence=routing.confidence,
        routing_reason=routing.reason,
    )
