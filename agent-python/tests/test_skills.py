import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from app.main import ReportRequest, build_prompt, resolve_skill, route_skill_by_rules
except ModuleNotFoundError as exc:
    raise unittest.SkipTest(f"optional agent dependency is not installed: {exc.name}") from exc


class SkillRoutingTests(unittest.TestCase):
    def test_rule_routes_paper_summary_with_high_confidence(self) -> None:
        route = route_skill_by_rules("论文阅读", "机器学习", "总结 paper 的创新点和实验结果")
        self.assertIsNotNone(route)
        self.assertEqual(route.resolved_skill_id, "paper_summary")
        self.assertEqual(route.mode, "known_skill")
        self.assertGreaterEqual(route.confidence, 0.7)

    def test_rule_routes_lab_report_with_high_confidence(self) -> None:
        route = route_skill_by_rules("图像分类实验", "计算机视觉", "实现 CNN 代码并分析实验结果")
        self.assertIsNotNone(route)
        self.assertEqual(route.resolved_skill_id, "lab_report")
        self.assertEqual(route.mode, "known_skill")

    def test_ambiguous_assignment_uses_dynamic_planner_when_router_fails(self) -> None:
        payload = ReportRequest(
            assignment_id=1,
            title="产品分析",
            description="根据资料完成产品分析和建议",
            skill_id="AUTO",
        )
        skill, routing = resolve_skill(payload)
        self.assertEqual(skill.id, "dynamic_planner")
        self.assertEqual(routing.mode, "dynamic_plan")

    def test_manual_skill_bypasses_auto(self) -> None:
        payload = ReportRequest(
            assignment_id=1,
            title="论文阅读",
            description="总结创新点",
            skill_id="lab_report",
        )
        skill, routing = resolve_skill(payload)
        self.assertEqual(skill.id, "lab_report")
        self.assertEqual(routing.confidence, 1.0)

    def test_prompt_contains_required_sections(self) -> None:
        payload = ReportRequest(assignment_id=1, title="论文阅读", skill_id="paper_summary")
        skill, _ = resolve_skill(payload)
        prompt = build_prompt(payload, skill, "material")
        self.assertIn("研究背景", prompt)
        self.assertIn("汇报提纲", prompt)


if __name__ == "__main__":
    unittest.main()
