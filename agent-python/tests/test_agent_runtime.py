import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_runtime import RetrievedEvidence, evaluate_quality, run_report_agent, should_rewrite


class FakeCollection:
    def query(self, query_embeddings, n_results, include):
        return {
            "ids": [["10-0"]],
            "documents": [["实验目的内容 实验步骤内容"]],
            "metadatas": [[{"material_id": 10, "filename": "实验要求.md"}]],
            "distances": [[0.25]],
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
        if "请改写" in prompt:
            return FakeResponse(
                "# 实验目的\n基于资料说明实验目标。[来源: 实验要求.md]\n\n"
                "# 实验步骤\n按资料完成环境、实现和验证步骤。[来源: 实验要求.md]"
            )
        return FakeResponse(
            "# 实验目的\n待补充。\n\n"
            "# 实验步骤\n基于资料说明。[来源: 实验要求.md]"
        )


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self):
        self.chat = FakeChat()


class FakePayload:
    assignment_id = 1
    top_k = 3


class FakeSkill:
    id = "lab_report"
    system_prompt = "system"
    required_sections = ["实验目的", "实验步骤"]


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
        self.assertTrue(should_rewrite("# 实验目的\n待补充。", quality, []))

    def test_no_evidence_short_draft_requests_user_input(self) -> None:
        quality = evaluate_quality(
            "# 实验目的\n待补充。",
            ["实验目的", "实验步骤"],
            [],
            rewrite_triggered=False,
        )
        self.assertEqual(quality.decision, "NEEDS_USER_INPUT")
        self.assertFalse(should_rewrite("# 实验目的\n待补充。", quality, []))


if __name__ == "__main__":
    unittest.main()
