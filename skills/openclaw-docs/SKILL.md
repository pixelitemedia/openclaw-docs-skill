---
name: openclaw-docs
description: Authoritative reference for OpenClaw — the daily-refreshed flattened docs at github.com/pixelitemedia/openclaw-docs-skill. Trigger when the user asks anything about OpenClaw features, config fields, CLI flags, gateway behavior, plugin SDK, channels, providers, secrets, doctor, or onboarding. **You MUST verify every config-field, flag, and API-shape claim against the docs before stating it. Do not answer OpenClaw questions from training-data memory — model memory of OpenClaw is unreliable and frequently invents fields that do not exist (e.g. `env` on exec providers, when only `passEnv` is real).**
---

# OpenClaw Docs

## ⚠️ Primary directive

**Model memory of OpenClaw is unreliable.** OpenClaw releases roughly daily (CalVer `YYYY.M.D`); training data is months-to-years old; many "obvious" config patterns common in adjacent systems (Docker Compose, systemd, Kubernetes) **do not exist in OpenClaw**. This skill exists because answering from memory has produced wrong configs that fail validation in real deployments.

**Before stating any of the following, verify it appears verbatim in the docs:**

- Any config-field name (e.g. `secrets.providers.<name>.env` — does this exist?)
- Any CLI flag (e.g. `--bind loopback` — is this the real flag name?)
- Any environment variable (e.g. `OPENCLAW_LIVE_TEST` — is this the real var?)
- Any API or function name (e.g. `createPluginEntry` — does this exist?)
- Any protocol shape (request/response JSON, file format)
- Any "X supports Y" claim about behavior

If the term doesn't appear in the docs, **the term does not exist**. Recommend an alternative that does.

## Verification surfaces (pick the highest one your environment supports)

There's a hosted MCP server, a local CLI, and a fallback grep path. They all hit the same source-of-truth flattened docs; pick by capability:

### ★ Highest — MCP server (preferred when MCP tools are available)

```
https://gzfdvhuglftjnlhlcgjj.supabase.co/functions/v1/mcp
```

Public, no-auth, JSON-RPC 2.0. Adds four tools to any MCP-capable client:

- **`openclaw_field_check`** — *call before stating any config field name.* Returns `{ exists: bool, matches: [...], real_alternatives: [...] }`. The structural guard against hallucinating fields that aren't in the schema.
- **`openclaw_search`** — hybrid 3072-dim vector + trigram search. Use for open-ended questions ("how do I set up Telegram?").
- **`openclaw_section`** — extract a section by path; optionally narrow to one heading.
- **`openclaw_versions`** — list indexed versions.

Tool definitions include trigger guidance ("call this BEFORE asserting that a field exists in OpenClaw config") so a well-configured client will route appropriately. See README.md for install snippets.

### ★ Local CLI — `scripts/lookup.py` (when the skill is installed locally)

```bash
python3 scripts/lookup.py --query "passEnv" --version latest
python3 scripts/lookup.py --toc "telegram setup" --version latest
python3 scripts/lookup.py --section gateway/secrets.md --heading "Provider config"
```

Same retrieval logic, runs against the local `versions/` files (auto-fetches from GitHub Release for non-latest).

### Fallback — `Grep` over the flattened doc

For environments without shell/MCP: `Grep` for the term in `<skill-root>/versions/openclaw-docs.<ver>.md`. Use fixed-string mode for identifiers.

## Mandatory verification protocol

For every OpenClaw question, follow this protocol — **do not skip steps just because you think you know the answer**:

1. **Identify the version** in scope (see "Version selection" below).
2. **Run a verification query** for each technical term you're about to use:
   - **★ Preferred**: call the MCP tool `openclaw_field_check` (for fields) or `openclaw_search` (for open-ended). If the MCP server isn't connected, use one of the next two:
   - `python3 <skill-root>/scripts/lookup.py --query "<term>" --version <ver>`
   - Fallback (no shell): `Grep` for the term in `<skill-root>/versions/openclaw-docs.<ver>.md`
   - Last resort (no local copy): `WebFetch` the raw doc URL or call the `--toc` index via the lookup script
3. **If the term has zero matches**, do not use it in your answer. Either:
   - Find the real term that does the job (re-query with broader terms), or
   - Tell the user the feature/field doesn't appear to exist in this version.
4. **Cite the docs**: every answer must begin with the citation header that `lookup.py` produces, of the exact form:

   ```
   # According to docs for OpenClaw <CONCRETE-VERSION> — <section-path>
   ```

   Where `<CONCRETE-VERSION>` is the resolved version (e.g. `2026.5.6`), **never** the literal string `latest`. If you write `According to docs for OpenClaw latest:` you have not actually consulted the docs and the answer is unsafe.

5. **Quote where helpful**: when claims are non-obvious or contested, include a short verbatim quote from the relevant section in your answer so the user can audit the grounding.

## Known hallucination traps

Common false fields/patterns models invent for OpenClaw. Do not use these unless `lookup.py --query` confirms they exist:

| Hallucinated | Real equivalent |
|---|---|
| `env: { K: V }` on a provider | `passEnv: ["K"]` (allowlists from parent process env; OpenClaw does **not** support literal env-value maps on providers) |
| `secret:` field | `SecretRef` object: `{ source, provider, id }` |
| `auth:` section at provider top level | Provider-specific; consult the provider's docs section |
| `--config` for everything | OpenClaw uses `~/.openclaw/openclaw.json` plus per-command flags; check the actual flag |
| Free-form regex search defaults | Identifier search must be **fixed-string** — `.`, `-`, `/`, `@` are regex metacharacters in OpenClaw names |

