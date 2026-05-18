# OpenClaw Docs — Claude Code plugin

Authoritative, daily-refreshed [OpenClaw](https://github.com/openclaw/openclaw) docs for any AI agent.

One plugin install gives Claude Code (or any MCP-capable AI) **everything**:

- a hosted **MCP server** with four tools — vector + trigram search, structural `field_check` (prevents hallucinated config fields), section extraction, version listing
- a local **Claude skill** with the flattened docs + retrieval CLI, for offline / no-MCP use
- a stable **citation contract** — every tool response embeds the concrete OpenClaw version + section path

## Install — pick your harness

Different AI tools have different plugin/skill conventions; one artifact can't natively cover them all. The matrix below tells you which file + which path per harness. **All paths converge on the same docs** — the differences are surface-level.

### Anthropic Claude Code

The full plugin: skill + auto-registered MCP server in one install.

```bash
# Recommended — plugin install (sets up MCP server automatically):
claude /plugin marketplace add pixelitemedia/openclaw-docs-skill
claude /plugin install openclaw-docs

# — or, git clone if your Claude Code build doesn't have plugin commands:
git clone https://github.com/pixelitemedia/openclaw-docs-skill ~/.claude/plugins/openclaw-docs

# — or, downloadable plugin ZIP (no git required):
curl -sL https://github.com/pixelitemedia/openclaw-docs-skill/releases/latest/download/openclaw-docs-plugin.zip -o /tmp/p.zip
unzip /tmp/p.zip -d ~/.claude/plugins/openclaw-docs
```

Verify:

```bash
claude /plugin list    # should show openclaw-docs
claude /mcp list       # should include openclaw-docs HTTP server
```

### OpenAI Codex CLI

Codex reads `~/.codex/skills/<name>/SKILL.md` directly — no plugin manifest. Download the slim skill ZIP and extract:

```bash
mkdir -p ~/.codex/skills/openclaw-docs
curl -sL https://github.com/pixelitemedia/openclaw-docs-skill/releases/latest/download/openclaw-docs-skill.zip \
  | bsdtar -xf- -C ~/.codex/skills/openclaw-docs
```

The skill ZIP also includes `agents/openai.yaml` for Codex's UI metadata.

### Anthropic Skills (claude.ai web) / Manus

Both accept Skill ZIP uploads via their UI. Download:

```
https://github.com/pixelitemedia/openclaw-docs-skill/releases/latest/download/openclaw-docs-skill.zip
```

Then upload via the harness's "Add skill" / "Upload skill" button.

### ChatGPT Custom GPT

ChatGPT doesn't have a skill concept — it uses knowledge files. Two options:

- **Easy:** Upload `openclaw-docs.latest.md` as a knowledge file. Get it from <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/skills/openclaw-docs/versions/openclaw-docs.latest.md>.
- **Better:** Build a Custom GPT with an Action calling the MCP endpoint at `https://gzfdvhuglftjnlhlcgjj.supabase.co/functions/v1/mcp` (the four tools are exposed via JSON-RPC; map them as Action operations).

### Cursor / Cline / Continue / Windsurf (any MCP-capable tool)

Add to your tool's MCP config:

```json
{
  "mcpServers": {
    "openclaw-docs": {
      "type": "http",
      "url": "https://gzfdvhuglftjnlhlcgjj.supabase.co/functions/v1/mcp"
    }
  }
}
```

No local install needed. The four tools (`openclaw_field_check`, `openclaw_search`, `openclaw_section`, `openclaw_versions`) appear in your tool's MCP tool list.

### Direct API consumers (Claude API, OpenAI API, raw SDKs)

Two options:

- Fetch the latest markdown as a string and inject as context:
  ```python
  import httpx
  docs = httpx.get("https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/skills/openclaw-docs/versions/openclaw-docs.latest.md").text
  # use in system prompt or RAG
  ```
- Call the MCP endpoint's tools directly (JSON-RPC 2.0 over HTTPS):
  ```bash
  curl -X POST https://gzfdvhuglftjnlhlcgjj.supabase.co/functions/v1/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"openclaw_field_check","arguments":{"field_name":"env","context_path":"secrets.providers"}}}'
  ```

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
