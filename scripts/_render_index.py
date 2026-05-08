#!/usr/bin/env python3
"""Re-render versions/INDEX.md and refresh versions/openclaw-docs.latest.*
from whatever's currently on disk, without touching upstream or re-flattening.

Used by the CI workflow's `Re-render INDEX.md` step after the releases
manifest has been updated. Calling the helpers in flatten_docs.py directly
keeps the index-format logic in one place."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flatten_docs import list_version_docs, write_index, update_latest

versions_dir = Path("versions")
ranked = list_version_docs(versions_dir)
write_index(versions_dir, ranked)
update_latest(versions_dir, ranked)
print(f"Re-rendered INDEX.md against {len(ranked)} in-tree version doc(s).")
