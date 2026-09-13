#!/usr/bin/env python3
"""Extract the Introduction section from a converted paper text.

Input is the output of `pdf_to_text.py` (page-marked UTF-8 text). The tool:

  1. locates the Introduction heading,
  2. locates the following top-level section heading,
  3. strips running headers/footers and page numbers,
  4. numbers the surviving paragraphs P1..Pn,
  5. reports the PDF page range and a per-paragraph page locator.

Usage:
    python extract_intro.py <paper_text.txt> <out.md> --title "<paper title>"

The result is a *locator + source-text* record, kept separate from the
argument analysis. Nothing here is generated prose: every paragraph is the
extracted PDF text, with removal of running heads explicitly listed.
"""

import argparse
import re
import sys
from collections import Counter

PAGE_MARK = re.compile(r"^<<<PDFPAGE (\d+)>>>$")
# A top-level section heading: "2 Foo", "2. Foo", "3 Related Work", "2.1 Bar"
SECTION_HEAD = re.compile(r"^\s*(\d{1,2})(?:\.(\d{1,2}))?\.?\s+([A-Z][^\n]{1,80})$")
# The Introduction heading is sometimes its own line ("INTRODUCTION",
# "1 Introduction") and sometimes shares a line with the first body sentence
# ("Introduction Over the last decade, ..."), depending on the template.
INTRO_HEAD = re.compile(r"^\s*(?:1\.?\s*)?introduction\b\s*[:.]?\s*", re.IGNORECASE)
# Lines that are noise: bare folios, arXiv stamps, conference running feet.
# ACM prints 3–4 digit folios ("2870"); arXiv preprints print 1–2 digit ones.
# A 1–2 digit bare number may instead be a section number ("2" on its own
# line), so those are decided separately in `clean`.
FOLIO = re.compile(r"^\s*\d{3,4}\s*$")
SHORT_NUM = re.compile(r"^\s*\d{1,2}\s*$")
ARXIV_STAMP = re.compile(r"^\s*arXiv:\S+.*$")
RUNNING_TAIL = re.compile(r"^\s*(WWW\s*'?\d{2}|The Web Conference|Proceedings of the ACM Web Conference).*$")
# Non-prose furniture that the geometric pass still leaves inside the span:
# figure/table captions, author blocks, affiliations and footnotes.
CAPTION = re.compile(r"^\s*(Figure|Fig\.|Table|Algorithm|Listing|Eq\.)\s*\d+\s*[:.]", re.I)
EMAIL = re.compile(r"^[\w.+-]+@[\w.-]+\.\w+$")
AFFIL = re.compile(
    r"^\s*(?:[A-Z][\w&.\-]*\.?\s+)*"
    r"(University|Universit|Institute|Laborator|College|Academy|Inc\.|Ltd\.|Corp\.|"
    r"School of|Department of|Faculty of|Research)\b")
FOOTNOTE = re.compile(r"^\s*[∗†‡§¶]|^\s*\d+\s*[A-Z][a-z]+,?\s+(University|Institute)")


def load_pages(path):
    """Return a list of (page_number, [lines])."""
    pages, current = [], None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            m = PAGE_MARK.match(line)
            if m:
                current = (int(m.group(1)), [])
                pages.append(current)
            elif current is not None:
                current[1].append(line)
    return pages


def find_repeated_lines(pages):
    """Running heads appear on most pages; treat frequent short lines as noise."""
    counts = Counter()
    for _, lines in pages:
        for line in lines:
            s = line.strip()
            if 3 <= len(s) <= 90:
                counts[s] += 1
    threshold = max(3, int(len(pages) * 0.4))
    return {s for s, c in counts.items() if c >= threshold}


def looks_like_heading(s):
    """Heuristic for a section title line (used to protect section numbers).

    Section titles in these papers are ALL CAPS ("MOTIVATION") or short
    multi-word Title Case ("Related Work"). Chart axis captions are Title
    Case but one or two words ("Request Num", "Time"), so require length.
    """
    s = s.strip()
    if not (3 <= len(s) <= 70):
        return False
    words = s.split()
    letters = sum(c.isalpha() for c in s)
    if letters < len(s) * 0.5 or len(words) > 7:
        return False
    if s[:1].islower() or s.endswith((")", "%", ".", ",")):
        return False
    return s.isupper() or len(words) >= 3


