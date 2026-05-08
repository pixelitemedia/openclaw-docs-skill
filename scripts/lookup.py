#!/usr/bin/env python3
"""
Deterministic OpenClaw docs lookup.

Reads the flattened doc + JSONL indexes produced by ../flatten_docs.py and
returns compact, citable Markdown chunks. Designed so any AI agent (Claude
Code, Codex, Manus, etc.) gets the same retrieval behavior without
improvising grep/regex calls.

Modes
-----

  python3 lookup.py --version VER --query TERM         # exact-term search
  python3 lookup.py --version VER --toc TERM           # broad TOC search
  python3 lookup.py --version VER --section PATH       # extract a section
  python3 lookup.py --version VER --section PATH \\
                                  --heading TEXT       # extract a subsection

`--version latest` (the default) resolves to the highest-version files. Pass
e.g. `--version 2026.5.6` to pin.

Defaults to **fixed-string matching** for --query, since OpenClaw identifiers
contain regex metacharacters (dots, dashes, slashes, @-prefixes). Pass
`--regex` to switch to Python regex.

Output is Markdown — agents can paste the result into context directly.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

VERSION_PREFIX = "openclaw-docs."
SUFFIX_DOC = ".md"
SUFFIX_TOC = ".toc.jsonl"
SUFFIX_SEC = ".sections.jsonl"


def _default_versions_dir() -> Path:
    """Resolve the versions/ directory next to this script's parent (skill root)."""
    here = Path(__file__).resolve()
    return here.parent.parent / "versions"


@dataclass
class TocRow:
    version: str
    path: str
    start_line: int
    end_line: int
    h2: list
    h3: list
    keywords: list


@dataclass
class SecRow:
    version: str
    path: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    char_count: int


def _load_jsonl(path: Path) -> list:
    if not path.exists():
        sys.exit(f"Index missing: {path}\nRun flatten_docs.py first.")
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_toc(versions_dir: Path, version: str) -> list[TocRow]:
    p = versions_dir / f"{VERSION_PREFIX}{version}{SUFFIX_TOC}"
    return [TocRow(**r) for r in _load_jsonl(p)]


def load_sections(versions_dir: Path, version: str) -> list[SecRow]:
    p = versions_dir / f"{VERSION_PREFIX}{version}{SUFFIX_SEC}"
    return [SecRow(**r) for r in _load_jsonl(p)]


def doc_path(versions_dir: Path, version: str) -> Path:
    p = versions_dir / f"{VERSION_PREFIX}{version}{SUFFIX_DOC}"
    if not p.exists():
        sys.exit(f"Doc file missing: {p}")
    return p


def find_section_for_line(sections: list[SecRow], line_no: int) -> Optional[SecRow]:
    """Locate the section containing the given 1-indexed line."""
    for s in sections:
        if s.start_line <= line_no <= s.end_line:
            return s
    return None


def cmd_query(args, versions_dir: Path):
    """Exact-term search: return top matches with section path + line + context."""
    docp = doc_path(versions_dir, args.version)
    sections = load_sections(versions_dir, args.version)
    text = docp.read_text(encoding="utf-8").split("\n")

    if args.regex:
        try:
            pattern = re.compile(args.query)
        except re.error as e:
            sys.exit(f"Invalid regex: {e}")
        match = lambda line: bool(pattern.search(line))
    else:
        needle = args.query
        if args.ignore_case:
            needle_lc = needle.lower()
            match = lambda line: needle_lc in line.lower()
        else:
            match = lambda line: needle in line

    hits = []
    for i, line in enumerate(text, start=1):
        if match(line):
            hits.append((i, line))
            if len(hits) >= args.max_hits:
                break

    if not hits:
        print(f"No matches for `{args.query}` in OpenClaw {args.version}.")
        return

    print(f"# OpenClaw {args.version} — `{args.query}`\n")
    print(f"_{len(hits)} match(es)_\n")

    ctx = args.context_lines
    for line_no, line in hits:
        sec = find_section_for_line(sections, line_no)
        sec_path = sec.path if sec else "?"
        print(f"## `{sec_path}` (line {line_no})\n")
        lo = max(1, line_no - ctx)
        hi = min(len(text), line_no + ctx)
        print("```")
        for j in range(lo, hi + 1):
            marker = "→ " if j == line_no else "  "
            print(f"{marker}{j:>6}: {text[j - 1]}")
        print("```\n")


