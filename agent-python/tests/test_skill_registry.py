import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.skill_registry import SKILLS, load_skills


class SkillRegistryTests(unittest.TestCase):
    def test_registry_loads_directory_skills(self) -> None:
        skills = load_skills()
        self.assertIn("lab_report", skills)
        self.assertIn("paper_summary", skills)
        self.assertIn("course_qa_report", skills)
        self.assertIn("dynamic_planner", skills)

    def test_global_registry_uses_directory_skills(self) -> None:
        self.assertEqual(SKILLS["paper_summary"].label, "论文总结")


if __name__ == "__main__":
    unittest.main()
