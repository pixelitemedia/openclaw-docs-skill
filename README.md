# OpenClaw Docs — Claude Code plugin

Authoritative, daily-refreshed [OpenClaw](https://github.com/openclaw/openclaw) docs for any AI agent.

One plugin install gives Claude Code (or any MCP-capable AI) **everything**:

- a hosted **MCP server** with four tools — vector + trigram search, structural `field_check` (prevents hallucinated config fields), section extraction, version listing
- a local **Claude skill** with the flattened docs + retrieval CLI, for offline / no-MCP use
- a stable **citation contract** — every tool response embeds the concrete OpenClaw version + section path

## Install (Claude Code)

```bash
# Add this repo as a plugin marketplace, then install:
claude /plugin marketplace add pixelitemedia/openclaw-docs-skill
claude /plugin install openclaw-docs

# — or, manual git clone if your Claude Code build doesn't have plugin commands yet:
git clone https://github.com/pixelitemedia/openclaw-docs-skill ~/.claude/plugins/openclaw-docs
```

That's it. Claude Code reads `.claude-plugin/plugin.json` (plugin metadata), `.mcp.json` (registers the hosted MCP server automatically), and `skills/openclaw-docs/SKILL.md` (registers the skill). Next time you ask about OpenClaw, the model has all four MCP tools plus the local skill on hand.

To check it landed:

```bash
# These commands let you confirm the plugin is registered
claude /plugin list
claude /mcp list   # should include openclaw-docs
```

## Install (other AI harnesses)

| Harness | Path |
|---|---|
| **OpenAI Codex** | `git clone … ~/.codex/skills/openclaw-docs` — Codex reads SKILL.md from `skills/openclaw-docs/` directly. Plugin manifest is ignored, but the skill works. |
| **Anthropic Skills (claude.ai)**, **Manus**, **ChatGPT Custom GPT** | Download the slim skill ZIP from the latest GitHub Release (`openclaw-docs-skill.zip`) — it contains only `SKILL.md`, `agents/`, `scripts/`, `versions/`. Upload via the harness's skill-upload UI. |
| **Cursor / Cline / Continue / Windsurf** | Drop the MCP URL into your tool's `mcp.json`: `{ "openclaw-docs": { "type": "http", "url": "https://gzfdvhuglftjnlhlcgjj.supabase.co/functions/v1/mcp" } }` |

## The MCP server

```
https://gzfdvhuglftjnlhlcgjj.supabase.co/functions/v1/mcp
```

Public, no-auth, JSON-RPC 2.0 (`type: http`). Four tools:

| Tool | Use for |
|---|---|
| `openclaw_field_check` | **Call before stating any OpenClaw config field exists.** Returns `{ exists, matches, real_alternatives }`. Structural guard against hallucinated fields. |
| `openclaw_search` | Open-ended questions. 3072-dim vector + trigram hybrid; returns ranked snippets. |
| `openclaw_section` | Extract a known section by source path; optionally narrow to one heading. |
| `openclaw_versions` | List indexed versions + resolve `latest`. |

All responses include a citation header: `According to docs for OpenClaw 2026.5.6 — gateway/secrets.md`.

## Architecture

```
                                ┌────────────────────────┐
   GitHub repo: openclaw/openclaw │  upstream docs        │
                                └──────────┬─────────────┘
                                           │ daily
                                           ▼
              ┌────────────────────────────────────────────┐
              │  CI workflow (this repo, .github/workflows) │
              │   ci/flatten_docs.py  →  versioned md       │
              │   ci/ci_ingest.py     →  embed via OpenRouter│
              │                       →  POST to Supabase    │
              └─────────┬──────────────────────┬────────────┘
                        │                      │
              ┌─────────▼──────┐    ┌─────────▼──────────────┐
              │ GitHub Releases│    │ Supabase Postgres       │
              │ (versioned MD  │    │ docs_chunks (6,500 rows)│
              │  + JSONL +     │    │ docs_fields (1,993)     │
              │  skill ZIP)    │    │ pgvector + pg_trgm      │
              └────────┬───────┘    └─────────┬───────────────┘
                       │                      │
              ┌────────▼────────┐    ┌────────▼─────────────────┐
              │ skills/openclaw-│    │  Edge Functions          │
              │ docs/ (in main)│    │  /versions /section      │
              │ — latest.* +   │    │  /search /field-check    │
              │   indexes      │    │  /mcp (JSON-RPC wrapper) │
              │ — lookup.py    │    │  /ingest (auth, CI-only) │
              └────────┬───────┘    └────────┬─────────────────┘
                       │                      │
                       └──────┬───────────────┘
                              ▼
                  ┌──────────────────────────┐
                  │ AI clients               │
                  │ Claude Code / Codex /    │
                  │ Cursor / Cline / claude.ai│
                  └──────────────────────────┘
```

## Files in this repo

```
.
├── .claude-plugin/plugin.json         ← plugin manifest (Claude Code reads this)
├── .mcp.json                          ← MCP server config (registered on install)
├── skills/openclaw-docs/               ← the skill itself (also the ZIP contents)
│   ├── SKILL.md                       ← skill manifest
│   ├── agents/openai.yaml             ← Codex skill UI metadata
│   ├── scripts/
│   │   ├── lookup.py                  ← deterministic local retrieval CLI
│   │   ├── update.py                  ← in-place refresh (auto-detects git/ZIP)
│   │   └── smoke_test.sh              ← regression guard
│   └── versions/
│       ├── INDEX.md                   ← rendered list of versions + Release URLs
│       ├── openclaw-docs.latest.md         ← flattened docs (newest)
│       ├── openclaw-docs.latest.toc.jsonl  ← TOC: path + H2/H3 + line range + keywords
│       ├── openclaw-docs.latest.sections.jsonl  ← line + byte ranges per section
│       └── releases.json              ← manifest of all published versions
├── ci/                                ← CI-only scripts (not installed)
│   ├── flatten_docs.py                ← walks upstream/docs → flattened MD + indexes
│   ├── build_embeddings.py            ← chunker + OpenRouter embedder + upsert
│   ├── ci_ingest.py                   ← CI step: chunk + embed + POST to ingest
│   ├── _render_index.py               ← regenerates INDEX.md from releases.json
│   └── _sync_releases_manifest.py     ← maintains releases.json from gh API
├── supabase/                          ← Edge Function source + setup notes
│   ├── README.md
│   └── functions/{versions,section,field-check,search,mcp,ingest}/index.ts
├── .github/workflows/refresh.yml      ← daily cron
└── README.md                          ← this file
```

## URLs (raw access, no install required)

For tools that consume markdown directly via URL:

| Resource | URL |
|---|---|
| Latest flattened doc | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/skills/openclaw-docs/versions/openclaw-docs.latest.md> |
| Latest TOC index | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/skills/openclaw-docs/versions/openclaw-docs.latest.toc.jsonl> |
| Latest section index | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/skills/openclaw-docs/versions/openclaw-docs.latest.sections.jsonl> |
| Pinned version (release asset) | `https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v<version>/openclaw-docs.<version>.md` |
| Skill ZIP (for non-plugin harnesses) | `https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v<version>/openclaw-docs-skill.zip` |

Only `latest.*` is committed to `main`. Historical versions are **GitHub Release** assets — fetching `…/main/versions/openclaw-docs.<version>.md` returns 404 (use the release URL).

## Forking this for your own docs

See [`supabase/README.md`](supabase/README.md) for the setup steps: enable extensions, apply migrations, deploy Edge Functions, configure GitHub Actions secrets. The repository is structured so a fork only needs to swap the upstream docs source (`ci/flatten_docs.py` `--repo` argument) and the Supabase project ID.

## License

MIT
