---
name: openclaw-docs
description: Authoritative reference for OpenClaw — points to the public, daily-refreshed flattened docs at github.com/pixelitemedia/openclaw-docs-skill. Trigger when the user asks anything about OpenClaw features, config, CLI, gateway, plugin SDK, channels, providers, or is debugging a running OpenClaw instance. Use to ground answers in current docs instead of model memory.
---

# OpenClaw Docs

## What this skill is

A pointer. The actual OpenClaw documentation is mirrored, flattened, and version-snapshotted by GitHub Actions in <https://github.com/pixelitemedia/openclaw-docs-skill>. This skill teaches you (the assistant) where to find it, which version to pick, and how to cite it.

You do **not** need to run any flatten / sync script. CI does that upstream. Your job is consumption.

## Where the docs live

**Public URLs** (no auth needed):

| File | URL |
|---|---|
| Latest version | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/openclaw-docs.latest.md> |
| Pinned version (release asset) | `https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v<version>/openclaw-docs.<version>.md` |
| Index of stored versions | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/INDEX.md> |

Only the `latest.*` triplet lives in `main`. Pinned versions are GitHub Release assets — `https://.../main/versions/openclaw-docs.<version>.md` returns 404. `scripts/lookup.py` handles both surfaces transparently.

**Local copy** (when the skill is installed via `git clone`):

```
<skill-root>/
├── versions/
│   ├── INDEX.md                          ← list of available versions + Release URLs
│   ├── openclaw-docs.latest.md           ← flattened docs, newest version
│   ├── openclaw-docs.latest.toc.jsonl    ← TOC: section path + H2/H3 + line range + keywords
│   └── openclaw-docs.latest.sections.jsonl  ← line + byte ranges per section
└── scripts/
    └── lookup.py                         ← deterministic retrieval CLI
```

Only the `latest.*` triplet is committed to `main`. **Historical version snapshots live as GitHub Release assets**, not in the working tree, so cloning the skill stays cheap forever:

```
https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v<version>/openclaw-docs.<version>.<suffix>
```

`scripts/lookup.py` auto-fetches non-latest versions from the matching release and caches them under `~/.cache/openclaw-docs/<version>/`. No manual download required.

`<skill-root>` depends on the host:

| Host | Conventional skill root |
|---|---|
| Anthropic Claude Code | `~/.claude/skills/openclaw-docs/` |
| OpenAI Codex | `~/.codex/skills/openclaw-docs/` (or `~/.agents/skills/openclaw-docs/` per the docs default) |
| ChatGPT / Cursor / others | The uploaded knowledge file or `@`-referenced project file |

Prefer the local copy when present — `Grep` is much faster than `WebFetch` on a 5+ MB file. If the local copy is missing or stale, `git -C <skill-root> pull` gets the latest snapshots, or fall back to `WebFetch` on the raw URL above.

## When to invoke