When in doubt, grep first. **A wrong config is worse than "I don't know" — wrong configs fail at validation or produce silent misbehavior; "I don't know, here's how to find out" lets the user verify before deploying.**

## Where the docs live

**Hosted MCP server** (preferred — registered automatically when this plugin is installed in Claude Code):

```
https://gzfdvhuglftjnlhlcgjj.supabase.co/functions/v1/mcp
```

**Public URLs** (no auth needed) — for fallback / non-MCP harnesses:

| File | URL |
|---|---|
| Latest | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/skills/openclaw-docs/versions/openclaw-docs.latest.md> |
| Pinned (release asset) | `https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v<version>/openclaw-docs.<version>.md` |
| Index | <https://raw.githubusercontent.com/pixelitemedia/openclaw-docs-skill/main/skills/openclaw-docs/versions/INDEX.md> |

Only `latest.*` lives in `main`. Pinned versions are **GitHub Release assets** — `https://.../main/skills/openclaw-docs/versions/openclaw-docs.<version>.md` returns 404. `scripts/lookup.py` resolves both surfaces transparently.

**Local install layout** (after `git clone` or ZIP extraction):

```
<skill-root>/
├── SKILL.md
├── scripts/
│   ├── lookup.py    ← deterministic retrieval CLI (preferred)
│   └── update.py    ← in-place refresh (auto-detects git/ZIP)
└── versions/
    ├── INDEX.md
    ├── openclaw-docs.latest.md
    ├── openclaw-docs.latest.toc.jsonl
    └── openclaw-docs.latest.sections.jsonl
```

Conventional skill roots:

| Host | Path |
|---|---|
| Anthropic Claude Code (plugin install) | `~/.claude/plugins/openclaw-docs/skills/openclaw-docs/` |
| OpenAI Codex | `~/.codex/skills/openclaw-docs/` (or `~/.agents/skills/openclaw-docs/`) |
| Claude.ai / Manus / ChatGPT (uploaded) | The harness's managed skills directory |

## Version selection

1. **If a specific instance is in scope**, identify its version:
   - Remote: `ssh <host> 'openclaw --version'`
   - Local repo: read `version` from `package.json`
   - User-stated: take it but confirm against `versions/INDEX.md` or `versions/releases.json`
2. **Match** to `openclaw-docs.<version>.md`. If absent, fall back to `latest.md` and **warn** the user that behavior may differ.
3. **No version known** → use `latest.md`.
4. The citation header must always show the **concrete** version (`2026.5.6`), not `latest`. `lookup.py` does this automatically.

## Lookup mechanics

Files are 5+ MB. **Never full-`Read` them.** Sections are delimited by `# Section: <relative-path>` headers; within each section, original H2/H3 headings are preserved.

**Specific query** (field name, flag, identifier, error string):

- `python3 scripts/lookup.py --query "<exact-term>" --version <ver>`
- Or: `grep -F "<exact-term>" versions/openclaw-docs.<ver>.md` (fixed-string mode is mandatory; OpenClaw identifiers contain regex metacharacters)
- Read a small offset around the top hit.

**Broad query** ("how does X work?", "Telegram setup"):

1. Route via the TOC: `python3 scripts/lookup.py --toc "<query>" --version <ver>` returns ranked candidate sections with H2/H3 outline.
2. Or grep the heading skeleton: `grep -E "^(# Section:|#{2,3} )" versions/openclaw-docs.<ver>.md` and pre-filter with another grep for query keywords.
3. Pick 1–3 most relevant sections, then extract: `python3 scripts/lookup.py --section <path> [--heading "<sub>"]`.

**No local copy** → `WebFetch` raw URL, or `Range:`-fetch byte slices from `.sections.jsonl` offsets.

## Refresh

- CI re-flattens daily at 06:00 UTC.
- To refresh an installed skill: `python3 scripts/update.py` (auto-detects git vs ZIP install).
- Or re-download the ZIP from `https://github.com/pixelitemedia/openclaw-docs-skill/releases/latest/download/openclaw-docs-skill.zip`.

## Interaction with other skills

- **SSH skills** (`openclaw-remote`, `remote-relay`): capture `openclaw --version` from the SSH'd host first, then load the matching docs file before answering host-specific questions.

## Prohibitions (hard rules)

1. **Never** state a config field, flag, or API name without verifying it appears in the docs via `lookup.py --query` or `grep -F`.
2. **Never** write `According to docs for OpenClaw latest:` — always resolve to the concrete version. If your output contains `latest`, you skipped step 4 of the verification protocol.
3. **Never** invent JSON schema fields or env-var names by analogy to similar systems. OpenClaw's API surface is specific.
4. **Never** hand-edit files in `versions/` — produced by CI; edits get overwritten.
5. **Never** answer from training-data memory of OpenClaw when this skill is available. The whole point of the skill is that memory is wrong.

If the harness sandbox can't run `lookup.py` and can't grep the docs file, say so explicitly: "I cannot verify against the docs in this environment. Here is what model memory suggests, but you must confirm against `<doc-url>` before relying on it." That's better than confidently asserting an unverified field name.
