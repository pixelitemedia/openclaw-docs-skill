# Supabase backend — Edge Functions + pgvector

Powers the **MCP server** at <https://gzfdvhuglftjnlhlcgjj.supabase.co/functions/v1/mcp> (or your fork's equivalent).

## Architecture

```
                ┌───────────────────────────┐
GitHub Actions  │  scripts/ci_ingest.py     │  chunk → embed → POST
(daily refresh) ├───────────────────────────┤
                │  POST /functions/v1/ingest │  (X-Ingest-Token auth)
                └────────────┬──────────────┘
                             │ service_role
                             ▼
              ┌──────────────────────────────┐
              │  Postgres + pgvector + pg_trgm│
              │   docs_chunks   (6,500 rows) │
              │   docs_fields   (1,993 rows) │
              └──────────────┬───────────────┘
                             │
              ┌──────────────┴───────────────┐
              │       Edge Functions          │
              │  /versions   /section         │
              │  /search     /field-check     │
              │  /mcp  ←  JSON-RPC wrapper    │
              └───────────────────────────────┘
                             │
                ┌────────────┴────────────┐
              AI clients via MCP:
              Claude, Cursor, Cline, …
```

## Setup (for a fork)

1. **Create a Supabase project.** Enable `vector`, `pg_trgm`, `pg_net`, `http` extensions.

2. **Apply migrations.** Three are needed:
   - `init_docs_chunks` — `docs_chunks` + `docs_fields` tables, HNSW + trigram indexes, RLS read-only for anon
   - `add_resolve_version_helper` — `resolve_version()`, `match_docs()`, `find_field_mentions()` SQL functions
   - `add_versions_and_smart_context_rpcs` — `list_versions()`, `find_fields_by_context()` SQL functions

   Run them via the Supabase MCP `apply_migration` tool or paste into the SQL editor. Migration SQL is preserved in your fork's history once applied.

3. **Generate an ingest token.** Any strong random string. Store it as the GitHub Actions secret `INGEST_TOKEN`.

4. **Deploy the Edge Functions.** Each function source lives under `supabase/functions/<name>/index.ts`. Replace `__INGEST_TOKEN__` in `ingest/index.ts` with your real token, then deploy via Supabase CLI or the MCP `deploy_edge_function` tool. The `search` function additionally needs `OPENROUTER_API_KEY` available — either as an Edge Function secret OR baked into the source as a fallback constant.

5. **Configure Edge Function secrets** in the Supabase dashboard (Settings → Edge Functions → Secrets):
   - `OPENROUTER_API_KEY` — your OpenRouter inference key
   - `INGEST_TOKEN` — must match the GitHub Actions secret

6. **Configure GitHub Actions secrets** (Settings → Secrets and variables → Actions):
   - `OPENROUTER_API_KEY` — same value as in Supabase
   - `SUPABASE_URL` — `https://<project-ref>.supabase.co`
   - `INGEST_TOKEN` — same value as in Supabase
   - `SUPABASE_QUERY_KEY` — optional anon/publishable key for the idempotency precheck

7. **Initial data load.** Either:
   - Wait for the next daily CI run to populate the DB, or
   - Run locally: `OPENROUTER_API_KEY=... SUPABASE_URL=... INGEST_TOKEN=... python3 scripts/ci_ingest.py`

## Files

| Path | Purpose |
|---|---|
| `functions/versions/index.ts` | Public — list indexed versions |
| `functions/section/index.ts` | Public — extract a section by path |
| `functions/field-check/index.ts` | Public — verify whether a config field exists |
| `functions/search/index.ts` | Public — hybrid vector + trigram search |
| `functions/mcp/index.ts` | Public — JSON-RPC 2.0 MCP wrapper for the four above |
| `functions/ingest/index.ts` | **Auth-gated** — bulk upsert into `docs_chunks`/`docs_fields` |

All public functions deploy with `verify_jwt: false` so MCP clients can call them with no auth setup. RLS keeps the underlying tables read-only for anon; writes only happen via `ingest` with the matching `X-Ingest-Token` header.
