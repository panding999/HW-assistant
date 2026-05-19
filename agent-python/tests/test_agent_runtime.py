import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_runtime import QualityMetrics, RetrievedEvidence, SearchQuery, calculate_citation_coverage, decide_quality, evaluate_quality, improve_report_agent, manual_review_reason_for, model_quality_score, quality_pass_score, run_report_agent, search_materials, should_rewrite


class FakeCollection:
    def query(self, query_embeddings, n_results, include):
        return {
            "ids": [["10-0"]],
            "documents": [["实验目的内容 实验步骤内容"]],
            "metadatas": [[{"material_id": 10, "filename": "实验要求.md"}]],
            "distances": [[0.25]],
        }


class MultiQueryCollection:
    def query(self, query_embeddings, n_results, include):
        self.query_count = len(query_embeddings)
        return {
            "ids": [["10-0", "10-1"], ["10-1", "11-0"], ["12-0"]],
            "documents": [["片段 A", "片段 B"], ["片段 B 更相关", "片段 C"], ["片段 D"]],
            "metadatas": [
                [{"material_id": 10, "filename": "a.md"}, {"material_id": 10, "filename": "a.md"}],
                [{"material_id": 10, "filename": "a.md"}, {"material_id": 11, "filename": "b.md"}],
                [{"material_id": 12, "filename": "c.md"}],
            ],
            "distances": [[0.4, 0.7], [0.1, 0.2], [0.3]],
        }


class HybridParentCollection:
    def query(self, query_embeddings, n_results, include):
        return {
            "ids": [["low-keyword", "high-vector"]],
            "documents": [["alpha beta keyword rich content", "unrelated content"]],
            "metadatas": [[
                {
                    "material_id": 10,
                    "filename": "requirements.md",
                    "section_title": "keyword section",
                    "parent_id": "10-p0",
                    "parent_excerpt": "parent context with alpha beta keyword rich details",
                    "section_summary": "section summary",
                    "document_summary": "document summary",
                    "document_outline": "1. keyword section",
                    "key_terms": "alpha beta keyword",
                },
                {
                    "material_id": 11,
                    "filename": "other.md",
                    "section_title": "other",
                    "parent_id": "11-p0",
                    "parent_excerpt": "other parent",
                },
            ]],
            "distances": [[0.9, 0.01]],
        }


class FakeChoice:
    def __init__(self, content):
        self.message = type("Message", (), {"content": content})()


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self):
        self.quality_calls = 0

    def create(self, **kwargs):
        prompt = kwargs["messages"][-1]["content"]
        if '"scores"' in prompt and "质量审稿器" in prompt:
            self.quality_calls += 1
            if self.quality_calls == 1:
                return FakeResponse(
                    json.dumps(
                        {
                            "scores": {
                                "structure": 1.0,
                                "grounding": 0.7,
                                "specificity": 0.4,
                                "readiness": 0.45,
                                "risk": 0.55,
                            },
                            "review_summary": "内容偏粗，需要改写成更具体的草稿。",
                            "issues": ["实现建议不够具体"],
                            "rewrite_focus": ["补充任务拆解和资料依据"],
                            "decision_hint": "NEEDS_REWRITE",
                        },
                        ensure_ascii=False,
                    )
                )
            return FakeResponse(
                json.dumps(
                    {
                        "scores": {
                            "structure": 1.0,
                            "grounding": 0.85,
                            "specificity": 0.86,
                            "readiness": 0.84,
                            "risk": 0.1,
                        },
                        "review_summary": "改写后结构和依据更完整。",
                        "issues": [],
                        "rewrite_focus": [],
                        "decision_hint": "PASS",
                    },
                    ensure_ascii=False,
                )
            )
        if "最小必要修补" in prompt:
            return FakeResponse(
                "# 实验目的\n基于资料说明实验目标。[来源: 实验要求.md]\n\n"
                "# 实验步骤\n按资料完成环境、实现和验证步骤。[来源: 实验要求.md]"
            )
        return FakeResponse(
            "# 实验目的\n基于资料说明。\n\n"
            "# 实验步骤\n基于资料说明。[来源: 实验要求.md]"
        )


