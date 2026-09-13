#!/usr/bin/env python3
"""Parse official WWW accepted-paper listing HTML into TSV.

Handles the two markup shapes used by the 2024 and 2026 conference sites:

  2024  <div class="card-title"><strong>TITLE</strong></div>
        <p class="m-0 p-0">AUTHORS</p>
        (flat list, no track headings)

  2026  <h2>TRACK NAME</h2>
        <ul><li><span class="paper-id">(rfp0028)</span> TITLE —
        <span class="paper-authors">AUTHORS</span></li></ul>
        (grouped by track)

Usage:
    python parse_accepted_listings.py <input.html> <output.tsv>

Output columns: paper_id, track, title, authors
Track is empty for the 2024 flat listings.

This tool only reads local HTML snapshots; it performs no network access.
"""

import html
import re
import sys


def _clean(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("​", "")          # zero-width space used in 2026 titles
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_2026(source):
    """Grouped <h2> sections of <li> entries with paper-id spans."""
    rows = []
    # Split on track headings, keeping them in order with their bodies.
    parts = re.split(r"<h2[^>]*>(.*?)</h2>", source, flags=re.S)
    if len(parts) == 1:
        # Some listings (2026 Industry) have no <h2> track headings at all.
        parts = ["", "Industry", source]
    # parts[0] is the preamble before the first heading.
    for i in range(1, len(parts), 2):
        track = _clean(parts[i])
        body = parts[i + 1] if i + 1 < len(parts) else ""
        for item in re.findall(r"<li[^>]*>(.*?)</li>", body, flags=re.S):
            m_id = re.search(r'class="paper-id"[^>]*>\((.*?)\)<', item)
            m_authors = re.search(r'class="paper-authors"[^>]*>(.*?)</span>', item, flags=re.S)
            title_part = item
            if m_id:
                title_part = title_part.split("</span>", 1)[-1]
            if m_authors:
                title_part = title_part.split('<span class="paper-authors"', 1)[0]
            title = _clean(title_part).strip(" —-–")
            authors = _clean(m_authors.group(1)) if m_authors else ""
            if title:
                rows.append((m_id.group(1) if m_id else "", track, title, authors))
    return rows


def parse_2024(source):
    """Flat card-title / authors paragraphs."""
    rows = []
    pattern = re.compile(
        r'<div class="card-title">(.*?)</div>\s*<p class="m-0 p-0">(.*?)</p>',
        re.S,
    )
    for title_html, authors_html in pattern.findall(source):
        title = _clean(title_html)
        if title:
            rows.append(("", "", title, _clean(authors_html)))
    return rows


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    src_path, out_path = sys.argv[1], sys.argv[2]
    with open(src_path, encoding="utf-8", errors="replace") as fh:
        source = fh.read()
    source = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", source)

    rows = parse_2026(source)
    if not rows:
        rows = parse_2024(source)

    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("paper_id\ttrack\ttitle\tauthors\n")
        for r in rows:
            fh.write("\t".join(f.replace("\t", " ") for f in r) + "\n")
    print(f"{src_path} -> {out_path}: {len(rows)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
