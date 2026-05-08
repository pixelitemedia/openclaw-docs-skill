# OpenClaw Docs Skill

A platform-agnostic, versioned snapshot of the official [OpenClaw](https://github.com/openclaw/openclaw) documentation, designed to be loaded into any AI coding assistant or LLM context.

A GitHub Actions workflow runs daily — it clones upstream, flattens `docs/**/*.md` into a single file, version-prefixes it (`openclaw-docs.<version>.md`), and refreshes `openclaw-docs.latest.md`. Consumers don't need to run anything; they just point at the raw URLs or `git pull` this repo.

OpenClaw uses CalVer (`YYYY.M.D`) and ships frequently, so pinning to the exact running version avoids stale answers.

## Files in this repo

```
.
├── SKILL.md                          ← Anthropic Claude Skill manifest
├── flatten_docs.py                   ← refresh script
├── .github/workflows/refresh.yml     ← daily auto-refresh
└── versions/
    ├── INDEX.md                      ← list of stored versions, newest first
    ├── openclaw-docs.latest.md       ← always a copy of the newest version file
    └── openclaw-docs.<version>.md    ← one file per snapshotted release
```

`openclaw-docs.latest.md` is a real file (not a symlink) so it can be fetched as raw bytes from `raw.githubusercontent.com` and uploaded into hosted chat products / fed into APIs / read by Windows checkouts.

## Raw URLs (for any consumer)

For interactive / one-off use, GitHub raw URLs are fine:

- Latest: <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/openclaw-docs.latest.md>
- Pinned: `https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/openclaw-docs.<version>.md`
- Index of all stored versions: <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/INDEX.md>

For automated / repeated fetches, prefer **jsDelivr** — same files, properly CDN'd, no per-IP rate limits:

- Latest: <https://cdn.jsdelivr.net/gh/pixelitemedia/openclaw-docs-skill@main/versions/openclaw-docs.latest.md>
- Pinned: `https://cdn.jsdelivr.net/gh/pixelitemedia/openclaw-docs-skill@main/versions/openclaw-docs.<version>.md`
- Index: <https://cdn.jsdelivr.net/gh/pixelitemedia/openclaw-docs-skill@main/versions/INDEX.md>

jsDelivr caches up to 12 hours and serves from a global CDN — better at scale, free for both you and consumers.

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
