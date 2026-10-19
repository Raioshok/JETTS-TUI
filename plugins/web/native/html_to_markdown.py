"""Readable-Markdown extraction from raw HTML, stdlib only.

Builds a light element tree with :mod:`html.parser`, picks the main content
region (``<main>`` / ``<article>`` / ``role=main``, else ``<body>`` minus page
chrome), and renders it as Markdown: headings, paragraphs, links, images,
lists, code blocks, quotes and simple tables.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin

_VOID = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})
# Never content, anywhere.
_DROP = frozenset({
    "script", "style", "noscript", "template", "svg", "canvas", "iframe",
    "object", "embed", "select", "button", "input", "textarea", "dialog", "head",
})
# Page chrome, dropped when we fall back to rendering the whole <body>.
_CHROME = frozenset({"nav", "header", "footer", "aside", "form"})
_CHROME_ROLES = frozenset({"navigation", "banner", "contentinfo", "complementary", "search"})
_BLOCK = frozenset({
    "p", "div", "section", "article", "main", "header", "footer", "nav", "aside",
    "figure", "figcaption", "details", "summary", "address", "dl", "dt", "dd",
    "body", "html", "center",
})
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: Dict[str, str], parent: Optional["_Node"]):
        self.tag = tag
        self.attrs = attrs
        self.children: List[Union["_Node", str]] = []
        self.parent = parent

    def text_len(self) -> int:
        total = 0
        for c in self.children:
            total += len(c.strip()) if isinstance(c, str) else c.text_len()
        return total

    def iter(self):
        yield self
        for c in self.children:
            if isinstance(c, _Node):
                yield from c.iter()


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {}, None)
        self.cur = self.root
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        # Implicitly close an open <p>/<li> when a sibling of the same kind starts.
        if tag in ("p", "li", "dt", "dd", "tr", "td", "th", "option"):
            node = self.cur
            while node is not self.root and node.tag not in ("ul", "ol", "table", "tbody", "thead", "dl"):
                if node.tag == tag:
                    self.cur = node.parent or self.root
                    break
                node = node.parent or self.root
        node = _Node(tag, attr_map, self.cur)
        self.cur.children.append(node)
        if tag not in _VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID and self.cur.tag == tag.lower():
            self.cur = self.cur.parent or self.root

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        node = self.cur
        while node is not self.root:
            if node.tag == tag:
                self.cur = node.parent or self.root
                return
            node = node.parent or self.root

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        self.cur.children.append(data)


def _hidden(node: _Node) -> bool:
    a = node.attrs
    return (
        "hidden" in a
        or a.get("aria-hidden") == "true"
        or bool(_HIDDEN_STYLE.search(a.get("style", "")))
    )


def _pick_content_root(root: _Node) -> Tuple[_Node, bool]:
    """Return ``(node, strip_chrome)`` for the region worth reading."""
    candidates = [
        n for n in root.iter()
        if n.tag in ("main", "article") or n.attrs.get("role") in ("main", "article")
    ]
    if candidates:
        best = max(candidates, key=lambda n: n.text_len())
        body = next((n for n in root.iter() if n.tag == "body"), root)
        # Ignore a tiny <article> teaser when the page body is much richer.
        if best.text_len() >= 0.25 * body.text_len() or best.text_len() > 2000:
            return best, False
    body = next((n for n in root.iter() if n.tag == "body"), root)
    return body, True


class _Renderer:
    def __init__(self, base_url: str, strip_chrome: bool):
        self.base_url = base_url
        self.strip_chrome = strip_chrome

    def _abs(self, href: str) -> str:
        href = href.strip()
        if not href or href.startswith(("javascript:", "data:", "#")):
            return ""
        try:
            return urljoin(self.base_url, href)
        except ValueError:
            return ""

    def inline(self, node: Union[_Node, str], pre: bool = False) -> str:
        if isinstance(node, str):
            return node if pre else re.sub(r"\s+", " ", node)
        tag = node.tag
        if tag in _DROP or _hidden(node):
            return ""
        if tag == "br":
            return "\n"
        if tag == "img":
            alt = re.sub(r"\s+", " ", node.attrs.get("alt", "")).strip()
            src = self._abs(node.attrs.get("src", ""))
            return f"![{alt}]({src})" if src and alt else ""
        inner = "".join(self.inline(c, pre) for c in node.children)
        if tag == "a":
            text = inner.strip()
            href = self._abs(node.attrs.get("href", ""))
            if not text:
                return ""
            return f"[{text}]({href})" if href else text
        if tag in ("strong", "b") and inner.strip():
            return f"**{inner.strip()}**"
        if tag in ("em", "i") and inner.strip():
            return f"*{inner.strip()}*"
        if tag == "code" and not pre and inner.strip():
            return f"`{inner.strip()}`"
        if tag in ("sub", "sup", "small", "span", "abbr", "time", "mark", "label", "font", "u", "s", "q", "cite"):
            return inner
        # A block element inside inline context: separate it.
        if tag in _BLOCK or tag in ("ul", "ol", "table", "pre", "blockquote") or re.match(r"h[1-6]$", tag):
            return "\n\n" + self.block(node).strip() + "\n\n"
        return inner

    def block(self, node: _Node, depth: int = 0) -> str:
        tag = node.tag
        if tag in _DROP or _hidden(node):
            return ""
        if self.strip_chrome and (tag in _CHROME or node.attrs.get("role") in _CHROME_ROLES):
            return ""
        m = re.match(r"h([1-6])$", tag)
        if m:
            text = self._flat(node)
            return f"\n\n{'#' * int(m.group(1))} {text}\n\n" if text else ""
        if tag == "pre":
            code = "".join(self.inline(c, pre=True) for c in node.children).strip("\n")
            return f"\n\n```\n{code}\n```\n\n" if code.strip() else ""
        if tag == "blockquote":
            inner = self._children(node, depth).strip()
            return "\n\n" + "\n".join("> " + line if line else ">" for line in inner.splitlines()) + "\n\n"
        if tag in ("ul", "ol"):
            return "\n\n" + self._list(node, depth) + "\n\n"
        if tag == "table":
            return "\n\n" + self._table(node) + "\n\n"
        if tag == "hr":
            return "\n\n---\n\n"
        if tag == "li":  # stray <li> outside a list
            return "\n- " + self._children(node, depth).strip() + "\n"
        if tag in _BLOCK or tag == "#root":
            return "\n\n" + self._children(node, depth) + "\n\n"
        return self.inline(node)

    def _children(self, node: _Node, depth: int) -> str:
        parts: List[str] = []
        for c in node.children:
            parts.append(self.inline(c) if isinstance(c, str) else self.block(c, depth))
        return "".join(parts)

    def _flat(self, node: _Node) -> str:
        return re.sub(r"\s+", " ", "".join(self.inline(c) for c in node.children)).strip()

    def _list(self, node: _Node, depth: int) -> str:
        ordered = node.tag == "ol"
        lines: List[str] = []
        n = 0
        for c in node.children:
            if not isinstance(c, _Node) or c.tag != "li" or _hidden(c):
                continue
            n += 1
            marker = f"{n}." if ordered else "-"
            text_parts: List[str] = []
            nested: List[str] = []
            for gc in c.children:
                if isinstance(gc, _Node) and gc.tag in ("ul", "ol"):
                    nested.append(self._list(gc, depth + 1))
                else:
                    text_parts.append(self.inline(gc) if isinstance(gc, str) else self.block(gc, depth + 1))
            text = re.sub(r"\s*\n\s*\n\s*", " ", "".join(text_parts)).strip()
            text = re.sub(r"[ \t]+", " ", text)
            if text or nested:
                lines.append("  " * depth + f"{marker} {text}")
                lines.extend(nested)
        return "\n".join(lines)

    def _table(self, node: _Node) -> str:
        rows: List[List[str]] = []
        for tr in node.iter():
            if tr.tag != "tr":
                continue
            cells = [self._flat(td).replace("|", "\\|") for td in tr.children
                     if isinstance(td, _Node) and td.tag in ("td", "th")]
            if any(cells):
                rows.append(cells)
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        out = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
        out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return "\n".join(out)


def html_to_markdown(html: str, base_url: str = "") -> Tuple[str, str]:
    """Convert an HTML document to ``(title, markdown)``."""
    builder = _TreeBuilder()
    try:
        builder.feed(html)
        builder.close()
    except Exception:  # malformed markup: keep whatever parsed
        pass
    base = base_url
    base_tag = next((n for n in builder.root.iter() if n.tag == "base" and n.attrs.get("href")), None)
    if base_tag is not None:
        base = urljoin(base_url, base_tag.attrs["href"])
    content, strip_chrome = _pick_content_root(builder.root)
    text = _Renderer(base, strip_chrome).block(content)
    # Normalise whitespace: trim lines, collapse blank runs.
    lines = [line.rstrip() for line in text.splitlines()]
    out: List[str] = []
    in_code = False
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
        if not in_code:
            line = re.sub(r"(?<=\S) {2,}", " ", line).lstrip() if not re.match(r"\s*([-*]|\d+\.) ", line) else line
        if not line.strip() and out and not out[-1].strip() and not in_code:
            continue
        out.append(line)
    title = re.sub(r"\s+", " ", builder.title).strip()
    return title, "\n".join(out).strip()
