"""Helpers for loading and filling prompt templates."""

from __future__ import annotations

from pathlib import Path
from string import Template


PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(name: str, **variables) -> str:
    """
    Load a .txt prompt template from shared/prompts/ and fill placeholders.

    Example:
        text = load_prompt("summarize", topic="thermodynamics", length="3 sentences")
    """
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    template = Template(path.read_text())
    return template.safe_substitute(**variables)
