"""Tests for the compact banner's skill count across terminal widths."""

import os
from unittest.mock import patch

from rich.console import Console

import freeide_cli.banner as banner
import model_tools
import tools.mcp_tool


def _build_banner_with_skills(skills_by_category, term_width=160):
    """Helper: build banner with given skills and return captured output."""
    with (
        patch.object(
            model_tools,
            "check_tool_availability",
            return_value=([], []),
        ),
        patch.object(banner, "get_available_skills", return_value=skills_by_category),
        patch.object(banner, "get_update_result", return_value=None),
        patch.object(tools.mcp_tool, "get_mcp_status", return_value=[]),
        patch("freeide_cli.skin_engine.get_active_skin", return_value=None),
        patch("shutil.get_terminal_size", return_value=os.terminal_size((term_width, 50))),
    ):
        console = Console(
            record=True, force_terminal=False, color_system=None, width=term_width
        )
        banner.build_welcome_banner(
            console=console,
            model="anthropic/test-model",
            cwd="/tmp/project",
            tools=[],
        )
        return console.export_text()


def test_wide_terminal_counts_skills_without_listing_them():
    skills = {"research": [f"skill-{i:02d}" for i in range(15)]}
    text = _build_banner_with_skills(skills, term_width=200)
    assert "15 skills" in text
    assert "skill-08" not in text


def test_narrow_terminal_keeps_skill_count():
    skills = {"research": [f"skill-{i:02d}" for i in range(15)]}
    text = _build_banner_with_skills(skills, term_width=80)
    assert "15 skills" in text
    assert "skill-00" not in text


def test_small_category_counts_skills():
    skills = {"security": ["auth", "vault"]}
    text = _build_banner_with_skills(skills, term_width=80)
    assert "2 skills" in text
    assert "vault" not in text


def test_category_label_does_not_change_count():
    skills = {"very-long-category-name": [f"skill-{i:02d}" for i in range(10)]}
    text = _build_banner_with_skills(skills, term_width=120)
    assert "10 skills" in text
    assert "very-long-category-name" not in text
