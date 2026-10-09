"""Installer fallback tiers must understand this package's declared extras."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("installer", ["install.sh", "install.ps1"])
def test_fallback_extra_parser_matches_project_all_extras(installer: str) -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    specs = metadata["project"]["optional-dependencies"]["all"]
    source = (ROOT / "scripts" / installer).read_text(encoding="utf-8")
    patterns = re.findall(r"m = re\.search\(r['\"]([^'\"]+)", source)
    patterns = [pattern for pattern in patterns if "\\[" in pattern and "\\]" in pattern]
    assert len(patterns) == 1, "expected one fallback-extra parser in the installer"

    actual = {match.group(1) for spec in specs if (match := re.search(patterns[0], spec))}
    expected = {
        spec.removeprefix(metadata["project"]["name"] + "[").removesuffix("]")
        for spec in specs
    }
    assert actual == expected
