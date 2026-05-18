#!/usr/bin/env python3
"""Re-render <skill-dir>/versions/INDEX.md and refresh
<skill-dir>/versions/openclaw-docs.latest.* from whatever's currently on
disk, without touching upstream or re-flattening.

Used by the CI workflow's `Re-render INDEX.md` step after the releases
manifest has been updated."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make flatten_docs importable (it lives next to this script in ci/)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from flatten_docs import list_version_docs, write_index, update_latest  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--skill-dir",
        default="skills/openclaw-docs",
        help="Path to the skill root (default: skills/openclaw-docs)",
    )
    args = ap.parse_args()

    versions_dir = Path(args.skill_dir) / "versions"
    if not versions_dir.is_dir():
        sys.exit(f"versions dir not found: {versions_dir}")
    ranked = list_version_docs(versions_dir)
    write_index(versions_dir, ranked)
    update_latest(versions_dir, ranked)
    print(f"Re-rendered INDEX.md against {len(ranked)} in-tree version doc(s) at {versions_dir}.")


if __name__ == "__main__":
    main()
