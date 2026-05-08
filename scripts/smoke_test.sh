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

# ---------- 2. Heading extraction includes child H3s for an H2 match ----------

out=$(python3 scripts/lookup.py --section gateway/configuration-reference.md --heading "Hooks")
echo "$out" | grep -q "^## Hooks"             || fail "expected '## Hooks' in --heading output"
echo "$out" | grep -q "^### Gmail integration" || fail "H3 child of '## Hooks' was truncated"
pass "--section --heading 'Hooks' (H2) includes child H3 'Gmail integration'"

# ---------- 3. Index integrity: byte offsets resolve to # Section: lines ----------

python3 - <<'PY'
import json, pathlib, sys

base = pathlib.Path("versions")
checked = 0
for sec_file in base.glob("openclaw-docs.*.sections.jsonl"):
    if "latest" in sec_file.name:
        continue  # latest.* is a copy of a versioned file, validated via that
    version = sec_file.name.removeprefix("openclaw-docs.").removesuffix(".sections.jsonl")
    doc = base / f"openclaw-docs.{version}.md"
    if not doc.exists():
        # Released-only version (typical post-migration). Skip the byte check —
        # we'd need to fetch the release asset, which the smoke test doesn't do.
        continue
    data = doc.read_bytes()
    rows = sec_file.read_text().splitlines()
    # Sample first, middle, last rows
    samples = {0, len(rows) // 2, len(rows) - 1}
    for i in sorted(samples):
        row = json.loads(rows[i])
        chunk = data[row["start_byte"] : row["end_byte"]].decode("utf-8")
        if not chunk.lstrip().startswith(f"# Section: {row['path']}"):
            print(f"FAIL: {version} row {i}: byte slice doesn't start with `# Section: {row['path']}`", file=sys.stderr)
            sys.exit(1)
        checked += 1

if checked == 0:
    print("SKIP: no in-tree version docs to byte-check (post-migration; releases are the source of truth)")
else:
    print(f"PASS: {checked} byte-offset sample(s) resolve to expected `# Section:` headers")
PY
