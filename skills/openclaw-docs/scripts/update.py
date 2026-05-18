#!/usr/bin/env python3
"""Refresh the openclaw-docs-skill installation in place.

Auto-detects whether the skill is installed as a `git clone` or extracted
from a ZIP and uses the appropriate refresh path:

- **git install** (`.git` directory present) → `git pull --ff-only`
- **ZIP install** (no `.git`) → `curl` the runtime files from raw GitHub

Either way, after running this the skill has the current `latest.*` docs +
indexes + lookup script + version manifest.

Run from anywhere — the script resolves its own location:

    python3 scripts/update.py

Override the raw base for forks via `OPENCLAW_DOCS_RAW_BASE`."""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
# Files live under skills/openclaw-docs/ in the repo since the plugin restructure.
RAW_BASE = os.environ.get(
    "OPENCLAW_DOCS_RAW_BASE",
    "https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/skills/openclaw-docs",
)

# Runtime files an installed skill needs. CI-only helpers
# (flatten_docs.py, scripts/_sync_releases_manifest.py, etc.) are intentionally
# excluded — consumers don't run them.
RUNTIME_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/lookup.py",
    "scripts/update.py",
    "scripts/smoke_test.sh",
    "versions/openclaw-docs.latest.md",
    "versions/openclaw-docs.latest.toc.jsonl",
    "versions/openclaw-docs.latest.sections.jsonl",
    "versions/INDEX.md",
    "versions/releases.json",
    "README.md",
)


def is_git_clone() -> bool:
    return (SKILL_ROOT / ".git").is_dir()


def update_via_git() -> None:
    print(f"git install detected at {SKILL_ROOT}; running git pull...")
    subprocess.run(["git", "-C", str(SKILL_ROOT), "fetch", "--quiet"], check=True)
    subprocess.run(
        ["git", "-C", str(SKILL_ROOT), "pull", "--ff-only", "--quiet"], check=True
    )
    rev = subprocess.run(
        ["git", "-C", str(SKILL_ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    print(f"Updated to {rev}.")


def _fetch(url: str, dest: Path) -> bool:
    """Fetch a single URL to dest, atomically. Returns True on success."""
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
        return True
    except urllib.error.HTTPError as e:
        tmp.unlink(missing_ok=True)
        print(f"  ✗ {dest.relative_to(SKILL_ROOT)} ← HTTP {e.code}", file=sys.stderr)
        return False
    except Exception as e:
        tmp.unlink(missing_ok=True)
        print(f"  ✗ {dest.relative_to(SKILL_ROOT)} ← {e}", file=sys.stderr)
        return False


def update_via_curl() -> None:
    print(f"ZIP install detected at {SKILL_ROOT}; fetching from {RAW_BASE}...")
    ok = 0
    for relpath in RUNTIME_FILES:
        target = SKILL_ROOT / relpath
        if _fetch(f"{RAW_BASE}/{relpath}", target):
            print(f"  ✓ {relpath}")
            ok += 1
    print(f"Refreshed {ok}/{len(RUNTIME_FILES)} files.")
    if ok < len(RUNTIME_FILES):
        sys.exit(1)


def main() -> None:
    if is_git_clone():
        update_via_git()
    else:
        update_via_curl()


if __name__ == "__main__":
    main()