def clean(lines, noise):
    out = []
    for line in lines:
        s = line.strip()
        if not s:
            out.append("")
            continue
        if FOLIO.match(s) or ARXIV_STAMP.match(s) or RUNNING_TAIL.match(s):
            continue
        if s in noise:
            continue
        if CAPTION.match(s) or EMAIL.match(s) or AFFIL.match(s):
            continue
        if FOOTNOTE.match(s) and len(s) < 120:
            continue
        out.append(s)

    # A bare 1–2 digit line is a page folio unless it introduces a heading.
    kept = []
    for i, s in enumerate(out):
        if SHORT_NUM.match(s):
            nxt = next((x for x in out[i + 1:] if x), "")
            if not looks_like_heading(nxt):
                continue
        kept.append(s)
    return kept


def _is_next_section_heading(flat, j):
    """True if flat[j] starts the section following the Introduction.

    ACM typesetting puts the number and title on separate lines:

        2
        MOTIVATION

    so both the split form and the single-line form must be recognised.
    Chart tick labels ("20" / "Request Num") look similar, so the split form
    requires the number to be exactly the next section number (2 or 3) and the
    title line to read like a heading rather than an axis caption.
    """
    s = flat[j][2].strip()
    if not s or INTRO_HEAD.match(s):
        return False
    if re.match(r"^\s*(References|Acknowledg|Bibliography)\b", s, re.I):
        return True

    # Unnumbered ALL-CAPS headings ("PRELIMINARIES", "METHODOLOGY") are common
    # in the ACM template; they mark the end of the Introduction just as
    # numbered ones do.
    if s.isupper() and looks_like_heading(s):
        return True

    m = SECTION_HEAD.match(s)
    if m and not re.match(r"^introduction$", m.group(3).strip(), re.I):
        return int(m.group(1)) <= 5

    if s in ("2", "3", "4", "5"):
        nxt = next((flat[k][2] for k in range(j + 1, len(flat)) if flat[k][2].strip()), "")
        return looks_like_heading(nxt)
    return False


def locate(pages, noise):
    """Find the Introduction span: (start_page, end_page, lines)."""
    flat = []                                   # (page, line_index, text)
    for pno, lines in pages:
        cleaned = clean(lines, noise)
        for i, s in enumerate(cleaned):
            flat.append((pno, i, s))

    start = None
    for i, (pno, _, s) in enumerate(flat):
        if INTRO_HEAD.match(s):
            start = i
            break
    if start is None:
        return None

    # When the heading shares its line with body text, keep the remainder as
    # the first body line rather than dropping it.
    remainder = INTRO_HEAD.sub("", flat[start][2]).strip()
    flat[start] = (flat[start][0], flat[start][1], remainder)

    if remainder:
        # Heading and first sentence shared a line; that line is body text.
        body_start = start
    else:
        body_start = start + 1
        while body_start < len(flat) and not flat[body_start][2].strip():
            body_start += 1

    end = len(flat)
    for j in range(body_start, len(flat)):
        if _is_next_section_heading(flat, j):
            end = j
            break

    span = flat[body_start:end]
    if not span:
        return None
    return {
        "start_page": span[0][0],
        "end_page": span[-1][0],
        "lines": [(p, s) for p, _, s in span],
    }


def to_paragraphs(lines):
    """Group lines into paragraphs, tracking the page each paragraph starts on."""
    paras, buf, cur_page = [], [], None
    for pno, s in lines:
        if s.strip():
            if cur_page is None:
                cur_page = pno
            buf.append(s.strip())
        else:
            if buf:
                paras.append((cur_page, " ".join(buf)))
                buf, cur_page = [], None
    if buf:
        paras.append((cur_page, " ".join(buf)))
    return paras


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("out")
    ap.add_argument("--title", default="")
    args = ap.parse_args()

    pages = load_pages(args.text)
    noise = find_repeated_lines(pages)
    found = locate(pages, noise)
    if not found:
        print("INTRODUCTION NOT FOUND", file=sys.stderr)
        return 1

    paras = to_paragraphs(found["lines"])
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        if args.title:
            fh.write(f"# Introduction — {args.title}\n\n")
        fh.write(
            f"PDF pages: {found['start_page']}–{found['end_page']} | "
            f"paragraphs: {len(paras)} | "
            f"running heads removed: {len(noise)}\n\n"
        )
        for i, (pno, text) in enumerate(paras, 1):
            fh.write(f"**P{i}** _(PDF p.{pno})_\n\n{text}\n\n")
    print(f"{args.out}: pages {found['start_page']}-{found['end_page']}, "
          f"{len(paras)} paragraphs, {len(noise)} running-head lines removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
