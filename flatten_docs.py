#!/usr/bin/env python3
"""
Flatten OpenClaw docs into a single markdown file, stored by version.

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
    4. overwrite <skill-dir>/versions/openclaw-docs.latest.md with the newest version
    5. write <skill-dir>/versions/INDEX.md listing all stored versions
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

EXCLUDE_DIRS = {".generated", "images", "assets", "zh-CN", "ja-JP", ".i18n"}


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


VERSION_GLOB = "openclaw-docs.*.md"
VERSION_PREFIX = "openclaw-docs."
LATEST_NAME = "openclaw-docs.latest.md"


def _version_key(p):
    # "openclaw-docs.2026.5.6" -> (2026, 5, 6); sorts numerically not lexically
    parts = p.stem[len(VERSION_PREFIX):].split(".")
    return tuple(int(x) if x.isdigit() else x for x in parts)


def write_index(versions_dir):
    files = sorted(
        [
            p
            for p in Path(versions_dir).glob(VERSION_GLOB)
            if p.name != LATEST_NAME
        ],
        key=_version_key,
        reverse=True,
    )
    idx = Path(versions_dir) / "INDEX.md"
    with open(idx, "w") as f:
        f.write("# OpenClaw Docs — Stored Versions\n\n")
        for p in files:
            ver = p.stem[len(VERSION_PREFIX):]  # "openclaw-docs.2026.5.6" -> "2026.5.6"
            size_kb = p.stat().st_size // 1024
            f.write(f"- **{ver}** — `{p.name}` ({size_kb} KB)\n")
    return files


def update_latest(versions_dir, ranked_files):
    """Overwrite openclaw-docs.latest.md with a real copy of the highest-version file
    in the directory (not the file we just wrote — running on an older checkout
    must not clobber latest.md with older content). Plain copy, not symlink, so
    raw.githubusercontent.com fetches and Windows checkouts work."""
    if not ranked_files:
        return
    newest = ranked_files[0]
    latest = Path(versions_dir) / LATEST_NAME
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.write_bytes(newest.read_bytes())


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
    out_file = versions_dir / f"{VERSION_PREFIX}{version}.md"
    flatten(repo, out_file)

    files = write_index(versions_dir)
    update_latest(versions_dir, files)

    print(f"Flattened OpenClaw docs v{version} → {out_file}")
    print(f"Stored versions: {len(files)}")


if __name__ == "__main__":
    main()
