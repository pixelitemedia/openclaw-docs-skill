# OpenClaw Docs — Versions

Each snapshotted OpenClaw version is published as a [GitHub Release](https://github.com/pixelitemedia/openclaw-docs-skill/releases) with three asset files attached:

- `openclaw-docs.<version>.md` — flattened docs
- `openclaw-docs.<version>.toc.jsonl` — TOC (section path + H2/H3 + keywords + line range)
- `openclaw-docs.<version>.sections.jsonl` — line + byte ranges per section

Direct download URL pattern:

```
https://github.com/pixelitemedia/openclaw-docs-skill/releases/download/v<version>/openclaw-docs.<version>.<suffix>
```

The `openclaw-docs.latest.*` triplet in this `versions/` directory is always a copy of the newest release's assets, kept in `main` for fast `git pull` access. `scripts/lookup.py` auto-fetches non-latest versions from Releases on demand.

## In-tree (newest first)

- **2026.5.6** — `openclaw-docs.2026.5.6.md` (5805 KB) · [release v2026.5.6](https://github.com/pixelitemedia/openclaw-docs-skill/releases/tag/v2026.5.6)