def cmd_toc(args, versions_dir: Path):
    """Broad TOC routing. Searches path + h2 + h3 + keywords for the query."""
    rows = load_toc(versions_dir, args.version)
    needle = args.toc.lower()
    terms = [t for t in re.split(r"\s+", needle) if t]

    def score(r: TocRow) -> int:
        haystack = " ".join(
            [r.path, *r.h2, *r.h3, *r.keywords]
        ).lower()
        # +3 path/heading hits, +1 keyword hits
        s = 0
        for term in terms:
            if term in r.path.lower():
                s += 3
            if any(term in h.lower() for h in r.h2 + r.h3):
                s += 3
            if term in r.keywords:
                s += 1
        return s

    scored = [(score(r), r) for r in rows]
    scored.sort(key=lambda t: -t[0])
    top = [r for s, r in scored if s > 0][: args.max_hits]

    if not top:
        print(f"No TOC matches for `{args.toc}` in OpenClaw {args.version}.")
        return

    print(f"# OpenClaw {args.version} — TOC matches for `{args.toc}`\n")
    print(f"_Top {len(top)} candidate sections, ranked_\n")
    for r in top:
        print(f"## `{r.path}` (lines {r.start_line}–{r.end_line})")
        if r.h2:
            print(f"- **H2:** {', '.join(r.h2[:8])}")
        if r.h3:
            print(f"- **H3:** {', '.join(r.h3[:8])}")
        print()
    print(f"_Use `--section <path>` to extract one._\n")


def cmd_section(args, versions_dir: Path):
    """Extract a section by path; optionally narrow to one heading."""
    docp = doc_path(versions_dir, args.version)
    sections = load_sections(versions_dir, args.version)
    target = next((s for s in sections if s.path == args.section), None)
    if target is None:
        # Fuzzy: prefix or basename match
        candidates = [
            s
            for s in sections
            if args.section in s.path or s.path.endswith("/" + args.section)
        ]
        if not candidates:
            sys.exit(f"No section matches `{args.section}` in OpenClaw {args.version}.")
        if len(candidates) > 1:
            print("# Multiple matches — be more specific:\n", file=sys.stderr)
            for c in candidates[:10]:
                print(f"- `{c.path}`", file=sys.stderr)
            sys.exit(1)
        target = candidates[0]

    text = docp.read_text(encoding="utf-8").split("\n")
    lines = text[target.start_line - 1 : target.end_line]

    if args.heading:
        # Trim to the H2/H3 block matching the heading text.
        h_re = re.compile(r"^#{2,3}\s+(.+)$")
        start = None
        end = None
        needle_lc = args.heading.lower()
        for i, line in enumerate(lines):
            m = h_re.match(line)
            if not m:
                continue
            if start is None and needle_lc in m.group(1).lower():
                start = i
                continue
            if start is not None and end is None:
                end = i
                break
        if start is None:
            sys.exit(f"Heading `{args.heading}` not found in `{target.path}`.")
        end = end if end is not None else len(lines)
        lines = lines[start:end]

    body = "\n".join(lines)
    if len(body) > args.max_chars:
        truncated = body[: args.max_chars]
        body = (
            truncated
            + f"\n\n... _truncated at {args.max_chars} chars; full section is {target.char_count} chars_"
        )

    citation = f"`{target.path}`"
    if args.heading:
        citation += f" → `{args.heading}`"
    print(f"# OpenClaw {target.version} — {citation}\n")
    print(body)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default="latest", help="Doc version to query (default: latest)")
    ap.add_argument(
        "--versions-dir",
        type=Path,
        default=None,
        help="Override the versions/ directory (default: ../versions next to this script)",
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--query", help="Exact-term search across the doc")
    g.add_argument("--toc", help="Broad search of section paths + headings + keywords")
    g.add_argument("--section", help="Extract a specific section by path")
    ap.add_argument("--heading", help="When used with --section, extract only this H2/H3")
    ap.add_argument("--regex", action="store_true", help="Treat --query as a Python regex (default: fixed string)")
    ap.add_argument("-i", "--ignore-case", action="store_true", help="Case-insensitive match for --query")
    ap.add_argument("--context-lines", type=int, default=3, help="Lines of context around each --query hit")
    ap.add_argument("--max-hits", type=int, default=10, help="Cap hits returned by --query / --toc")
    ap.add_argument("--max-chars", type=int, default=30000, help="Truncate --section output to this many chars")
    args = ap.parse_args()

    versions_dir = args.versions_dir or _default_versions_dir()
    if not versions_dir.is_dir():
        sys.exit(f"versions/ directory not found: {versions_dir}")

    if args.query is not None:
        cmd_query(args, versions_dir)
    elif args.toc is not None:
        cmd_toc(args, versions_dir)
    elif args.section is not None:
        cmd_section(args, versions_dir)


if __name__ == "__main__":
    main()
