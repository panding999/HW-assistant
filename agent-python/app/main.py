from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Iterable

import chromadb
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field
from pypdf import PdfReader


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
    top_k: int = Field(default=8, ge=1, le=20)


class ReportResponse(BaseModel):
    assignment_id: int
    markdown: str
    retrieved_chunks: int


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
    fenced = re.fullmatch(r"```(?:markdown|md)?\s*\n(?P<body>[\s\S]*?)\n```", text, re.IGNORECASE)
    if fenced:
        return fenced.group("body").strip()
    return text


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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

    query = "\n".join(
        part
        for part in [
            f"作业标题：{payload.title}",
            f"课程：{payload.course or ''}",
            f"作业说明：{payload.description or ''}",
            "请检索与实验目的、实验原理、实验步骤、代码分析和实验总结相关的内容。",
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

    prompt = f"""
你是高校实验报告助手。请严格基于给定资料生成一份中文 Markdown 实验报告草稿。

作业标题：{payload.title}
课程：{payload.course or "未提供"}
作业说明：{payload.description or "未提供"}

资料摘录：
{context_text or "没有检索到资料，请基于作业说明给出可编辑草稿，并标注需要补充资料的位置。"}

输出要求：
1. 使用 Markdown。
2. 必须包含以下一级或二级标题：实验目的、实验原理、实验步骤、核心代码分析、实验总结。
3. 不要编造具体实验数据；资料不足时写“待补充”。
4. 语气专业、简洁，方便学生继续编辑。
5. 直接输出 Markdown 正文，不要使用 ```markdown 或其他代码围栏包裹全文。
""".strip()

    response = llm_client().chat.completions.create(
        model=os.getenv("LLM_MODEL", "qwen-plus"),
        messages=[
            {"role": "system", "content": "你是严谨的高校实验报告写作助手。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    markdown = normalize_markdown(response.choices[0].message.content or "")
    return ReportResponse(
        assignment_id=payload.assignment_id,
        markdown=markdown.strip(),
        retrieved_chunks=len(contexts),
    )
