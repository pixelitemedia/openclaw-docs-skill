---
name: openclaw-docs
description: Authoritative reference for OpenClaw — points to the public, daily-refreshed flattened docs at github.com/pixelitemedia/openclaw-docs-skill. Trigger when the user asks anything about OpenClaw features, config, CLI, gateway, plugin SDK, channels, providers, or is debugging a running OpenClaw instance. Use to ground answers in current docs instead of model memory.
---

# OpenClaw Docs

## What this skill is

A pointer. The actual OpenClaw documentation is mirrored, flattened, and version-snapshotted by GitHub Actions in <https://github.com/pixelitemedia/openclaw-docs-skill>. This skill teaches you (the assistant) where to find it, which version to pick, and how to cite it.

You do **not** need to run any flatten / sync script. CI does that upstream. Your job is consumption.

## Where the docs live

**Public raw URLs** (no auth needed):

| File | URL |
|---|---|
| Latest version | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/openclaw-docs.latest.md> |
| Pinned version | `https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/openclaw-docs.<version>.md` |
| Index of stored versions | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/versions/INDEX.md> |

**Local copy** (when this skill is installed via `git clone` into `~/.claude/skills/openclaw-docs/`):

```
~/.claude/skills/openclaw-docs/versions/
├── INDEX.md
├── openclaw-docs.latest.md
└── openclaw-docs.<version>.md
```

Prefer the local copy when present — `Grep` is much faster than `WebFetch` on a 5+ MB file. If the local copy is missing or stale, `git -C ~/.claude/skills/openclaw-docs pull` gets the latest snapshots, or fall back to `WebFetch` on the raw URL.

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
4. **Always preface OpenClaw answers** with `According to docs for OpenClaw <version>:` so the user knows which snapshot grounds the answer.

## How to read the docs efficiently

Files are 5+ MB. **Do not full-`Read` them.** Use `Grep` (or the tool equivalent in your platform):

- Sections are delimited by `# Section: <relative-path>` headers — these map 1:1 to the upstream `docs/**/*.md` tree.
- Grep for the section path (`Section: gateway/`), the config key (`gateway.mode`), or the symbol (`createPluginEntry`).
- After locating the section, `Read` a targeted offset around the match.

If you only have `WebFetch` (no local clone) and the file is too large to fetch whole, fetch the raw URL with a `Range:` header for the relevant byte slice, or fetch `INDEX.md` first to check version availability.

## Refresh & freshness

- CI re-flattens daily at 06:00 UTC against `openclaw/openclaw` `main`.
- Local clones go stale until `git pull`. If `openclaw-docs.latest.md`'s version (the first `# Section:` block reveals it, or check `INDEX.md`) is clearly older than what the user is running, `git pull` the skill repo (or `WebFetch` the raw URL).
- If even the public `latest.md` is older than the running instance, that means CI hasn't run since the upstream release — recommend running the workflow manually or wait for the next daily tick.

## Interaction with other skills

- **SSH / remote management** (`openclaw-remote`, `remote-relay`): when SSH'd into a box running OpenClaw, capture `openclaw --version` first, then load the matching docs file before answering questions about that host's behavior.
- **Scheduled tasks**: this skill replaces the older `openclaw-project-docs` scheduled task. The CI workflow at `.github/workflows/refresh.yml` is the canonical refresh path.

## Prohibitions

- Do not answer OpenClaw factual questions from model memory when a docs file is available — grep the file.
- Do not fabricate a version number. If you don't know the running version, say so and use `openclaw-docs.latest.md` with the preface rule.
- Do not hand-edit files in `versions/` — they're produced by CI. Edits will be overwritten on the next refresh.
