#!/usr/bin/env python3
"""
Flatten OpenClaw docs into a single markdown file, plus generate retrieval
indexes (TOC + section offsets), stored by version.

Usage:
    python3 flatten_docs.py [--repo PATH] [--skill-dir PATH]

Defaults:
    --repo       ~/OpenClaw/docs/openclaw
    --skill-dir  ~/.claude/skills/openclaw-docs

Behavior:
    1. git fetch + pull the repo
    2. read version from package.json
    3. walk <repo>/docs/**/*.md and concatenate into
       <skill-dir>/versions/openclaw-docs.<version>.md
    4. emit indexes alongside the docs:
         versions/openclaw-docs.<version>.toc.jsonl
         versions/openclaw-docs.<version>.sections.jsonl
    5. overwrite versions/openclaw-docs.latest.{md,toc.jsonl,sections.jsonl}
       with copies of the highest-version files
    6. write versions/INDEX.md listing all stored versions
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EXCLUDE_DIRS = {".generated", "images", "assets", "zh-CN", "ja-JP", ".i18n"}

VERSION_GLOB = "openclaw-docs.*.md"
VERSION_PREFIX = "openclaw-docs."
LATEST_NAME = "openclaw-docs.latest.md"

# Filename suffix conventions
SUFFIX_DOC = ".md"
SUFFIX_TOC = ".toc.jsonl"
SUFFIX_SEC = ".sections.jsonl"

# Markdown patterns. We intentionally only consider headings at the start of a
# physical line outside of fenced code blocks (we strip code fences when scanning).
RE_SECTION = re.compile(r"^# Section: (.+)$")
RE_H2 = re.compile(r"^## (.+)$")
RE_H3 = re.compile(r"^### (.+)$")
RE_FENCE = re.compile(r"^```")
RE_KEYWORD_SPLIT = re.compile(r"[^a-z0-9]+")


def sh(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"$ {' '.join(cmd)}\n{r.stderr}")
    return r.stdout.strip()


def git_pull(repo):
    sh(["git", "fetch", "--all", "--tags"], cwd=repo)
    sh(["git", "pull", "--ff-only"], cwd=repo, check=False)


def read_version(repo):
    pkg = Path(repo) / "package.json"
    with open(pkg) as f:
        return json.load(f)["version"]


def flatten(repo, out_file):
    docs_dir = Path(repo) / "docs"
    with open(out_file, "w", encoding="utf-8") as out:
        out.write(f"# OpenClaw Documentation\n\n")
        out.write(f"_Source: {repo}_\n\n")
        for root, dirs, files in os.walk(docs_dir):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for file in sorted(files):
                if not file.endswith(".md"):
                    continue
                fp = Path(root) / file
                rel = fp.relative_to(docs_dir)
                out.write(f"\n\n# Section: {rel}\n\n")
                try:
                    out.write(fp.read_text(encoding="utf-8"))
                except Exception as e:
                    print(f"Failed to read {fp}: {e}", file=sys.stderr)
                out.write("\n")


def _keywords_from(path: str, h2: list, h3: list) -> list:
    """Cheap keyword extraction: lowercase tokens from path + headings, deduped,
    stop-words removed, length>=3. No NLP — just structural routing terms."""
    stop = {
        "the", "and", "for", "with", "from", "into", "but", "not", "you",
        "your", "are", "can", "this", "that", "these", "those", "use", "using",
        "how", "what", "when", "where", "why", "all", "any", "out", "via",
        "openclaw", "doc", "docs", "section", "sections",
    }
    text = " ".join([path, *h2, *h3]).lower()
    tokens = [t for t in RE_KEYWORD_SPLIT.split(text) if len(t) >= 3 and t not in stop]
    seen = set()
    out = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:20]  # cap at 20 to keep TOC rows compact


def build_indexes(doc_path: Path, version: str) -> tuple:
    """Single pass over the flattened doc. Emits two parallel JSONL streams:
      - toc.jsonl: one row per section with path, line range, h2/h3, keywords
      - sections.jsonl: one row per section with line + byte ranges + char count
    Both share the same row order (one per `# Section: ...` block)."""
    text = doc_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    # Build a parallel byte-offset table: byte_offsets[i] is the byte index of
    # the start of line i (1-indexed; byte_offsets[0] is unused).
    byte_offsets = [0]
    cumulative = 0
    for line in lines:
        byte_offsets.append(cumulative)
        cumulative += len(line.encode("utf-8")) + 1  # +1 for the \n
    # The last sentinel: total byte length
    byte_offsets.append(cumulative)

    toc_rows = []
    sec_rows = []

    in_fence = False
    cur = None  # current section dict in progress

    def close_section(end_line_excl: int):
        if cur is None:
            return
        start_line = cur["start_line"]
        end_line = end_line_excl - 1  # inclusive last line of this section
        # Drop the section header line itself from byte range? Keep it included
        # so the section row is self-contained when extracted.
        start_byte = byte_offsets[start_line]
        end_byte = byte_offsets[end_line + 1]  # exclusive
        char_count = sum(len(lines[i - 1]) + 1 for i in range(start_line, end_line + 1))

        toc_rows.append({
            "version": version,
            "path": cur["path"],
            "start_line": start_line,
            "end_line": end_line,
            "h2": cur["h2"],
            "h3": cur["h3"],
            "keywords": _keywords_from(cur["path"], cur["h2"], cur["h3"]),
        })
        sec_rows.append({
            "version": version,
            "path": cur["path"],
            "start_line": start_line,
            "end_line": end_line,
            "start_byte": start_byte,
            "end_byte": end_byte,
            "char_count": char_count,
        })

    for i, line in enumerate(lines, start=1):
        if RE_FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        m = RE_SECTION.match(line)
        if m:
            close_section(i)
            cur = {"path": m.group(1).strip(), "start_line": i, "h2": [], "h3": []}
            continue
        if cur is None:
            continue
        m = RE_H2.match(line)
        if m:
            cur["h2"].append(m.group(1).strip())
            continue
        m = RE_H3.match(line)
        if m:
            cur["h3"].append(m.group(1).strip())

    # close trailing section
    close_section(len(lines) + 1)

    return toc_rows, sec_rows


def _emit_indexes_for(doc_path: Path, version: str, versions_dir: Path):
    toc_rows, sec_rows = build_indexes(doc_path, version)
    stem = doc_path.name[: -len(SUFFIX_DOC)]
    write_jsonl(versions_dir / f"{stem}{SUFFIX_TOC}", toc_rows)
    write_jsonl(versions_dir / f"{stem}{SUFFIX_SEC}", sec_rows)
    print(f"  {version}: TOC={len(toc_rows)} sections, sections={len(sec_rows)}")


def write_jsonl(path: Path, rows: list):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def _version_key(p):
    # "openclaw-docs.2026.5.6" -> (2026, 5, 6); sorts numerically not lexically
    stem = p.name[len(VERSION_PREFIX):-len(SUFFIX_DOC)]  # strip prefix + ".md"
    parts = stem.split(".")
    return tuple(int(x) if x.isdigit() else x for x in parts)


def list_version_docs(versions_dir: Path) -> list:
    """All openclaw-docs.<ver>.md files (excluding latest.md), newest first."""
    return sorted(
        [
            p
            for p in versions_dir.glob(VERSION_GLOB)
            if p.name != LATEST_NAME and p.suffix == SUFFIX_DOC
        ],
        key=_version_key,
        reverse=True,
    )


def write_index(versions_dir: Path, ranked: list):
    idx = versions_dir / "INDEX.md"
    with open(idx, "w") as f:
        f.write("# OpenClaw Docs — Stored Versions\n\n")
        f.write("Each version has three artifacts:\n\n")
        f.write("- `openclaw-docs.<version>.md` — flattened docs\n")
        f.write("- `openclaw-docs.<version>.toc.jsonl` — TOC (sections + H2/H3 + keywords + line ranges)\n")
        f.write("- `openclaw-docs.<version>.sections.jsonl` — section offsets (line + byte ranges)\n\n")
        f.write("`openclaw-docs.latest.*` are real copies of the highest-version files.\n\n")
        f.write("## Versions (newest first)\n\n")
        for p in ranked:
            stem = p.name[len(VERSION_PREFIX):-len(SUFFIX_DOC)]
            size_kb = p.stat().st_size // 1024
            f.write(f"- **{stem}** — `{p.name}` ({size_kb} KB)\n")


def update_latest(versions_dir: Path, ranked_docs: list):
    """Overwrite latest.{md,toc.jsonl,sections.jsonl} with copies of the highest-
    version triplet. Always copy from the on-disk newest, not from whatever was
    just written this run — running on an older checkout must not clobber latest."""
    if not ranked_docs:
        return
    newest_doc = ranked_docs[0]
    stem = newest_doc.name[: -len(SUFFIX_DOC)]  # "openclaw-docs.2026.5.6"
    pairs = [
        (newest_doc, versions_dir / LATEST_NAME),
        (versions_dir / f"{stem}{SUFFIX_TOC}", versions_dir / f"openclaw-docs.latest{SUFFIX_TOC}"),
        (versions_dir / f"{stem}{SUFFIX_SEC}", versions_dir / f"openclaw-docs.latest{SUFFIX_SEC}"),
    ]
    for src, dst in pairs:
        if not src.exists():
            continue  # missing index — older version that pre-dates indexes; tolerate
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        dst.write_bytes(src.read_bytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.expanduser("~/OpenClaw/docs/openclaw"))
    ap.add_argument(
        "--skill-dir", default=os.path.expanduser("~/.claude/skills/openclaw-docs")
    )
    ap.add_argument(
        "--no-pull", action="store_true", help="Skip git fetch/pull (useful offline)"
    )
    args = ap.parse_args()

    repo = Path(args.repo)
    if not (repo / ".git").exists():
        sys.exit(f"Not a git repo: {repo}")

    versions_dir = Path(args.skill_dir) / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    if not args.no_pull:
        git_pull(repo)

    version = read_version(repo)
    doc_file = versions_dir / f"{VERSION_PREFIX}{version}{SUFFIX_DOC}"
    flatten(repo, doc_file)

    # Build indexes for the version we just produced
    _emit_indexes_for(doc_file, version, versions_dir)

    # Backfill indexes for any other version docs that don't have them yet
    # (e.g. committed before the index feature existed). One-time cost that
    # keeps INDEX.md and latest.* aliases consistent on every run.
    for p in list_version_docs(versions_dir):
        stem = p.name[: -len(SUFFIX_DOC)]
        toc_p = versions_dir / f"{stem}{SUFFIX_TOC}"
        sec_p = versions_dir / f"{stem}{SUFFIX_SEC}"
        if toc_p.exists() and sec_p.exists():
            continue
        ver = stem[len(VERSION_PREFIX):]
        print(f"Backfilling indexes for {ver}...")
        _emit_indexes_for(p, ver, versions_dir)

    # Re-rank versions on disk and refresh INDEX.md + latest.* aliases
    ranked = list_version_docs(versions_dir)
    write_index(versions_dir, ranked)
    update_latest(versions_dir, ranked)

    print(f"Flattened OpenClaw docs v{version} → {doc_file}")
    print(f"Stored versions: {len(ranked)}")


if __name__ == "__main__":
    main()
