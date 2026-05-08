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
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

VERSION_PREFIX = "openclaw-docs."
SUFFIX_DOC = ".md"
SUFFIX_TOC = ".toc.jsonl"
SUFFIX_SEC = ".sections.jsonl"

# Public release base. Override with OPENCLAW_DOCS_RELEASE_BASE for forks.
RELEASE_BASE = os.environ.get(
    "OPENCLAW_DOCS_RELEASE_BASE",
    "https://github.com/pixelitemedia/openclaw-docs-skill/releases/download",
)


def _default_versions_dir() -> Path:
    """Resolve the versions/ directory next to this script's parent (skill root)."""
    here = Path(__file__).resolve()
    return here.parent.parent / "versions"


def _cache_dir() -> Path:
    """Per-version cache for fetched release assets.

    Defaults to ``$XDG_CACHE_HOME/openclaw-docs/`` (or ``~/.cache/openclaw-docs/``).
    Releases are immutable so this cache never expires."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return Path(base) / "openclaw-docs"


def _fetch_release_asset(version: str, suffix: str, dest: Path) -> None:
    """Download a single release asset to `dest` (atomically). Raises on failure."""
    url = f"{RELEASE_BASE}/v{version}/{VERSION_PREFIX}{version}{suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=30) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        tmp.replace(dest)
    except urllib.error.HTTPError as e:
        tmp.unlink(missing_ok=True)
        sys.exit(f"Failed to fetch {url}: HTTP {e.code}")
    except Exception as e:
        tmp.unlink(missing_ok=True)
        sys.exit(f"Failed to fetch {url}: {e}")


def _resolve_version_files(versions_dir: Path, version: str) -> Path:
    """Return the directory containing the {md, toc.jsonl, sections.jsonl} triplet
    for this version. Looks in `versions_dir` first; if any are missing and the
    version is not "latest", fetches from the matching GitHub Release into the
    user's cache directory and returns that. Releases are immutable so the cached
    copy is reused on subsequent calls."""
    needed = [SUFFIX_DOC, SUFFIX_TOC, SUFFIX_SEC]
    if all((versions_dir / f"{VERSION_PREFIX}{version}{s}").exists() for s in needed):
        return versions_dir
    if version == "latest":
        # latest.* files are always supposed to be in versions/. If they aren't,
        # something is wrong with the install — don't try to fetch a tag.
        sys.exit(f"latest.* files missing in {versions_dir}; run flatten_docs.py or git pull.")
    cache = _cache_dir() / version
    for s in needed:
        target = cache / f"{VERSION_PREFIX}{version}{s}"
        if not target.exists():
            print(f"Fetching {target.name} from release v{version}...", file=sys.stderr)
            _fetch_release_asset(version, s, target)
    return cache


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
    src = _resolve_version_files(versions_dir, version)
    p = src / f"{VERSION_PREFIX}{version}{SUFFIX_TOC}"
    return [TocRow(**r) for r in _load_jsonl(p)]


def load_sections(versions_dir: Path, version: str) -> list[SecRow]:
    src = _resolve_version_files(versions_dir, version)
    p = src / f"{VERSION_PREFIX}{version}{SUFFIX_SEC}"
    return [SecRow(**r) for r in _load_jsonl(p)]


def doc_path(versions_dir: Path, version: str) -> Path:
    src = _resolve_version_files(versions_dir, version)
    p = src / f"{VERSION_PREFIX}{version}{SUFFIX_DOC}"
    if not p.exists():
        sys.exit(f"Doc file missing: {p}")
    return p


def find_section_for_line(sections: list[SecRow], line_no: int) -> Optional[SecRow]:
    """Locate the section containing the given 1-indexed line."""
    for s in sections:
        if s.start_line <= line_no <= s.end_line:
            return s
    return None


def _concrete_version(rows) -> str:
    """Resolve `latest` to the concrete version recorded in the indexes.

    Citations should always pin to a durable version string, never to the
    moving `latest` alias. The TOC + section indexes both carry `version`
    on every row; pull it from row 0."""
    if not rows:
        return "?"
    return rows[0].version if hasattr(rows[0], "version") else rows[0]["version"]


def _citation_header(version: str, suffix: str) -> str:
    """Standard preface used across all three commands."""
    return f"# According to docs for OpenClaw {version} — {suffix}"


def cmd_query(args, versions_dir: Path):
    """Exact-term search: return top matches with section path + line + context.

    Adjacent hits in the same section are grouped into one merged excerpt so
    exact identifier lookups don't burn output budget on duplicate context."""
    docp = doc_path(versions_dir, args.version)
    sections = load_sections(versions_dir, args.version)
    concrete = _concrete_version(sections)
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

    raw_hits = []
    for i, line in enumerate(text, start=1):
        if match(line):
            raw_hits.append(i)
            if len(raw_hits) >= args.max_hits:
                break

    if not raw_hits:
        print(f"No matches for `{args.query}` in OpenClaw {concrete}.")
        return

    # Group hits by their containing section so we emit one merged excerpt
    # per section instead of repeating overlapping context windows.
    by_section: dict = {}
    for line_no in raw_hits:
        sec = find_section_for_line(sections, line_no)
        sec_path = sec.path if sec else "?"
        by_section.setdefault(sec_path, []).append(line_no)

    print(_citation_header(concrete, f"`{args.query}`") + "\n")
    print(f"_{len(raw_hits)} match(es) across {len(by_section)} section(s)_\n")

    ctx = args.context_lines
    for sec_path, hit_lines in by_section.items():
        # Compute the merged context window: union of [hit-ctx, hit+ctx] across
        # this section's hits, collapsing adjacent/overlapping windows.
        windows = sorted([(max(1, h - ctx), min(len(text), h + ctx)) for h in hit_lines])
        merged: list = []
        for lo, hi in windows:
            if merged and lo <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        hit_set = set(hit_lines)
        first_hit = hit_lines[0]
        suffix = "" if len(hit_lines) == 1 else f" (+ {len(hit_lines) - 1} adjacent)"
        print(f"## `{sec_path}` (line {first_hit}{suffix})\n")
        for k, (lo, hi) in enumerate(merged):
            if k > 0:
                print("```\n")
            print("```")
            for j in range(lo, hi + 1):
                marker = "→ " if j in hit_set else "  "
                print(f"{marker}{j:>6}: {text[j - 1]}")
        print("```\n")