class WorseRewriteCompletions:
    def __init__(self):
        self.quality_calls = 0

    def create(self, **kwargs):
        prompt = kwargs["messages"][-1]["content"]
        if '"scores"' in prompt and "质量审稿器" in prompt:
            self.quality_calls += 1
            if self.quality_calls == 1:
                return FakeResponse(
                    json.dumps(
                        {
                            "scores": {
                                "structure": 1.0,
                                "grounding": 0.9,
                                "specificity": 0.4,
                                "readiness": 0.45,
                                "risk": 0.65,
                            },
                            "total_score": 0.72,
                            "review_summary": "初稿可用但仍需增强。",
                            "issues": ["还需要补充依据"],
                            "rewrite_focus": ["补充证据"],
                            "decision_hint": "NEEDS_REWRITE",
                        },
                        ensure_ascii=False,
                    )
                )
            return FakeResponse(
                json.dumps(
                    {
                        "scores": {
                            "structure": 1.0,
                            "grounding": 0.5,
                            "specificity": 0.4,
                            "readiness": 0.45,
                            "risk": 0.65,
                        },
                        "total_score": 0.6,
                        "review_summary": "改写后质量下降。",
                        "issues": ["依据变弱"],
                        "rewrite_focus": ["恢复原始依据"],
                        "decision_hint": "NEEDS_REWRITE",
                    },
                    ensure_ascii=False,
                )
            )
        if "最小必要修补" in prompt:
            return FakeResponse("# 实验目的\n改写后内容变差。\n\n# 实验步骤\n缺少依据。")
        return FakeResponse(
            "# 实验目的\n初稿内容较完整。[来源: 实验要求.md]\n\n"
            "# 实验步骤\n初稿步骤有依据。[来源: 实验要求.md]"
        )


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self):
        self.chat = FakeChat()


class WorseRewriteChat:
    def __init__(self):
        self.completions = WorseRewriteCompletions()


class WorseRewriteClient:
    def __init__(self):
        self.chat = WorseRewriteChat()


class WorseImproveCompletions:
    def __init__(self):
        self.quality_calls = 0

    def create(self, **kwargs):
        prompt = kwargs["messages"][-1]["content"]
        if '"scores"' in prompt and "质量审稿器" in prompt:
            self.quality_calls += 1
            if self.quality_calls == 1:
                return FakeResponse(
                    json.dumps(
                        {
                            "scores": {
                                "structure": 1.0,
                                "grounding": 0.9,
                                "specificity": 0.8,
                                "readiness": 0.8,
                                "risk": 0.1,
                            },
                            "review_summary": "当前用户草稿质量较好。",
                            "issues": [],
                            "rewrite_focus": [],
                            "decision_hint": "PASS",
                        },
                        ensure_ascii=False,
                    )
                )
            return FakeResponse(
                json.dumps(
                    {
                        "scores": {
                            "structure": 1.0,
                            "grounding": 0.4,
                            "specificity": 0.35,
                            "readiness": 0.35,
                            "risk": 0.65,
                        },
                        "review_summary": "候选优化稿质量下降。",
                        "issues": ["证据变弱"],
                        "rewrite_focus": ["保留用户草稿依据"],
                        "decision_hint": "NEEDS_REWRITE",
                    },
                    ensure_ascii=False,
                )
            )
        if "基于当前草稿继续优化" in prompt:
            return FakeResponse("# 实验目的\n候选稿缺少依据。\n\n# 实验步骤\n候选稿不完整。")
        return FakeResponse("unused")


class WorseImproveChat:
    def __init__(self):
        self.completions = WorseImproveCompletions()


class WorseImproveClient:
    def __init__(self):
        self.chat = WorseImproveChat()