- The user asks any factual question about OpenClaw: CLI flags, config keys, plugin SDK, gateway protocol, channels (Telegram/Discord/Slack/Signal/iMessage/Web), providers, doctor, onboarding, release flow, etc.
- You're about to assert how OpenClaw behaves — check the docs first instead of answering from memory.
- The user is debugging a specific OpenClaw instance (SSH'd host, local checkout, named version) — load the matching version's docs.

## Version-selection rule

1. **If a specific OpenClaw instance is in scope**, identify its version:
   - Remote: `ssh <host> 'openclaw --version'`
   - Local repo: read `version` field from `package.json`
   - User-stated: take their word, but confirm against `INDEX.md`
2. **Match that version** to a file: `openclaw-docs.<version>.md`. If it's not in `INDEX.md`, the snapshot doesn't exist — note that to the user, fall back to `openclaw-docs.latest.md`, and warn that behavior may differ.
3. **No specific version known** → use `openclaw-docs.latest.md`.
4. **Always preface OpenClaw answers** with `According to docs for OpenClaw <version>:` and **cite the section path** (e.g. `…see `gateway/configuration-reference.md`.`) so the user knows which snapshot and which file grounded the answer.

## How to read the docs efficiently

Files are 5+ MB. **Do not full-`Read` them.** Use `Grep` (or the tool equivalent in your platform). Sections are delimited by `# Section: <relative-path>` headers (1:1 with the upstream `docs/**/*.md` tree); within each section, the original H2/H3 headings are preserved.

### Lookup priority

In order of preference:

1. **`scripts/lookup.py`** — deterministic CLI that wraps the indexes. Same retrieval behavior across every host that can run Python 3.
2. **Native `Grep` + `Read`** on the flattened doc — fall back here when the lookup script isn't available (uploaded-knowledge-file surfaces, no shell access).
3. **`WebFetch` on the raw / jsDelivr URL** — last resort when there's no local clone.

### Lookup strategy — match the query type

**Specific query** (config key, CLI flag, function name, environment variable, package, file path, error string):

- Use **fixed-string matching** (not regex). OpenClaw identifiers contain regex metacharacters (`.`, `-`, `/`, `@`) that break naïve regex search.
- With the script: `python3 scripts/lookup.py --query gateway.mode --version latest`
- With native Grep: pass the fixed-string flag (`grep -F`, `rg -F`, or your tool's equivalent) and grep the keyword directly. Examples: `gateway.mode`, `--bind loopback`, `createPluginEntry`, `OPENCLAW_LIVE_TEST`, `@openclaw/plugin-sdk`.
- Read a small offset around the top hit.

**Broad / ambiguous query** ("how do plugins work?", "Telegram setup", "gateway configuration"):

1. **Route via the TOC.** With the script: `python3 scripts/lookup.py --toc "telegram setup" --version latest` returns ranked candidate sections with their H2/H3 outline. Without the script, grep the heading skeleton: `grep -E "^(# Section:|#{2,3} )" openclaw-docs.latest.md` (returns ~6K lines: sections + H2 + H3 — the doc's effective table of contents). For very broad queries, pre-filter the skeleton to keep context small: `grep -E "^(# Section:|#{2,3} )" openclaw-docs.latest.md | grep -Ei "plugin|sdk|entry" -C 4`.
2. Pick the 1–3 most relevant section paths.
3. **Extract.** With the script: `python3 scripts/lookup.py --section plugins/manifest.md` (optionally `--heading "Lifecycle"` to narrow to one H2/H3 block). Without the script: `Read` a targeted offset around the matching `# Section:` line, or grep narrower keywords within that section's line range.
4. Don't dump the whole skeleton into the response — it's a routing aid, not content.

**Fallback** when no local clone is available and the full file is too large to fetch over `WebFetch`: fetch `INDEX.md` first to confirm the version, then either fetch the small `.toc.jsonl` index for that version, or use a `Range:` header on the raw URL with byte offsets from `.sections.jsonl` for a precise byte slice.

## Refresh & freshness

- CI re-flattens daily at 06:00 UTC against `openclaw/openclaw` `main`.
- Local installs go stale between runs of `scripts/update.py` (or `git pull`). If `openclaw-docs.latest.md`'s version (check `INDEX.md` or row 0 of `latest.toc.jsonl`) is clearly older than what the user is running, refresh by running:

  ```bash
  python3 scripts/update.py
  ```

  Auto-detects git-clone vs ZIP install and uses the right refresh path (`git pull` or raw-GitHub fetch).
- If even the public `latest.md` is older than the running instance, that means CI hasn't run since the upstream release — recommend running the workflow manually or wait for the next daily tick.

## Interaction with other skills

- **SSH / remote management** (`openclaw-remote`, `remote-relay`): when SSH'd into a box running OpenClaw, capture `openclaw --version` first, then load the matching docs file before answering questions about that host's behavior.
- **Scheduled tasks**: this skill replaces the older `openclaw-project-docs` scheduled task. The CI workflow at `.github/workflows/refresh.yml` is the canonical refresh path.

## Prohibitions

- Do not answer OpenClaw factual questions from model memory when a docs file is available — grep the file.
- Do not fabricate a version number. If you don't know the running version, say so and use `openclaw-docs.latest.md` with the preface rule.
- Do not hand-edit files in `versions/` — they're produced by CI. Edits will be overwritten on the next refresh.
