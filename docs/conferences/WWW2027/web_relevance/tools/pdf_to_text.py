#!/usr/bin/env python3
"""Convert a two-column academic PDF to UTF-8 text with paragraphs and page markers.

The WWW proceedings are typeset in two columns. Naive extraction interleaves
the columns, and PDF "blocks" in these files often correspond to individual
lines rather than paragraphs, so both reading order and paragraph boundaries
have to be reconstructed geometrically:

  * reading order  - lines are assigned to the left or right column by their
    horizontal centre; full-width lines (title, section spans) are emitted by
    vertical position, headers first and footers last.
  * paragraphs     - a line starts a new paragraph when it is indented relative
    to its column's left margin, or when a vertical gap larger than normal
    leading separates it from the previous line. At a column or page change the
    paragraph continues unless the previous line ended a sentence.

Usage:
    python pdf_to_text.py <input.pdf> <output.txt> [--single-column]

Output: paragraphs separated by a blank line, each page prefixed with a
`<<<PDFPAGE n>>>` marker so any passage can be traced to a physical page.
A JSON QA report goes to stdout.

Residual noise: on some arXiv layouts, figure axis labels survive as short
lines spliced into the prose. Excluding figure bounding boxes was tried and
made results worse (the labels sit outside the plot rectangle), so the
narrow-line-run filter above is used instead, and `extract_intro.py` applies a
second, pattern-based pass.

Requires PyMuPDF (`import fitz`).
"""

import argparse
import json
import re
import sys
from collections import Counter

import fitz

SENTENCE_END = (".", "?", "!", ":", ";")
# A hyphen at end of line is a soft break if the next line starts lower-case.
SOFT_HYPHEN = re.compile(r"(\w)-$")


