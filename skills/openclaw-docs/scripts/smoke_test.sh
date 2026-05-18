#!/usr/bin/env bash
# Lightweight smoke test for the openclaw-docs-skill retrieval surface.
# Verifies that:
#   1. lookup.py --query, --toc, --section, and --section --heading all run
#      without error and emit the canonical citation header.
#   2. Section byte offsets in *.sections.jsonl resolve to lines that begin
#      with `# Section: <path>` — i.e. the indexes are mutually consistent
#      with the flattened doc.
#   3. --section --heading on an H2 includes child H3 content (regression
#      guard for the heading-extraction bug fixed in d3dcc9e).
#
# Run from repo root. Exit non-zero on failure. CI invokes this after
# regenerating docs + indexes.

set -euo pipefail

cd "$(dirname "$0")/.."

EXPECT_HEADER='^# According to docs for OpenClaw [0-9]+\.[0-9]+\.[0-9]+ '

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

# ---------- 1. Each lookup mode runs and emits the citation header ----------

out=$(python3 scripts/lookup.py --query "gateway.mode" --max-hits 1 --context-lines 1)
echo "$out" | head -n1 | grep -Eq "$EXPECT_HEADER" || fail "--query header missing concrete version"
pass "--query emits concrete-version citation header"

out=$(python3 scripts/lookup.py --toc "telegram setup" --max-hits 1)
echo "$out" | head -n1 | grep -Eq "$EXPECT_HEADER" || fail "--toc header missing concrete version"
pass "--toc emits concrete-version citation header"

out=$(python3 scripts/lookup.py --section gateway/configuration-reference.md --max-chars 2000)
echo "$out" | head -n1 | grep -Eq "$EXPECT_HEADER" || fail "--section header missing concrete version"
pass "--section emits concrete-version citation header"

# ---------- 2a. H2 heading extraction includes child H3s ----------

out=$(python3 scripts/lookup.py --section gateway/configuration-reference.md --heading "Hooks")
echo "$out" | grep -q "^## Hooks"             || fail "expected '## Hooks' in --heading output"
echo "$out" | grep -q "^### Gmail integration" || fail "H3 child of '## Hooks' was truncated"
pass "--section --heading 'Hooks' (H2) includes child H3 'Gmail integration'"

# ---------- 2b. H3 heading extraction stops before the next sibling H3 ----------

# Pick a section with at least two sibling H3s under the same H2 and verify
# extracting the first H3 does NOT include the second.
python3 - <<'PY' || exit 1
import re, subprocess, sys, json, pathlib

# Find a section with >= 2 sibling H3s under one H2 from the latest TOC index.
toc_path = pathlib.Path("versions/openclaw-docs.latest.toc.jsonl")
target_path, h3a, h3b = None, None, None
for line in toc_path.read_text().splitlines():
    row = json.loads(line)
    if len(row.get("h3", [])) >= 2:
        target_path = row["path"]
        h3a, h3b = row["h3"][0], row["h3"][1]
        break

if not target_path:
    print("SKIP: no section with >= 2 sibling H3s found", file=sys.stderr)
    sys.exit(0)

out = subprocess.run(
    ["python3", "scripts/lookup.py", "--section", target_path, "--heading", h3a],
    capture_output=True, text=True, check=True,
).stdout

if f"### {h3a}" not in out:
    print(f"FAIL: expected '### {h3a}' in output for {target_path}", file=sys.stderr)
    sys.exit(1)
if f"### {h3b}" in out:
    print(f"FAIL: H3 extraction of '{h3a}' leaked into sibling '### {h3b}'", file=sys.stderr)
    sys.exit(1)
print(f"PASS: --section --heading '{h3a}' (H3) stops before sibling H3 '{h3b}'")
PY

# ---------- 3. Index integrity: byte offsets resolve to # Section: lines ----------

python3 - <<'PY'
import json, pathlib, sys

base = pathlib.Path("versions")
checked = 0
# Validate every doc/index pair found in versions/. Post-migration this is
# typically just openclaw-docs.latest.{md,sections.jsonl}, but the loop
# transparently handles any in-flight pinned versions too.
for sec_file in sorted(base.glob("openclaw-docs.*.sections.jsonl")):
    stem = sec_file.name.removesuffix(".sections.jsonl")
    doc = base / f"{stem}.md"
    if not doc.exists():
        continue  # Pinned version not in tree (released-only); can't byte-check without fetching.
    data = doc.read_bytes()
    rows = sec_file.read_text().splitlines()
    if not rows:
        continue
    # Sample first, middle, last rows
    samples = {0, len(rows) // 2, len(rows) - 1}
    for i in sorted(samples):
        row = json.loads(rows[i])
        chunk = data[row["start_byte"] : row["end_byte"]].decode("utf-8")
        if not chunk.lstrip().startswith(f"# Section: {row['path']}"):
            print(f"FAIL: {stem} row {i}: byte slice doesn't start with `# Section: {row['path']}`", file=sys.stderr)
            sys.exit(1)
        checked += 1

if checked == 0:
    print("FAIL: no doc/index pairs found in versions/ — at minimum latest.* should be present", file=sys.stderr)
    sys.exit(1)
print(f"PASS: {checked} byte-offset sample(s) resolve to expected `# Section:` headers")
PY
