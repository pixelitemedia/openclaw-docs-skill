---
name: openclaw-docs
description: Fetch, flatten, and version-store OpenClaw documentation from the openclaw/openclaw GitHub repo into ~/.claude/skills/openclaw-docs/versions/, then serve as the authoritative reference for OpenClaw questions. Trigger when the user asks anything about OpenClaw features/config/APIs/CLI/gateway/plugins, asks to refresh/update OpenClaw docs, or is debugging a specific running OpenClaw instance (use in conjunction with SSH skills to detect the remote version).
---

# OpenClaw Docs

## Purpose

Keep a local, versioned copy of the official OpenClaw documentation that Claude can reference verbatim. OpenClaw releases frequently (CalVer: `YYYY.M.D`), so pinning docs to the exact running version avoids answering from a stale model prior.

## Layout

```
~/.claude/skills/openclaw-docs/
├── SKILL.md               ← this file
├── flatten_docs.py        ← sync + flatten script
└── versions/
    ├── INDEX.md           ← list of all stored versions
    ├── latest.md          ← symlink to newest flattened doc
    ├── openclaw_docs_2026.4.14.md
    ├── openclaw_docs_2026.3.28.md
    └── ...
```

The upstream clone lives at `~/OpenClaw/docs/openclaw` (git remote: `https://github.com/openclaw/openclaw`). The skill pulls from there — it does NOT re-clone.

## When to invoke

**Refresh the docs** (run the script) when:
- The user explicitly asks to update / pull / refresh OpenClaw docs.
- The user mentions an OpenClaw version you don't have a file for in `versions/`.
- More than ~a week has passed since `latest.md` was updated and the user is asking a current-behavior question.

**Read the docs** (grep / read the relevant version file) when:
- The user asks any factual question about OpenClaw: CLI flags, config keys, plugin SDK, gateway protocol, channels, providers, doctor, onboarding, release flow, etc.
- You're about to assert how OpenClaw behaves. Check the docs first rather than answering from memory.

## Version selection rule

1. **If a specific OpenClaw instance is in context** — e.g., an SSH session to a host running OpenClaw, or the user names a version — determine its version:
   - Remote: `ssh <host> 'openclaw --version'` or `openclaw version`
   - Local repo: read `package.json` version
2. **Match that version** to a file in `versions/`. If the exact version isn't stored, run `flatten_docs.py` to fetch it (it will checkout/pull current `main` and produce a file tagged with whatever version is in `package.json`).
3. **If no specific version is known**, use `versions/latest.md`.
4. **Always preface OpenClaw answers** with: `According to docs for OpenClaw <version>:` so the user knows which snapshot you used.

If the stored `latest.md` version is clearly older than what the user is running, refresh first.

## Running the sync script

```bash
python3 ~/.claude/skills/openclaw-docs/flatten_docs.py
```

Options:
- `--repo PATH` — override the local clone location (default `~/OpenClaw/docs/openclaw`)
- `--skill-dir PATH` — override this skill's directory
- `--no-pull` — skip `git fetch/pull` (offline / reading pinned checkout)

The script:
1. `git fetch --all --tags` + `git pull --ff-only` the repo.
2. Reads `version` from `package.json`.
3. Walks `docs/**/*.md` (excluding `.generated`, `images`, `assets`, `zh-CN`, `ja-JP`, `.i18n`), concatenates into `versions/openclaw_docs_<version>.md`.
4. Rewrites `versions/INDEX.md` and repoints `versions/latest.md`.

To pin to a specific version, check out that git tag in the repo first, then run with `--no-pull`:

```bash
cd ~/OpenClaw/docs/openclaw
git checkout v2026.3.28
python3 ~/.claude/skills/openclaw-docs/flatten_docs.py --no-pull
git checkout main   # restore
```

## Reading the docs efficiently

Flattened files are large (multi-MB). Don't `Read` the whole file unless asked — **use `Grep`** to find the section, then `Read` a targeted offset. Each file has `# Section: <rel-path>` headers that make navigation easy:

```
Grep for "Section: channels/" in versions/latest.md  → locate channel docs
Grep for "gateway.mode" to find config key usage
```

## Interaction with other skills

- **SSH / remote management skills** (`openclaw-remote`, `remote-relay`): when you SSH into a box running OpenClaw, capture the version from `openclaw --version` and load the matching docs file before answering questions about that host's behavior.
- **Scheduled tasks**: the existing `openclaw-project-docs` scheduled task can be updated to invoke this script on a cadence if the user wants automatic refreshes.

## Prohibitions

- Do not answer OpenClaw factual questions from model memory when a docs file exists — grep the file.
- Do not fabricate version numbers. If you don't know the running version, say so and use `latest.md` with the preface.
- Do not edit files inside `~/OpenClaw/docs/openclaw/` — that's the upstream clone. Edits belong elsewhere.
