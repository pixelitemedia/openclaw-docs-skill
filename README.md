# OpenClaw Docs Skill

A Claude Code skill that keeps a local, versioned copy of the official [OpenClaw](https://github.com/openclaw/openclaw) documentation. GitHub Actions refreshes it daily from upstream so consumers always have access to the current docs without re-cloning the OpenClaw repo themselves.

## What's in the repo

```
.
├── SKILL.md                  ← skill definition (Claude reads this)
├── flatten_docs.py           ← refresh script
├── .github/workflows/
│   └── refresh.yml           ← daily auto-refresh
└── versions/
    ├── INDEX.md              ← list of stored versions, newest first
    ├── latest.md             ← always a copy of the newest version file
    └── openclaw_docs_<ver>.md
```

`latest.md` is a real file (not a symlink), so it can be fetched as raw bytes from `raw.githubusercontent.com` and uploaded to Claude.ai / fed to APIs / read by Windows checkouts.

## Install in Claude Code

Clone into the user-global skills dir on each machine that runs Claude Code:

```bash
git clone https://github.com/pixelitemedia/openclaw-docs-skill.git \
  ~/.claude/skills/openclaw-docs
```

To stay current, periodically `git pull` (or add a launchd / cron job).

For project-scoped use, add as a submodule at `<project>/.claude/skills/openclaw-docs`.

## Use elsewhere

| Surface | How |
|---|---|
| Claude.ai (web/desktop) | Download `versions/latest.md` from `raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/latest.md` and upload as a Project file or Skill resource. |
| Claude API / SDK apps | `curl` the same raw URL at startup, inject as system prompt or RAG corpus. |
| Pin to a version | Use `versions/openclaw_docs_<version>.md` directly. |

## Refresh

Automatic: GitHub Actions runs daily at 06:00 UTC. Manual: Actions tab → "Refresh OpenClaw docs" → Run workflow.

To run locally:

```bash
python3 flatten_docs.py --repo /path/to/openclaw/clone --skill-dir .
```

The script clones-walks `<repo>/docs/**/*.md`, concatenates with `# Section: <rel-path>` headers, writes `versions/openclaw_docs_<ver>.md`, copies it over `latest.md`, and refreshes `INDEX.md`.

## How Claude uses it

When the skill is loaded:

1. Detect the OpenClaw version in context (SSH'd host, local repo, or user-named).
2. Match it to a file in `versions/`; otherwise use `latest.md`.
3. `Grep` the file (it's multi-MB — don't full-read).
4. Always preface answers with `According to docs for OpenClaw <version>:`.
