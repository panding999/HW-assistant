from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


AUTO_SKILL = "AUTO"


class SkillSpec(BaseModel):
    id: str
    label: str
    description: str = ""
    entry: str = "SKILL.md"
    system_prompt: str
    query_hint: str
    output_requirements: list[str] = []
    required_sections: list[str]
    instructions: str = ""


def load_skills(skills_dir: Path | None = None) -> dict[str, SkillSpec]:
    directory = skills_dir or Path(__file__).resolve().parent / "skills"
    skills: dict[str, SkillSpec] = {}
    for path in sorted(directory.glob("*/skill.json")):
        skill = load_skill_file(path)
        add_skill(skills, skill)
    for path in sorted(directory.glob("*.json")):
        skill = load_skill_file(path)
        add_skill(skills, skill)
    if not skills:
        raise ValueError(f"No skill files found in {directory}")
    return skills


def load_skill_file(path: Path) -> SkillSpec:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    entry = data.get("entry", "SKILL.md")
    instructions_path = path.parent / entry
    if instructions_path.exists():
        data["instructions"] = instructions_path.read_text(encoding="utf-8")
    return SkillSpec(**data)


def add_skill(skills: dict[str, SkillSpec], skill: SkillSpec) -> None:
    if skill.id in skills:
        raise ValueError(f"Duplicate skill id: {skill.id}")
    skills[skill.id] = skill


SKILLS = load_skills()
VALID_SKILLS = set(SKILLS)
