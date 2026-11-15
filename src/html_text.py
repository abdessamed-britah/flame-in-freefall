"""Paragraphs of the main content of a web page, with the section heading above each.

Standard library only. Text is kept as written; only tags are removed and entities decoded,
and runs of whitespace inside a paragraph become one space (HTML does not preserve them).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

SKIP = {"script", "style", "nav", "footer", "aside", "form", "button", "figure", "figcaption", "noscript",
        "svg", "header", "select", "iframe"}
HEADINGS = {"h1", "h2", "h3", "h4"}
BLOCKS = {"p", "li", "blockquote"}
VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "area", "base", "col", "embed", "track"}


class _Main(HTMLParser):
    def __init__(self, root_tag: str):
        super().__init__(convert_charrefs=True)
        self.root_tag, self.depth, self.skip = root_tag, 0, 0
        # some sites wrap the whole page in <form> (and put the title in <header>): only skip them inside <main>
        self.skip_tags = SKIP if root_tag == "main" else SKIP - {"form", "header"}
        self.kind: str | None = None
        self.buf: list[str] = []
        self.heading = ""
        self.title = ""
        self.out: list[tuple[str, str]] = []  # (section heading, paragraph)

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            if tag == "br" and self.kind:
                self.buf.append(" ")
            return
        if tag == self.root_tag:
            self.depth += 1
            return
        if not self.depth:
            return
        if tag in self.skip_tags:
            self.skip += 1
        elif not self.skip and (tag in HEADINGS or tag in BLOCKS) and self.kind is None:
            self.kind, self.buf = tag, []

    def handle_endtag(self, tag):
        if tag == self.root_tag and self.depth:
            self.depth -= 1
            return
        if not self.depth:
            return
        if tag in self.skip_tags and self.skip:
            self.skip -= 1
        elif tag == self.kind:
            text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if tag in HEADINGS:
                if text:
                    self.heading = text
                    if tag == "h1" and not self.title:
                        self.title = text
            elif text:
                self.out.append((self.heading, text))
            self.kind = None

    def handle_data(self, data):
        if self.depth and not self.skip and self.kind:
            self.buf.append(data)


def paragraphs(html: str) -> tuple[str, list[tuple[str, str]]]:
    """(page title, [(section heading, paragraph), ...]) from <main>, or <body> if the page has no <main>."""
    for root in ("main", "body"):
        if f"<{root}" in html:
            p = _Main(root)
            p.feed(html)
            if p.out:
                m = re.search(r"<title>(.*?)</title>", html, re.S)
                return p.title or (m.group(1).strip() if m else ""), p.out
    return "", []
