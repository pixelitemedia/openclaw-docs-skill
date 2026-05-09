# OpenClaw Docs — Versions

This skill mirrors [openclaw/openclaw](https://github.com/openclaw/openclaw) docs in two places:

1. **Latest** lives in `main` — see `openclaw-docs.latest.{md,toc.jsonl,sections.jsonl}` in this directory. Updated daily by CI.
2. **Pinned historical versions** live as [GitHub Release](https://github.com/pixelitemedia/openclaw-docs-skill/releases) assets.

Each version triplet is three files:

- `openclaw-docs.<version>.md` — flattened docs
- `openclaw-docs.<version>.toc.jsonl` — TOC (section path + H2/H3 + keywords + line range)
- `openclaw-docs.<version>.sections.jsonl` — line + byte ranges per section

Pinned download URL pattern:

```
https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v<version>/openclaw-docs.<version>.<suffix>
```

Note: `https://.../main/versions/openclaw-docs.<version>.md` returns 404 — only `latest.*` lives in `main`.

## Latest (in-tree)

- **2026.5.8** — `openclaw-docs.latest.md` (5855 KB) · [release v2026.5.8](https://github.com/pixelitemedia/openclaw-docs-skill/releases/tag/v2026.5.8)

## Archived (release assets)

| Version | Release | Markdown | TOC | Sections |
|---|---|---|---|---|
| 2026.5.8 | [v2026.5.8](https://github.com/pixelitemedia/openclaw-docs-skill/releases/tag/v2026.5.8) | [.md](https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v2026.5.8/openclaw-docs.2026.5.8.md) | [.toc.jsonl](https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v2026.5.8/openclaw-docs.2026.5.8.toc.jsonl) | [.sections.jsonl](https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v2026.5.8/openclaw-docs.2026.5.8.sections.jsonl) |
| 2026.5.6 | [v2026.5.6](https://github.com/pixelitemedia/openclaw-docs-skill/releases/tag/v2026.5.6) | [.md](https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v2026.5.6/openclaw-docs.2026.5.6.md) | [.toc.jsonl](https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v2026.5.6/openclaw-docs.2026.5.6.toc.jsonl) | [.sections.jsonl](https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v2026.5.6/openclaw-docs.2026.5.6.sections.jsonl) |
| 2026.5.3 | [v2026.5.3](https://github.com/pixelitemedia/openclaw-docs-skill/releases/tag/v2026.5.3) | [.md](https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v2026.5.3/openclaw-docs.2026.5.3.md) | [.toc.jsonl](https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v2026.5.3/openclaw-docs.2026.5.3.toc.jsonl) | [.sections.jsonl](https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v2026.5.3/openclaw-docs.2026.5.3.sections.jsonl) |
