# OpenClaw Docs Skill

A platform-agnostic, versioned, semantically-indexed mirror of the official [OpenClaw](https://github.com/openclaw/openclaw) docs, designed to be loaded into any AI coding assistant or LLM context.

Two consumption surfaces:

1. **★ Hosted MCP server** (best path for AI tools that support MCP — Claude, Cursor, Cline, Continue, ChatGPT Apps): vector + trigram search, structural field-check, section extraction, version listing. No install — paste one URL.
2. **Local skill ZIP / git clone**: flattened markdown + JSONL indexes + `scripts/lookup.py` CLI. For Claude Code, Codex CLI, and any LLM context that loads markdown files.

OpenClaw uses CalVer (`YYYY.M.D`) and ships frequently. A GitHub Actions workflow runs daily, re-flattens the docs, publishes a versioned GitHub Release, embeds 6,500+ chunks into Supabase (pgvector + pg_trgm), and refreshes `openclaw-docs.latest.*` in `main`. Pin to a specific version for reproducibility, or use `latest` for the moving alias.

## ★ MCP server — one URL, four tools

```
https://gzfdvhuglftjnlhlcgjj.supabase.co/functions/v1/mcp
```

Public, no-auth, JSON-RPC 2.0. Drop it into your AI tool's MCP config:

**Claude Code / Claude Desktop** (`~/.claude.json` or via the Customize → MCP panel):

```json
{
  "mcpServers": {
    "openclaw-docs": {
      "url": "https://gzfdvhuglftjnlhlcgjj.supabase.co/functions/v1/mcp",
      "type": "http"
    }
  }
}
```

**Cursor** (`~/.cursor/mcp.json` or per-project `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "openclaw-docs": {
      "url": "https://gzfdvhuglftjnlhlcgjj.supabase.co/functions/v1/mcp"
    }
  }
}
```

**Cline / Continue / Windsurf**: same URL, same JSON pattern in their MCP config.

The server exposes:

| Tool | Use for |
|---|---|
| `openclaw_field_check` | Verifying a config field, CLI flag, or identifier exists in the schema. **Call before writing OpenClaw config.** Returns `{ exists, matches, real_alternatives }`. |
| `openclaw_search` | Open-ended questions ("how do I set up Telegram?"). Hybrid 3072-dim vector + trigram, returns ranked snippets. |
| `openclaw_section` | Extracting a known section by path, optionally narrowed to one heading. |
| `openclaw_versions` | Listing indexed versions + resolving `latest`. |

All tools cite their docs version + section path in the response. The `openclaw_field_check` tool is the structural guard that prevents the most common failure mode: hallucinated field names (e.g. `env` on exec providers — the real field is `passEnv`).

## Local install (alternative — no MCP support, or offline)

For environments where MCP isn't available (Claude Code with older CLI, custom agents, regulated environments): clone the skill ZIP and point your AI tool at the local markdown.

## Files in this repo

```
.
├── SKILL.md                              ← skill manifest (Claude Code, Codex, etc.)
├── agents/openai.yaml                    ← OpenAI Codex UI metadata
├── flatten_docs.py                       ← CI refresh + index generator
├── scripts/
│   └── lookup.py                         ← deterministic retrieval CLI
├── .github/workflows/refresh.yml         ← daily auto-refresh + release publish
└── versions/
    ├── INDEX.md                          ← list of stored versions + Release URL pattern
    ├── openclaw-docs.latest.md           ← flattened docs (newest)
    ├── openclaw-docs.latest.toc.jsonl    ← TOC: section + H2/H3 + line range + keywords
    └── openclaw-docs.latest.sections.jsonl  ← line + byte ranges per section
```

Only the `latest.*` triplet lives in `main`. **Historical version snapshots are published as [GitHub Release](https://github.com/pixelitemedia/openclaw-docs-skill/releases) assets** — keeps the skill repo small forever (~6 MB) regardless of how many versions accumulate.

Each version triplet:
- `.md` — flattened doc (~5–6 MB)
- `.toc.jsonl` — TOC: routing index for broad queries (~300 KB)
- `.sections.jsonl` — line + byte ranges per section, for fast extraction or HTTP `Range` requests (~100 KB)

Stable URL pattern for any version (e.g. for Custom GPTs, vector pipelines, manual download):

```
https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v<version>/openclaw-docs.<version>.<suffix>
```

`scripts/lookup.py` fetches and caches non-latest versions automatically.

## Querying — `scripts/lookup.py`

Deterministic retrieval over the indexes. Returns compact Markdown that an agent can paste into context.

```bash
# Exact-term search (fixed-string by default; OpenClaw identifiers have regex metachars)
python3 scripts/lookup.py --query "gateway.mode"
python3 scripts/lookup.py --query "OPENCLAW_LIVE_TEST" --context-lines 8
python3 scripts/lookup.py --query "createPluginEntry" --version 2026.5.6

# Broad TOC routing — returns ranked candidate sections
python3 scripts/lookup.py --toc "plugin sdk lifecycle"
python3 scripts/lookup.py --toc "telegram setup"

# Section extraction (full section, or trimmed by heading)
python3 scripts/lookup.py --section plugins/manifest.md
python3 scripts/lookup.py --section gateway/configuration-reference.md --heading "Hooks"
```

`--version latest` is the default; pass `--version 2026.5.6` to pin. **Output always cites the concrete version** — even when called with `--version latest`, the script resolves through the indexes and emits a header like:

```markdown
# According to docs for OpenClaw 2026.5.6 — `gateway/configuration-reference.md`
```

Adjacent `--query` hits in the same section are merged into one excerpt to save context budget.

## Quick install (any harness that accepts skill ZIPs)

The simplest path. Download:

```
https://github.com/pixelitemedia/openclaw-docs-skill/releases/latest/download/openclaw-docs-skill.zip
```

Upload to your harness as a skill — works in:

- **Claude Skills** (claude.ai → Settings → Skills → Add)
- **Manus** (Skills → Upload ZIP, or paste the GitHub URL)
- **OpenAI Codex** (extract into `~/.codex/skills/openclaw-docs/` or `~/.agents/skills/openclaw-docs/`)
- **Anthropic Claude Code** (extract into `~/.claude/skills/openclaw-docs/`)

The ZIP is self-contained: SKILL.md, agents/openai.yaml, lookup script, latest docs + indexes, version manifest. ~6 MB. No further setup.

To refresh the docs in an installed skill, run:

```bash
python3 scripts/update.py
```

`update.py` auto-detects whether the skill was installed via `git clone` or ZIP extraction and uses the right refresh path (`git pull` or raw-GitHub fetch). Run it whenever you want fresh docs — the script is idempotent.

## URLs (for any consumer)

**Latest** — committed to `main`, fetch from raw GitHub or jsDelivr:

| Asset | URL |
|---|---|
| Latest doc | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/openclaw-docs.latest.md> |
| Latest TOC | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/openclaw-docs.latest.toc.jsonl> |
| Latest sections | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/openclaw-docs.latest.sections.jsonl> |
| Index | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/INDEX.md> |
| jsDelivr (CDN'd, better at scale) | <https://cdn.jsdelivr.net/gh/pixelitemedia/openclaw-docs-skill@main/versions/openclaw-docs.latest.md> |

**Pinned versions** — published as GitHub Release assets, **not** in `main`:

```
https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v<version>/openclaw-docs.<version>.md
https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v<version>/openclaw-docs.<version>.toc.jsonl
https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v<version>/openclaw-docs.<version>.sections.jsonl
```

> ⚠️ Pinned URLs of the form `…/main/versions/openclaw-docs.<version>.md` (raw GitHub or jsDelivr `@main`) **return 404** — only `latest.*` lives in `main`. Always use the release-asset URLs above for pinned access.

`scripts/lookup.py` resolves both surfaces transparently: `--version latest` reads the in-tree files, any other `--version` fetches from the matching release.

---

## Installation by platform

### Anthropic — Claude Code (CLI)

Clone into the user-global skills directory on each machine that runs Claude Code:

```bash
git clone https://github.com/pixelitemedia/openclaw-docs-skill.git \
  ~/.claude/skills/openclaw-docs
```

To stay current, periodically `git -C ~/.claude/skills/openclaw-docs pull` (set up a cron / launchd job, or pull manually before working on OpenClaw).

For project-scoped use instead of user-global:

```bash
cd <your-project>
git submodule add https://github.com/pixelitemedia/openclaw-docs-skill.git \
  .claude/skills/openclaw-docs
```

Claude Code auto-discovers `SKILL.md` and the skill triggers when OpenClaw questions come up.

### OpenAI — Codex (CLI)

Codex uses the same `SKILL.md` format as Claude Code, so the same repo works as-is. Codex additionally reads `agents/openai.yaml` (included in this repo) for its UI affordances (display name, brand color, default prompt).

Clone into Codex's user-global skills directory:

```bash
git clone https://github.com/pixelitemedia/openclaw-docs-skill.git \
  ~/.codex/skills/openclaw-docs
```

(The Codex docs also list `~/.agents/skills/` as a discovery path. `~/.codex/skills/` is `$CODEX_HOME/skills` which most installs use; pick whichever your install prefers.)

For project-scoped use, Codex looks at `.agents/skills/` walking up from the cwd:

```bash
cd <your-project>
git submodule add https://github.com/pixelitemedia/openclaw-docs-skill.git \
  .agents/skills/openclaw-docs
```

### Anthropic — Claude.ai (web / desktop / mobile)

Claude.ai cannot read your filesystem, so feed the docs in via Projects or Skills:

1. Download the latest flattened doc:
   ```bash
   curl -O https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/openclaw-docs.latest.md
   ```
2. In Claude.ai, create a Project (or open an existing one) → upload `openclaw-docs.latest.md` as a Project file.
3. Re-upload after notable upstream changes. There's no automatic sync into Claude.ai.

For the Claude Skills product feature, upload the same file as a skill resource and use the contents of `SKILL.md` here as the skill description.

### Anthropic — Claude API / Agent SDK

```python
import httpx, anthropic

DOCS_URL = "https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/openclaw-docs.latest.md"
docs = httpx.get(DOCS_URL).text  # 5–6 MB

client = anthropic.Anthropic()
client.messages.create(
    model="claude-sonnet-4-5",
    system=[
        {"type": "text",
         "text": f"You answer OpenClaw questions using these docs. Always preface answers with 'According to OpenClaw docs:'.\n\n{docs}",
         "cache_control": {"type": "ephemeral"}},  # cache the big doc
    ],
    messages=[{"role": "user", "content": "How do I configure gateway.mode?"}],
    max_tokens=1024,
)
```

Use prompt caching — the doc is large (5+ MB) and stable across requests.

### OpenAI — ChatGPT (web / desktop / mobile)

Two options:

**Custom GPT** (recommended): create a Custom GPT, upload `openclaw-docs.latest.md` as a Knowledge file, and put a one-liner in the instructions: "You are an OpenClaw assistant. Always cite sections from the uploaded docs and preface answers with 'According to OpenClaw docs:'." Re-upload the file when upstream changes substantially.

**Project files**: in a ChatGPT Project (Plus/Team/Enterprise), upload the file directly. Same re-upload workflow.

### OpenAI — Assistants API / Responses API

Upload the doc once, then attach it to your assistant or thread as a `file_search` tool:

```python
from openai import OpenAI
client = OpenAI()

# One-time upload
with open("openclaw-docs.latest.md", "rb") as f:
    file = client.files.create(file=f, purpose="assistants")

# Create a vector store with the doc
vs = client.vector_stores.create(name="openclaw-docs", file_ids=[file.id])

# Attach to an assistant
client.beta.assistants.create(
    model="gpt-4o",
    instructions="You answer OpenClaw questions using the provided docs. "
                 "Always preface answers with 'According to OpenClaw docs:'.",
    tools=[{"type": "file_search"}],
    tool_resources={"file_search": {"vector_store_ids": [vs.id]}},
)
```

To refresh, `curl` the latest URL, upload a new file, and swap it into the vector store.

### OpenAI — Responses API (chat completions, single-shot)

```python
from openai import OpenAI
import httpx

DOCS_URL = "https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/openclaw-docs.latest.md"
docs = httpx.get(DOCS_URL).text

OpenAI().chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system",
         "content": f"You answer OpenClaw questions using these docs. Preface answers with 'According to OpenClaw docs:'.\n\n{docs}"},
        {"role": "user", "content": "How do I configure gateway.mode?"},
    ],
)
```

For repeated use, prefer the file_search tool above so you don't pay for the doc tokens on every call.

### Cursor / Windsurf / Cline / other VS-Code-style assistants

Most accept either project rules files or arbitrary docs included in context:

- Drop `versions/openclaw-docs.latest.md` into your project (e.g. `.cursor/openclaw-docs.md`) and reference it in `.cursorrules` / `.windsurfrules`:

  ```
  When answering OpenClaw questions, consult @openclaw-docs.md and preface answers with "According to OpenClaw docs:".
  ```

- Or clone this repo as a sibling and `@`-mention the file path in chat.

### Generic LLM apps / RAG pipelines

Treat `openclaw-docs.latest.md` as a single source document. Recommended chunking: split on the `# Section: <rel-path>` headers — each chunk maps cleanly back to an upstream doc file and survives semantic search well.

```bash
curl -o openclaw-docs.md https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/openclaw-docs.latest.md
# split, embed, index in your vector store of choice
```

Re-fetch on a schedule (daily matches the upstream cadence).

---

## Refresh

**Automatic:** GitHub Actions runs daily at 06:00 UTC. The job exits cleanly without committing if upstream hasn't changed.

**Manual (anyone with repo write access):** Actions tab → "Refresh OpenClaw docs" → Run workflow.

**Local dry run:**

```bash
python3 flatten_docs.py --repo /path/to/openclaw/clone --skill-dir .
```

Pin to a specific tag:

```bash
cd /path/to/openclaw/clone
git checkout v2026.3.28
python3 flatten_docs.py --no-pull --skill-dir .
```

---

## Versioning policy

Every refresh produces `openclaw-docs.<version>.md` named after the `version` field in upstream `package.json`. Old version files are kept indefinitely so you can pin to any past release. `openclaw-docs.latest.md` is always a copy of the highest-version file in the directory (numerically version-sorted, not lexically — `2026.5.10` beats `2026.5.6`).
