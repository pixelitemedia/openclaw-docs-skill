# CLAUDE.md

Guidance for AI assistants working **on this repository**.

> Working *with* OpenClaw docs (answering OpenClaw questions) is a different job — that is what
> `skills/openclaw-docs/SKILL.md` governs. Read that file instead if you are answering a question
> about OpenClaw itself. This file is about changing the code that produces those docs.

## What this repo is

A **documentation distribution pipeline**, not an application. It mirrors the upstream
[`openclaw/openclaw`](https://github.com/openclaw/openclaw) `docs/` tree daily and republishes it
through three consumer surfaces that all resolve to the same source of truth:

| Surface | Artifact | Consumer |
|---|---|---|
| Claude Code plugin | `.claude-plugin/plugin.json` + `.mcp.json` + `skills/` | `claude /plugin install openclaw-docs` |
| Portable skill | `skills/openclaw-docs/` (also shipped as a ZIP) | Codex, claude.ai, Manus, ChatGPT |
| Hosted MCP server | `supabase/functions/mcp` | Cursor, Cline, Continue, any MCP client |

The reason the project exists: **model memory of OpenClaw is unreliable** (OpenClaw ships CalVer
`YYYY.M.D` releases roughly daily), and models invent config fields that do not exist. Every design
decision below — the citation contract, `field_check`, fixed-string search — serves that goal.
Preserve it when you change things.

## Repository layout

```
.claude-plugin/plugin.json   Claude Code plugin manifest
.mcp.json                    MCP server registration (hosted HTTP endpoint)
.github/workflows/refresh.yml  The whole pipeline — daily cron + release publishing
ci/                          CI-only Python; never installed on a user's machine
  flatten_docs.py              upstream docs/**/*.md → one flattened .md + 2 JSONL indexes
  build_embeddings.py          chunker + field extractor + OpenRouter embedder + PostgREST upsert
  ci_ingest.py                 CI driver: chunk → embed → POST to the ingest Edge Function
  _render_index.py             regenerates versions/INDEX.md (no re-flatten)
  _sync_releases_manifest.py   `gh release list` JSON → versions/releases.json
skills/openclaw-docs/        The installable skill (== contents of openclaw-docs-skill.zip)
  SKILL.md                     skill manifest + the verification protocol agents must follow
  agents/openai.yaml           Codex UI metadata
  scripts/lookup.py            deterministic local retrieval CLI (--query / --toc / --section)
  scripts/update.py            in-place refresh; auto-detects git-clone vs ZIP install
  scripts/smoke_test.sh        the only test suite in the repo
  versions/                    GENERATED — see "Never hand-edit" below
supabase/                     Deno Edge Function source + fork setup notes
  functions/{versions,section,search,field-check,mcp,ingest}/index.ts
```

## Hard rules

1. **Never hand-edit anything under `skills/openclaw-docs/versions/`.** Every file there
   (`openclaw-docs.latest.md`, both `.jsonl` indexes, `INDEX.md`, `releases.json`) is CI output and
   is overwritten on the next run. Fix the generator in `ci/` instead.
2. **Only `latest.*` is committed.** Per-version triplets are `.gitignore`d and live as GitHub
   Release assets under tag `v<version>`. A URL of the form
   `raw.githubusercontent.com/.../versions/openclaw-docs.<version>.md` returns 404 by design.
3. **The three index files must stay mutually consistent.** `toc.jsonl` and `sections.jsonl` have
   one row per `# Section:` block, in the same order, with byte offsets that slice the `.md`
   correctly. `smoke_test.sh` enforces this; do not weaken that check.
4. **Python is standard-library only.** No `requirements.txt`, no `pip install` step in CI — every
   script uses `urllib.request`, `json`, `pathlib`. Keep it that way; the skill must run inside
   arbitrary agent sandboxes.
5. **Never write `According to docs for OpenClaw latest`.** The citation header must carry the
   concrete CalVer version, resolved from row 0 of the indexes (`_concrete_version()`) or from
   `resolve_version()` in Postgres.

## The pipeline (`.github/workflows/refresh.yml`)

Runs daily at 06:00 UTC, on `workflow_dispatch`, and on pushes to `main` that touch `ci/**`,
`skills/openclaw-docs/scripts/**`, or the workflow itself. Step order matters:

1. Checkout this repo **and** `openclaw/openclaw` into `upstream/`.
2. `ci/flatten_docs.py --repo upstream --skill-dir skills/openclaw-docs --no-pull`
   → writes `openclaw-docs.<ver>.{md,toc.jsonl,sections.jsonl}`, then copies the newest triplet over
   `latest.*` and re-renders `INDEX.md`.
3. `scripts/smoke_test.sh` — gates everything downstream.
4. `ci/ci_ingest.py` — chunk + embed + POST to Supabase. **Skips with a notice** if
   `OPENROUTER_API_KEY` / `SUPABASE_URL` / `INGEST_TOKEN` are unset, so forks still get a green run.
   Must run *before* step 5, which deletes the version-specific `.md` from the working tree.
5. Publish each per-version triplet to release `v<version>`, then `rm` those files locally.
6. `gh release list` → `_sync_releases_manifest.py` → `releases.json`.
7. `_render_index.py` — re-render `INDEX.md` against the fresh manifest.
8. Build and attach two ZIPs to the release (see below).
9. Commit `versions/` as `openclaw-docs-bot`, message `Refresh OpenClaw docs to v<version>`.

The version string is always read from `upstream/package.json` → `.version`.

### The two ZIPs

- `openclaw-docs-skill.zip` — slim, `SKILL.md` at root. For Codex / claude.ai / Manus.
- `openclaw-docs-plugin.zip` — full Claude Code layout (`.claude-plugin/`, `.mcp.json`, `skills/`).

### File-list duplication — update all three together

The set of runtime files an installed skill needs is written out in **three** places. Adding or
renaming a runtime file means editing all of them, or ZIP installs silently drift from git installs:

1. `refresh.yml` → "Build + upload distribution ZIPs" → the skill ZIP `zip -r` list
2. the same step's plugin ZIP `zip -r` list
3. `skills/openclaw-docs/scripts/update.py` → `RUNTIME_FILES`

## Backend (Supabase)

Postgres with `vector` + `pg_trgm`, two tables, six Deno Edge Functions.

| Table | Unique key (`on_conflict`) | Feeds |
|---|---|---|
| `docs_chunks` | `version,section_path,start_line` | `search`, `section`, `versions` |
| `docs_fields` | `version,field_name,context_path` | `field-check` |

All writes go through `POST /functions/v1/ingest` gated by an `X-Ingest-Token` header; it fails
closed while the token is still the `__INGEST_TOKEN__` placeholder. The five read functions deploy
with `verify_jwt: false` — public, no auth — and use the service-role key server-side.
`mcp/index.ts` is a thin JSON-RPC 2.0 wrapper that fans out to the other four over HTTP.

SQL helpers called by the functions: `resolve_version()`, `match_docs()` (hybrid cosine + trigram),
`find_field_mentions()`, `list_versions()`, `find_fields_by_context()`.

**Gotcha:** the migration SQL is *not* in this repo — `supabase/README.md` names the three
migrations but they were applied via the Supabase MCP `apply_migration` tool. If you change a table
shape you must also apply the migration out-of-band and note it in `supabase/README.md`.

Embeddings: `openai/text-embedding-3-large` at 3072 dims, via OpenRouter's OpenAI-compatible
`/v1/embeddings`. Changing model or dims invalidates every stored vector — it requires a re-ingest
of all versions (`FORCE_REINGEST=1`) and an index rebuild, not just a config edit.

## Local development

Everything below runs from the repo root with plain `python3`; there is nothing to install. CI pins 3.12.

```bash
# Regenerate docs + indexes against a local clone of upstream
git clone --depth 1 https://github.com/openclaw/openclaw /tmp/openclaw
python3 ci/flatten_docs.py --repo /tmp/openclaw --skill-dir skills/openclaw-docs --no-pull

# The test suite (also the CI gate) — run this after ANY change to lookup.py or flatten_docs.py
cd skills/openclaw-docs && bash scripts/smoke_test.sh

# Exercise the retrieval CLI
python3 skills/openclaw-docs/scripts/lookup.py --query "passEnv"
python3 skills/openclaw-docs/scripts/lookup.py --toc "telegram setup"
python3 skills/openclaw-docs/scripts/lookup.py --section gateway/secrets.md --heading "Provider config"

# Exercise the hosted MCP server without installing anything
curl -sX POST https://gzfdvhuglftjnlhlcgjj.supabase.co/functions/v1/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Embedding phases can run independently (useful when debugging one stage)
python3 ci/build_embeddings.py chunk --version latest --skill-dir skills/openclaw-docs --out /tmp/c.jsonl
python3 ci/build_embeddings.py embed --in /tmp/c.jsonl --out /tmp/e.jsonl --resume
python3 ci/build_embeddings.py upsert --in /tmp/e.jsonl
```

`smoke_test.sh` resolves its own location (it `cd`s to `$(dirname $0)/..`), so it runs from any cwd.
It asserts: citation headers carry a concrete version in all three lookup modes; `--heading` on an H2 includes
child H3s while an H3 stops at its sibling; and sampled byte offsets land on `# Section:` lines.

## Conventions that matter

- **CalVer, sorted as tuples.** `2026.5.10` > `2026.5.6`. Never sort version strings lexically —
  `_version_key()`, `_version_sort_key()`, and `compareVersions()` in `versions/index.ts` all exist
  for this. Reuse them rather than writing a fourth.
- **Fixed-string search by default.** OpenClaw identifiers contain `.`, `-`, `/`, `@`, all regex
  metacharacters. `lookup.py --query` is literal unless `--regex` is passed; shell fallbacks must use
  `grep -F`.
- **Never full-read the flattened doc.** It is ~11 MB. `--section` seeks by byte offset for exactly
  this reason. Any new retrieval path should do the same.
- **Citation contract.** Every retrieval surface — CLI and Edge Function alike — emits
  `According to docs for OpenClaw <concrete-version> — <section-path>`. Keep the shape identical
  across surfaces; `smoke_test.sh` regex-matches it.
- **Two curation knobs, both in generators.** `EXCLUDE_DIRS` in `flatten_docs.py` (drops i18n,
  images, `.generated`) and `CANONICAL_SCHEMA_PATHS` in `build_embeddings.py` (restricts which
  sections feed `docs_fields`, so `field_check` stays high-precision). Widening the latter makes
  `field_check` noisier — the whole point is that a `false` result is trustworthy.
- **Idempotency everywhere.** Re-running ingest is a no-op via `Prefer: resolution=merge-duplicates`
  plus the unique keys; `ci_ingest.py` also pre-checks whether the version is already present.
- **Tone in `SKILL.md` is deliberately blunt.** The imperative "never / you MUST verify" phrasing and
  the hallucination-trap table are load-bearing prompt engineering. Don't soften them into neutral
  documentation prose. The same applies to the `WHEN TO CALL` blocks in `mcp/index.ts` tool
  descriptions — those are read by models as routing rules.

## Known rough edges

- `update.py`'s ZIP path lists `README.md` in `RUNTIME_FILES`, but no `README.md` exists under
  `skills/openclaw-docs/`, so the fetch 404s and `update_via_curl()` exits 1. Either drop it from the
  list or add a skill-level README.
- `supabase/README.md` and the `build_embeddings.py` docstring still reference `scripts/ci_ingest.py`
  and `scripts/build_embeddings.py`; both moved to `ci/`.
- `build_embeddings.py:extract_fields()` is dead code — `extract_field_records()` is the function
  actually used by `ci_ingest.py` and `cmd_upsert`.
- `versions/index.ts` builds a `distinct_versions_with_counts` RPC URL that it never calls, then
  falls back to a full `SELECT version` and counts in JS.

## Secrets and environment

Set as both GitHub Actions secrets and Supabase Edge Function secrets (`supabase/README.md` step 5–6):

| Name | Used by | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | `ci_ingest.py`, `search` | embedding calls |
| `SUPABASE_URL` | CI, all functions | `https://<ref>.supabase.co` |
| `INGEST_TOKEN` | `ci_ingest.py`, `ingest` | shared secret; must match on both sides |
| `SUPABASE_QUERY_KEY` | `ci_ingest.py` | optional; anon key for the already-ingested precheck |
| `SUPABASE_SERVICE_ROLE_KEY` | Edge Functions | auto-injected by Supabase |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMS` | CI, `search` | optional overrides; must match on both sides |
| `FORCE_REINGEST=1` | `ci_ingest.py` | bypass the idempotency precheck |
| `OPENCLAW_DOCS_RELEASE_BASE` | `lookup.py` | fork override for release-asset fetches |
| `OPENCLAW_DOCS_RAW_BASE` | `update.py` | fork override for raw-file refresh |

Never commit any of these. The Supabase project ref appears in URLs throughout the repo and is
public by design — that is not a secret; the service-role key and ingest token are.

## Making changes

- Branch from `main`; CI's bot owns the `Refresh OpenClaw docs to v<version>` commits on `main`, so
  rebase rather than fight it if your branch goes stale.
- Touching `ci/**` or `skills/openclaw-docs/scripts/**` triggers a full refresh run on push to
  `main` — a broken generator republishes bad docs to every consumer within minutes. Run
  `smoke_test.sh` locally first.
- Changing the flattened-doc format (section headers, heading levels) breaks `lookup.py`,
  `build_embeddings.py`'s chunker, `section/index.ts`'s `trimToHeading`, and every stored embedding
  at once. Treat `# Section: <path>` + preserved H2/H3 as a frozen wire format.
- Forking for other docs: swap `--repo` in the workflow, the Supabase project ref, and the
  `pixelitemedia/openclaw-docs-skill` slug (it is hardcoded as a default in `flatten_docs.py`,
  `lookup.py`, and `update.py`).