def _lines(page):
    """Return line records with geometry for one page."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for ln in block.get("lines", []):
            text = "".join(sp["text"] for sp in ln["spans"]).strip()
            if not text:
                continue
            x0, y0, x1, y1 = ln["bbox"]
            size = max((sp["size"] for sp in ln["spans"]), default=10.0)
            out.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                        "text": text, "size": size})
    return out


def _reading_order(lines, page_width, single_column):
    """Assign each line to a column and return them in reading order."""
    if single_column:
        return [dict(ln, col=0) for ln in sorted(lines, key=lambda l: l["y0"])]

    mid = page_width / 2.0
    full, left, right = [], [], []
    for ln in lines:
        width = ln["x1"] - ln["x0"]
        centre = (ln["x0"] + ln["x1"]) / 2.0
        if width > page_width * 0.62:
            full.append(dict(ln, col=-1))
        elif centre < mid:
            left.append(dict(ln, col=0))
        else:
            right.append(dict(ln, col=1))
    left.sort(key=lambda l: l["y0"])
    right.sort(key=lambda l: l["y0"])
    full.sort(key=lambda l: l["y0"])
    return full + left + right


def _join(a, b):
    """Join two lines, repairing soft hyphenation."""
    if SOFT_HYPHEN.search(a) and b[:1].islower():
        return a[:-1] + b
    return a + " " + b


NUMBERED_HEAD = re.compile(r"^\d{1,2}(?:\.\d{1,2})?\.?\s+[A-Z]")


def _is_heading(text):
    """Section heading: a short ALL-CAPS line, or a numbered section line.

    Font size is deliberately NOT used. On the first page the author names and
    affiliations are set larger than the body text, so a size threshold marks
    every author line as a heading.
    """
    t = text.strip()
    if not t or len(t) > 80 or t.endswith(SENTENCE_END):
        return False
    words = t.split()
    if len(words) > 8:
        return False
    if t.isupper() and 4 <= len(t) <= 60:
        return True
    return bool(NUMBERED_HEAD.match(t))


BARE_NUM = re.compile(r"^\d{1,2}$")


def _looks_like_title(s):
    """Short Title Case line — the second line of a two-line heading."""
    s = s.strip()
    if not (3 <= len(s) <= 60) or s.endswith(SENTENCE_END):
        return False
    if not s[:1].isupper() or len(s.split()) > 6:
        return False
    return sum(c.isalpha() for c in s) > len(s) * 0.5


def _heading_flags(ordered):
    """Per-line flags marking lines that belong to a section heading.

    The ACM template writes headings in two shapes:

        "2" / "MOTIVATION"      and      "1" / "Introduction"

    Only the first is caught by `_is_heading` alone; both halves of either
    shape are flagged here so the table filter never eats a heading.
    """
    flags = [False] * len(ordered)
    for i, ln in enumerate(ordered):
        if _is_heading(ln["text"]):
            flags[i] = True
        elif (BARE_NUM.match(ln["text"].strip()) and i + 1 < len(ordered)
              and _looks_like_title(ordered[i + 1]["text"])):
            flags[i] = True
            flags[i + 1] = True
    return flags


def _drop_table_rows(ordered_pages):
    """Remove runs of narrow lines, which are table cells or axis labels.

    Prose lines span most of their column. A paragraph's final line is short
    too, but it is a run of length one directly after a wide line, so only
    runs of two or more consecutive narrow lines are discarded.
    """
    widths = [ln["x1"] - ln["x0"] for _, o in ordered_pages
              for ln in o if ln["col"] != -1]
    if not widths:
        return ordered_pages
    widths.sort()
    column_width = widths[int(len(widths) * 0.9)]
    narrow_limit = 0.5 * column_width

    out = []
    for pno, ordered in ordered_pages:
        keep = [True] * len(ordered)
        flags = _heading_flags(ordered)

        def _narrow(ln, idx):
            return (ln["col"] != -1
                    and (ln["x1"] - ln["x0"]) < narrow_limit
                    and not flags[idx])

        i = 0
        while i < len(ordered):
            if _narrow(ordered[i], i):
                j = i
                while j < len(ordered) and _narrow(ordered[j], j):
                    j += 1
                if j - i >= 2:
                    for k in range(i, j):
                        keep[k] = False
                i = j
            else:
                i += 1
        out.append((pno, [ln for ln, k in zip(ordered, keep) if k]))
    return out


def build_paragraphs(pages, single_column=False):
    """Return a list of (page_number, paragraph_text)."""
    ordered_pages = []
    for pno, page in pages:
        ordered_pages.append((pno, _reading_order(
            _lines(page), page.rect.width, single_column)))
    ordered_pages = _drop_table_rows(ordered_pages)

    # Column margins are computed over the whole document: page 1 alone is
    # dominated by the title/author block and gives an unreliable margin.
    margin = {}
    for col in (0, 1):
        xs = [round(ln["x0"]) for _, o in ordered_pages for ln in o if ln["col"] == col]
        if xs:
            margin[col] = float(Counter(xs).most_common(1)[0][0])

    # Normal leading, measured from the document itself. Fixed thresholds
    # mis-split: journals differ in leading, and an over-tight gap threshold
    # turns every line into its own paragraph.
    gaps = []
    for _, ordered in ordered_pages:
        prev = None
        for ln in ordered:
            if prev is not None and ln["col"] == prev["col"] and ln["col"] != -1:
                g = ln["y0"] - prev["y1"]
                if 0 < g < 3 * ln["size"]:
                    gaps.append(g)
            prev = ln
    gaps.sort()
    leading = gaps[len(gaps) // 2] if gaps else 2.0

    paragraphs = []
    buf, buf_page, prev = "", None, None

    for pno, ordered in ordered_pages:
        prev_col = None
        for ln in ordered:
            text, col = ln["text"], ln["col"]

            # Headings stand alone: flush whatever is buffered, emit, continue.
            if _is_heading(text):
                if buf:
                    paragraphs.append((buf_page, buf))
                    buf = ""
                paragraphs.append((pno, text))
                prev, prev_col = ln, col
                continue

            if buf:
                gap = ln["y0"] - prev["y1"]
                new_col = col != prev_col
                gap_break = gap > max(1.5 * leading, 0.6 * ln["size"])
                if col == -1 or prev_col == -1:
                    # Full-width lines (title, running heads, wide figures) do
                    # not by themselves end a paragraph.
                    start_new = gap_break
                else:
                    # A first line is indented ~1em relative to the column margin.
                    indented = ln["x0"] - margin.get(col, 0.0) > 0.7 * ln["size"]
                    start_new = (indented or gap_break
                                 or (new_col and prev["text"].endswith(SENTENCE_END)))
                if start_new:
                    paragraphs.append((buf_page, buf))
                    buf = ""

            if not buf:
                buf_page = pno
                buf = text
            else:
                # `_join` repairs soft hyphenation at the line break.
                buf = _join(buf, text)
            prev, prev_col = ln, col

    if buf:
        paragraphs.append((buf_page, buf))
    return paragraphs


def convert(pdf_path, single_column=False):
    doc = fitz.open(pdf_path)
    pages = [(i + 1, doc[i]) for i in range(doc.page_count)]
    paragraphs = build_paragraphs(pages, single_column)

    chunks, last_page = [], None
    for pno, text in paragraphs:
        if pno != last_page:
            chunks.append(f"<<<PDFPAGE {pno}>>>")
            last_page = pno
        chunks.append(text + "\n")
    full_text = "\n".join(chunks)

    empty_pages = [i + 1 for i, (_, p) in enumerate(pages) if not p.get_text().strip()]
    qa = {
        "pdf": pdf_path,
        "pages": doc.page_count,
        "paragraphs": len(paragraphs),
        "chars": len(full_text),
        "intro_heading_found": bool(
            re.search(r"(?im)^\s*(1\.?\s*)?introduction\s*$", full_text)
        ),
        "pages_needing_ocr": empty_pages,
    }
    doc.close()
    return full_text, qa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("out")
    ap.add_argument("--single-column", action="store_true")
    args = ap.parse_args()
    text, qa = convert(args.pdf, args.single_column)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(json.dumps(qa, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