class BetterImproveCompletions:
    def __init__(self):
        self.quality_calls = 0

    def create(self, **kwargs):
        prompt = kwargs["messages"][-1]["content"]
        if '"scores"' in prompt and "质量审稿器" in prompt:
            self.quality_calls += 1
            if self.quality_calls == 1:
                return FakeResponse(
                    json.dumps(
                        {
                            "scores": {
                                "structure": 1.0,
                                "grounding": 0.55,
                                "specificity": 0.45,
                                "readiness": 0.45,
                                "risk": 0.45,
                            },
                            "review_summary": "当前用户草稿仍可增强。",
                            "issues": ["步骤偏粗"],
                            "rewrite_focus": ["补充资料依据"],
                            "decision_hint": "NEEDS_REWRITE",
                        },
                        ensure_ascii=False,
                    )
                )
            return FakeResponse(
                json.dumps(
                    {
                        "scores": {
                            "structure": 1.0,
                            "grounding": 0.9,
                            "specificity": 0.9,
                            "readiness": 0.88,
                            "risk": 0.08,
                        },
                        "review_summary": "候选优化稿质量更高。",
                        "issues": [],
                        "rewrite_focus": [],
                        "decision_hint": "PASS",
                    },
                    ensure_ascii=False,
                )
            )
        if "基于当前草稿继续优化" in prompt:
            return FakeResponse(
                "# 实验目的\n优化后补充了资料依据。[来源: 实验要求.md]\n\n"
                "# 实验步骤\n优化后步骤更完整。[来源: 实验要求.md]"
            )
        return FakeResponse("unused")


class BetterImproveChat:
    def __init__(self):
        self.completions = BetterImproveCompletions()


class BetterImproveClient:
    def __init__(self):
        self.chat = BetterImproveChat()


class RecordingCompletions:
    def __init__(self, label):
        self.label = label
        self.calls = []

    def create(self, **kwargs):
        prompt = kwargs["messages"][-1]["content"]
        self.calls.append({"model": kwargs.get("model"), "prompt": prompt, "label": self.label})
        if '"scores"' in prompt and "质量审稿器" in prompt:
            return FakeResponse(
                json.dumps(
                    {
                        "scores": {
                            "structure": 1.0,
                            "grounding": 0.9,
                            "specificity": 0.9,
                            "readiness": 0.86,
                            "risk": 0.08,
                        },
                        "review_summary": "独立审稿器认为该草稿可以作为高质量初稿继续编辑。",
                        "issues": [],
                        "rewrite_focus": [],
                        "decision_hint": "PASS",
                    },
                    ensure_ascii=False,
                )
            )
        return FakeResponse("# 实验目的\n生成稿。[来源: 实验要求.md]\n\n# 实验步骤\n生成稿。[来源: 实验要求.md]")


class RecordingChat:
    def __init__(self, completions):
        self.completions = completions


class RecordingClient:
    def __init__(self, completions):
        self.chat = RecordingChat(completions)


class FakePayload:
    assignment_id = 1
    top_k = 3


class FakeSkill:
    id = "lab_report"
    system_prompt = "system"
    required_sections = ["实验目的", "实验步骤"]


class FakeDynamicSkill(FakeSkill):
    id = "dynamic_planner"


