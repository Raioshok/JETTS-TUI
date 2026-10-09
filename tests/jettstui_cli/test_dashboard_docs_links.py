"""The dashboard channel catalog must link to shipped Markdown guides."""

from pathlib import Path
from urllib.parse import urlparse

from jettstui.web_server import _PLATFORM_OVERRIDES


def test_channel_docs_links_point_to_existing_repository_guides():
    docs_root = Path(__file__).resolve().parents[2] / "docs"
    github_prefix = "/Raioshok/JETTS-TUI/blob/main/docs/"

    for platform, details in _PLATFORM_OVERRIDES.items():
        url = details.get("docs_url", "")
        assert "jettstui.jettstui.dev" not in url, platform
        if not url.startswith("https://github.com/Raioshok/JETTS-TUI/"):
            continue  # External platform documentation is intentionally linked.
        path = urlparse(url).path
        assert path.startswith(github_prefix), (platform, url)
        guide = docs_root / path.removeprefix(github_prefix)
        assert guide.is_file(), (platform, guide)
