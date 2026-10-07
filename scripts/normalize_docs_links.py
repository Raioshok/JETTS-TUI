"""Convert links from the removed Docusaurus site to repository Markdown links.

Only links whose destination exists in ``docs/`` are rewritten. Unresolved
links are reported so a missing document cannot be silently invented.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MARKDOWN_LINK = re.compile(r"\]\((?P<target>[^\s)]+)(?P<suffix>\s+[^)]*)?\)")
LEGACY_HOSTS = {"jettstui.jettstui.dev", "www.jettstui.jettstui.dev"}
ROUTE_ALIASES = {"/reference/automation-blueprints-catalog": "/reference/automation-blueprints"}
UPSTREAM_SOURCE_PREFIXES = (
    "/jettstui/jettstui/blob/main/",
    "/jettstui/jettstui/tree/main/",
)


def _relative_target(source: Path, candidate: Path, fragment: str = "") -> str:
    relative = Path(os.path.relpath(candidate, source.parent)).as_posix()
    if not relative.startswith("."):
        relative = "./" + relative
    return relative + fragment


def destination(source: Path, target: str) -> str | None:
    parsed = urlsplit(target)
    if parsed.scheme == "https" and parsed.netloc == "github.com":
        for prefix in UPSTREAM_SOURCE_PREFIXES:
            if not parsed.path.startswith(prefix):
                continue
            repo_path = unquote(parsed.path[len(prefix):])
            if repo_path.startswith("jettstui/"):
                repo_path = "jettstui/" + repo_path[len("jettstui/"):]
            candidate = (ROOT / repo_path).resolve()
            if candidate.is_relative_to(ROOT.resolve()) and candidate.exists():
                suffix = ("?" + parsed.query if parsed.query else "") + ("#" + parsed.fragment if parsed.fragment else "")
                return _relative_target(source, candidate, suffix)
        return None
    if parsed.scheme and parsed.netloc not in LEGACY_HOSTS:
        return None
    if parsed.netloc in LEGACY_HOSTS:
        route = parsed.path
    elif target.startswith("/"):
        route = parsed.path
    else:
        return None
    if not route.startswith("/") or route.startswith("//"):
        return None
    if route.startswith("/docs/"):
        route = route[5:]
    route = ROUTE_ALIASES.get(route.rstrip("/"), route)
    if route.startswith("/img/"):
        candidate = DOCS / "assets" / route.lstrip("/")
        candidates = (candidate,)
    else:
        stem = DOCS / unquote(route.lstrip("/"))
        candidates = (stem.with_suffix(".md"), stem / "index.md", stem / "README.md")
    for candidate in candidates:
        if candidate.is_file():
            suffix = ("?" + parsed.query if parsed.query else "") + ("#" + parsed.fragment if parsed.fragment else "")
            return _relative_target(source, candidate, suffix)
    return None


def normalize(source: Path, *, fix: bool) -> tuple[int, list[str]]:
    original = source.read_text(encoding="utf-8")
    unresolved: list[str] = []
    changed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        target = match.group("target")
        replacement = destination(source, target)
        if replacement is None:
            if target.startswith("/") or "jettstui.jettstui.dev" in target:
                unresolved.append(target)
            return match.group(0)
        changed += 1
        return "](" + replacement + (match.group("suffix") or "") + ")"

    updated = MARKDOWN_LINK.sub(replace, original)
    if fix and updated != original:
        source.write_text(updated, encoding="utf-8", newline="")
    return changed, unresolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="rewrite resolvable links")
    args = parser.parse_args()
    changed = 0
    unresolved: list[str] = []
    for source in DOCS.rglob("*.md"):
        count, missing = normalize(source, fix=args.fix)
        changed += count
        unresolved.extend(f"{source.relative_to(ROOT)}: {target}" for target in missing)
    print(f"{'Rewrote' if args.fix else 'Found'} {changed} resolvable site-style links")
    print(f"{len(unresolved)} unresolved site-style links")
    for item in unresolved[:30]:
        print(item)
    return 0 if not unresolved else 1


if __name__ == "__main__":
    raise SystemExit(main())
