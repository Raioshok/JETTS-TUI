"""Repository Markdown links must not depend on the removed docs website."""

from scripts.normalize_docs_links import DOCS, destination, normalize


def test_site_route_becomes_relative_markdown_link():
    source = DOCS / "getting-started" / "quickstart.md"
    assert destination(source, "/user-guide/tui#sessions") == "../user-guide/tui.md#sessions"


def test_removed_site_host_uses_local_document():
    source = DOCS / "getting-started" / "quickstart.md"
    assert destination(source, "https://github.com/Raioshok/JETTS-TUI/blob/main/docs/user-guide/tui.md") == "../user-guide/tui.md"


def test_unrelated_external_link_is_unchanged():
    source = DOCS / "getting-started" / "quickstart.md"
    assert destination(source, "https://github.com/Raioshok/JETTS-TUI") is None


def test_upstream_source_link_uses_renamed_local_package():
    source = DOCS / "user-guide" / "messaging" / "slack.md"
    target = "https://github.com/Raioshok/JETTS-TUI/blob/main/jettstui/commands.py#registry"
    assert destination(source, target) == "../../../jettstui/commands.py#registry"


def test_historical_upstream_issue_link_is_preserved():
    source = DOCS / "user-guide" / "messaging" / "slack.md"
    assert destination(source, "https://github.com/Raioshok/JETTS-TUI/issues/30768") is None


def test_docs_have_no_resolvable_or_unresolved_site_style_links():
    for source in DOCS.rglob("*.md"):
        changed, unresolved = normalize(source, fix=False)
        assert changed == 0, f"site-style links remain in {source.relative_to(DOCS)}"
        assert not unresolved, f"broken site-style links in {source.relative_to(DOCS)}: {unresolved}"