class AgentRuntimeTests(unittest.TestCase):
    def test_quality_uses_model_scores_and_local_signals(self) -> None:
        quality = evaluate_quality(
            "# 实验目的\n内容。[来源: 实验要求.md]\n\n# 实验步骤\n内容。",
            ["实验目的", "实验步骤"],
            [
                RetrievedEvidence(
                    chunk_id="10-0",
                    material_id=10,
                    filename="实验要求.md",
                    excerpt="实验要求",
                )
            ],
            rewrite_triggered=False,
            llm_client=lambda: FakeClient(),
            skill=FakeSkill(),
            payload=FakePayload(),
        )
        self.assertEqual(quality.section_completeness, 1.0)
        self.assertGreater(quality.total_score, 0)
        self.assertIn(quality.decision, {"PASS", "NEEDS_REWRITE"})
        self.assertEqual(quality.retrieved_chunks, 1)

    def test_agent_loop_uses_independent_evaluator_client_for_quality(self) -> None:
        generator_calls = RecordingCompletions("generator")
        evaluator_calls = RecordingCompletions("evaluator")
        with patch.dict("os.environ", {"LLM_MODEL": "generator-model"}, clear=False):
            result = run_report_agent(
                payload=FakePayload(),
                skill=FakeSkill(),
                collection=FakeCollection(),
                query="query",
                embed_texts=lambda texts: [[0.1, 0.2]],
                llm_client=lambda: RecordingClient(generator_calls),
                quality_llm_client=lambda: RecordingClient(evaluator_calls),
                evaluator_model="evaluator-model",
                evaluator_mode="independent",
                build_prompt=lambda payload, skill, context: context,
                normalize_markdown=lambda text: text.strip(),
                logger=type("Logger", (), {"info": lambda *args, **kwargs: None})(),
            )

        self.assertEqual(generator_calls.calls[0]["model"], "generator-model")
        self.assertEqual(evaluator_calls.calls[0]["model"], "evaluator-model")
        self.assertEqual(result.quality.evaluator_model, "evaluator-model")
        self.assertEqual(result.quality.evaluator_mode, "independent")

    def test_quality_marks_default_evaluator_fallback_mode(self) -> None:
        quality = evaluate_quality(
            "# 实验目的\n内容。[来源: 实验要求.md]\n\n# 实验步骤\n内容。[来源: 实验要求.md]",
            ["实验目的", "实验步骤"],
            [
                RetrievedEvidence(
                    chunk_id="10-0",
                    material_id=10,
                    filename="实验要求.md",
                    excerpt="实验要求",
                )
            ],
            rewrite_triggered=False,
            llm_client=lambda: FakeClient(),
            skill=FakeSkill(),
            payload=FakePayload(),
            evaluator_model="deepseek-v4-flash",
            evaluator_mode="fallback",
        )

        self.assertEqual(quality.evaluator_model, "deepseek-v4-flash")
        self.assertEqual(quality.evaluator_mode, "fallback")

    def test_agent_loop_returns_evidence_quality_and_trace(self) -> None:
        client = FakeClient()
        result = run_report_agent(
            payload=FakePayload(),
            skill=FakeSkill(),
            collection=FakeCollection(),
            query="query",
            embed_texts=lambda texts: [[0.1, 0.2]],
            llm_client=lambda: client,
            build_prompt=lambda payload, skill, context: context,
            normalize_markdown=lambda text: text.strip(),
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None})(),
        )
        self.assertEqual(result.retrieved_evidence[0].chunk_id, "10-0")
        self.assertGreaterEqual(len(result.agent_trace), 4)
        self.assertLessEqual(len(result.agent_trace), 4)
        self.assertTrue(result.quality.rewrite_triggered)
        self.assertEqual(result.quality.decision, "PASS")
        self.assertTrue(all(step.duration_ms >= 1 for step in result.agent_trace))

    def test_multi_query_search_deduplicates_and_limits_results(self) -> None:
        collection = MultiQueryCollection()
        result = search_materials(
            collection,
            [
                SearchQuery(name="assignment_query", text="作业"),
                SearchQuery(name="skill_query", text="章节"),
                SearchQuery(name="section_query", text="要求"),
            ],
            top_k=3,
            embed_texts=lambda texts: [[0.1, 0.2] for _ in texts],
        )
        self.assertEqual(result.query_count, 3)
        self.assertEqual(result.raw_hits, 5)
        self.assertEqual(result.deduped_hits, 4)
        self.assertLessEqual(len(result.evidence), 3)
        self.assertEqual(len({item.chunk_id for item in result.evidence}), len(result.evidence))
        self.assertEqual(result.evidence[0].chunk_id, "10-1")

    def test_hybrid_search_prefers_keyword_match_and_returns_parent_context(self) -> None:
        result = search_materials(
            HybridParentCollection(),
            [SearchQuery(name="keyword_query", text="alpha beta keyword")],
            top_k=2,
            embed_texts=lambda texts: [[0.1, 0.2] for _ in texts],
        )
        self.assertEqual(result.parent_merged_hits, 2)
        self.assertEqual(result.evidence[0].chunk_id, "low-keyword")
        self.assertEqual(result.evidence[0].parent_id, "10-p0")
        self.assertEqual(result.evidence[0].section_title, "keyword section")
        self.assertGreater(result.evidence[0].keyword_score, result.evidence[1].keyword_score)
        self.assertIn("parent context", result.evidence[0].excerpt)

    def test_dynamic_planner_adds_plan_step_before_retrieval(self) -> None:
        client = FakeClient()
        result = run_report_agent(
            payload=FakePayload(),
            skill=FakeDynamicSkill(),
            collection=FakeCollection(),
            query=[SearchQuery(name="assignment_query", text="open task")],
            embed_texts=lambda texts: [[0.1, 0.2] for _ in texts],
            llm_client=lambda: client,
            build_prompt=lambda payload, skill, context, plan="": f"{plan}\n{context}",
            normalize_markdown=lambda text: text.strip(),
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None})(),
        )
        self.assertEqual(result.agent_trace[0].tool_name, "plan_report_outline")
        self.assertEqual(result.agent_trace[1].tool_name, "search_materials")
        self.assertIn("plan", result.agent_trace[0].details)

    def test_agent_loop_keeps_original_when_rewrite_scores_lower(self) -> None:
        client = WorseRewriteClient()
        result = run_report_agent(
            payload=FakePayload(),
            skill=FakeSkill(),
            collection=FakeCollection(),
            query="query",
            embed_texts=lambda texts: [[0.1, 0.2]],
            llm_client=lambda: client,
            build_prompt=lambda payload, skill, context: context,
            normalize_markdown=lambda text: text.strip(),
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None})(),
        )
        self.assertIn("初稿内容较完整", result.markdown)
        self.assertEqual(result.quality.total_score, 0.675)
        self.assertTrue(result.quality.rewrite_triggered)
        self.assertIn("已保留初稿", result.draft_version_reason)
        self.assertIn("accepted_rewrite=false", result.agent_trace[-1].output_summary)

    def test_improve_report_keeps_current_draft_when_candidate_scores_lower(self) -> None:
        client = WorseImproveClient()
        current_markdown = (
            "# 实验目的\n用户已补充完整依据。[来源: 实验要求.md]\n\n"
            "# 实验步骤\n用户已写清楚步骤。[来源: 实验要求.md]"
        )
        result = improve_report_agent(
            payload=FakePayload(),
            skill=FakeSkill(),
            collection=FakeCollection(),
            query="query",
            current_markdown=current_markdown,
            embed_texts=lambda texts: [[0.1, 0.2]],
            llm_client=lambda: client,
            normalize_markdown=lambda text: text.strip(),
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None})(),
        )

        self.assertEqual(result.markdown, current_markdown)
        self.assertIn("未采纳", result.draft_version_reason)
        self.assertIn("accepted_improvement=false", result.agent_trace[-1].output_summary)

    def test_improve_report_accepts_candidate_when_score_is_higher(self) -> None:
        client = BetterImproveClient()
        result = improve_report_agent(
            payload=FakePayload(),
            skill=FakeSkill(),
            collection=FakeCollection(),
            query="query",
            current_markdown="# 实验目的\n当前较粗。[来源: 实验要求.md]\n\n# 实验步骤\n当前较粗。",
            embed_texts=lambda texts: [[0.1, 0.2]],
            llm_client=lambda: client,
            normalize_markdown=lambda text: text.strip(),
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None})(),
        )

        self.assertIn("优化后补充了资料依据", result.markdown)
        self.assertIn("已采纳", result.draft_version_reason)
        self.assertIn("accepted_improvement=true", result.agent_trace[-1].output_summary)

    def test_should_rewrite_weak_draft_with_fallback_quality(self) -> None:
        quality = evaluate_quality(
            "# 实验目的\n待补充。",
            ["实验目的", "实验步骤"],
            [
                RetrievedEvidence(
                    chunk_id="10-0",
                    material_id=10,
                    filename="实验要求.md",
                    excerpt="实验要求",
                )
            ],
            rewrite_triggered=False,
        )
        self.assertFalse(should_rewrite("# 实验目的\n待补充。", quality, []))

    def test_no_evidence_short_draft_requests_user_input(self) -> None:
        quality = evaluate_quality(
            "# 实验目的\n待补充。",
            ["实验目的", "实验步骤"],
            [],
            rewrite_triggered=False,
        )
        self.assertEqual(quality.decision, "NEEDS_USER_INPUT")
        self.assertFalse(should_rewrite("# 实验目的\n待补充。", quality, []))

    def test_score_above_threshold_passes_even_when_model_suggests_rewrite(self) -> None:
        decision = decide_quality(
            markdown="# 实验目的\n内容完整。\n\n# 实验步骤\n内容完整。",
            evidence=[
                RetrievedEvidence(
                    chunk_id="10-0",
                    material_id=10,
                    filename="实验要求.md",
                    excerpt="实验要求",
                )
            ],
            section_completeness=1.0,
            total_score=0.84,
            pass_score=0.78,
            decision_hint="NEEDS_REWRITE",
        )
        self.assertEqual(decision, "PASS")

    def test_weak_marker_requires_manual_review_even_when_score_passes(self) -> None:
        markdown = "# 实验目的\n内容完整。\n\n# 实验步骤\nTODO"
        decision = decide_quality(
            markdown=markdown,
            evidence=[
                RetrievedEvidence(
                    chunk_id="10-0",
                    material_id=10,
                    filename="实验要求.md",
                    excerpt="实验要求",
                )
            ],
            section_completeness=1.0,
            total_score=0.9,
            pass_score=0.75,
            decision_hint="PASS",
            manual_review_reason=manual_review_reason_for(markdown),
        )
        self.assertEqual(decision, "NEEDS_REWRITE")
        self.assertIn("TODO", manual_review_reason_for(markdown))

    def test_pending_info_heading_alone_does_not_require_manual_review(self) -> None:
        markdown = "# 待补充信息\n本节概括后续可以扩展的方向，但不包含占位符。"
        self.assertEqual(manual_review_reason_for(markdown), "")

    def test_manual_review_marker_above_threshold_does_not_auto_rewrite(self) -> None:
        quality = QualityMetrics(
            section_completeness=1.0,
            citation_coverage=1.0,
            retrieved_chunks=1,
            rewrite_triggered=False,
            total_score=0.76,
            pass_score=0.75,
            decision="NEEDS_REWRITE",
            manual_review_reason="草稿包含待补充、资料不足或 TODO 等未完成标记",
            quality_note="模型评分 76%，需人工审核。",
        )
        self.assertFalse(should_rewrite("# 待补充信息\n列出后续需要用户确认的内容。", quality, []))

    def test_citation_coverage_requires_explicit_source_marker(self) -> None:
        evidence = [
            RetrievedEvidence(chunk_id="10-0", material_id=10, filename="实验要求.pdf", excerpt="实验二"),
            RetrievedEvidence(chunk_id="11-0", material_id=11, filename="课程 资料.md", excerpt="要求"),
        ]
        markdown = "实验要求不是引用正文。\n\n结论来自资料。[来源: 课程 资料.md#11-0]"
        self.assertEqual(calculate_citation_coverage(markdown, evidence), 0.5)

    def test_citation_coverage_accepts_chunk_id_marker(self) -> None:
        evidence = [
            RetrievedEvidence(chunk_id="10-0", material_id=10, filename="实验要求.pdf", excerpt="实验二"),
        ]
        self.assertEqual(calculate_citation_coverage("结论。[chunk_id: 10-0 | source: 实验要求.pdf]", evidence), 1.0)

    def test_quality_pass_score_default_matches_env_example(self) -> None:
        self.assertEqual(quality_pass_score(), 0.85)

    def test_model_total_score_is_recomputed_from_dimensions(self) -> None:
        review = type(
            "Review",
            (),
            {
                "total_score": 0.99,
                "structure_score": 1.0,
                "grounding_score": 1.0,
                "specificity_score": 1.0,
                "readiness_score": 1.0,
                "risk_score": 1.0,
            },
        )()
        self.assertAlmostEqual(model_quality_score(review), 0.85)


if __name__ == "__main__":
    unittest.main()