# Stop-words filtered out of broad --toc queries so phrasings like
# "how do I set up Telegram" route on "set telegram" (the meaningful part).
_TOC_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were",
    "do", "does", "did", "have", "has", "had",
    "i", "you", "we", "they", "it",
    "to", "of", "in", "on", "at", "by", "for", "with", "from",
    "and", "or", "but", "not",
    "how", "what", "when", "where", "why", "which",
    "can", "could", "should", "would",
    "this", "that", "these", "those",
    "up", "out",
    "openclaw", "doc", "docs",
})


def cmd_toc(args, versions_dir: Path):
    """Broad TOC routing. Searches path + h2 + h3 + keywords for the query."""
    rows = load_toc(versions_dir, args.version)
    concrete = _concrete_version(rows)
    needle = args.toc.lower()
    raw_terms = [t for t in re.split(r"\s+", needle) if t]
    terms = [t for t in raw_terms if t not in _TOC_STOPWORDS] or raw_terms

    def score(r: TocRow) -> int:
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
        print(f"No TOC matches for `{args.toc}` in OpenClaw {concrete}.")
        return

    print(_citation_header(concrete, f"TOC matches for `{args.toc}`") + "\n")
    print(f"_Top {len(top)} candidate section(s), ranked_\n")
    for r in top:
        print(f"## `{r.path}` (lines {r.start_line}–{r.end_line})")
        if r.h2:
            print(f"- **H2:** {', '.join(r.h2[:8])}")
        if r.h3:
            print(f"- **H3:** {', '.join(r.h3[:8])}")
        print()
    print("_Use `--section <path>` to extract one._\n")


def cmd_section(args, versions_dir: Path):
    """Extract a section by path; optionally narrow to one heading.

    Uses byte-offset slicing (start_byte / end_byte from the section index)
    instead of reading the whole flattened doc and slicing by line — saves
    ~6 MB of read I/O per call."""
    docp = doc_path(versions_dir, args.version)
    sections = load_sections(versions_dir, args.version)
    concrete = _concrete_version(sections)
    target = next((s for s in sections if s.path == args.section), None)
    if target is None:
        # Fuzzy: prefix or basename match
        candidates = [
            s
            for s in sections
            if args.section in s.path or s.path.endswith("/" + args.section)
        ]
        if not candidates:
            sys.exit(f"No section matches `{args.section}` in OpenClaw {concrete}.")
        if len(candidates) > 1:
            print("# Multiple matches — be more specific:\n", file=sys.stderr)
            for c in candidates[:10]:
                print(f"- `{c.path}`", file=sys.stderr)
            sys.exit(1)
        target = candidates[0]

    # Byte-offset slice — open in binary, seek, read just this section's bytes.
    with open(docp, "rb") as f:
        f.seek(target.start_byte)
        section_bytes = f.read(target.end_byte - target.start_byte)
    section_text = section_bytes.decode("utf-8")
    lines = section_text.split("\n")

    if args.heading:
        # Trim to the H2/H3 block matching the heading text. When the matched
        # heading is H2, extraction continues through child H3s until the next
        # H2 (end at next heading with level <= matched_level).
        h_re = re.compile(r"^(#{2,3})\s+(.+)$")
        start = None
        matched_level = None  # 2 or 3
        end = None
        needle_lc = args.heading.lower()
        for i, line in enumerate(lines):
            m = h_re.match(line)
            if not m:
                continue
            level = len(m.group(1))
            heading_text = m.group(2)
            if start is None:
                if needle_lc in heading_text.lower():
                    start = i
                    matched_level = level
                continue
            if level <= matched_level:
                end = i
                break
        if start is None:
            sys.exit(f"Heading `{args.heading}` not found in `{target.path}`.")
        end = end if end is not None else len(lines)
        lines = lines[start:end]

    body = "\n".join(lines)
    if len(body) > args.max_chars:
        body = (
            body[: args.max_chars]
            + f"\n\n... _truncated at {args.max_chars} chars; full section is {target.char_count} chars_"
        )

    citation = f"`{target.path}`"
    if args.heading:
        citation += f" → `{args.heading}`"
    print(_citation_header(target.version, citation) + "\n")
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
