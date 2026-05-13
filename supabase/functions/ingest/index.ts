/**
 * POST /functions/v1/ingest
 *
 * Bulk-insert helper for the daily CI ingest pipeline. Accepts batched rows of
 * docs_chunks or docs_fields and upserts them via the auto-injected
 * SUPABASE_SERVICE_ROLE_KEY (bypassing RLS so writes succeed).
 *
 * Auth: requires X-Ingest-Token header. The token comes from the INGEST_TOKEN
 * env var (set as a Supabase Edge Function secret) — when deploying, substitute
 * the real token via dashboard secret or by rewriting the fallback in this
 * source.
 *
 * Body shape:
 *   { "table": "docs_chunks" | "docs_fields", "rows": [...] }
 *
 * Returns:
 *   { "inserted": N, "table": "<table>" }
 *
 * Idempotency: PostgREST is called with `Prefer: resolution=merge-duplicates`
 * + the table's unique constraint, so re-running the same payload is a no-op.
 */
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
// Prefer env var; the fallback constant is overwritten by the deploy script
// in this repo with the project-specific token. Leave as empty string in the
// source so a misconfigured deploy fails closed.
const INGEST_TOKEN = Deno.env.get("INGEST_TOKEN") || "__INGEST_TOKEN__";

const ON_CONFLICT: Record<string, string> = {
  docs_chunks: "version,section_path,start_line",
  docs_fields: "version,field_name,context_path",
};
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, content-type, x-ingest-token",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  if (req.method !== "POST")
    return new Response(JSON.stringify({ error: "POST only" }), {
      status: 405,
      headers: { ...CORS, "Content-Type": "application/json" },
    });

  const token = req.headers.get("X-Ingest-Token") || req.headers.get("x-ingest-token");
  if (!token || token !== INGEST_TOKEN || INGEST_TOKEN === "__INGEST_TOKEN__") {
    return new Response(
      JSON.stringify({ error: "forbidden — invalid or missing X-Ingest-Token header" }),
      { status: 403, headers: { ...CORS, "Content-Type": "application/json" } },
    );
  }
  try {
    const body = await req.json();
    const table = String(body.table || "");
    const rows = Array.isArray(body.rows) ? body.rows : [];
    const onConflict = ON_CONFLICT[table];
    if (!onConflict)
      return new Response(JSON.stringify({ error: `unknown table: ${table}` }), {
        status: 400,
        headers: { ...CORS, "Content-Type": "application/json" },
      });
    if (rows.length === 0)
      return new Response(JSON.stringify({ inserted: 0 }), {
        headers: { ...CORS, "Content-Type": "application/json" },
      });

    const r = await fetch(`${SUPABASE_URL}/rest/v1/${table}?on_conflict=${onConflict}`, {
      method: "POST",
      headers: {
        apikey: SERVICE_ROLE,
        Authorization: `Bearer ${SERVICE_ROLE}`,
        "Content-Type": "application/json",
        Prefer: "resolution=merge-duplicates,return=minimal",
      },
      body: JSON.stringify(rows),
    });
    if (!r.ok) {
      const text = await r.text();
      return new Response(
        JSON.stringify({ error: "upstream", status: r.status, body: text.slice(0, 500) }),
        { status: 502, headers: { ...CORS, "Content-Type": "application/json" } },
      );
    }
    return new Response(JSON.stringify({ inserted: rows.length, table }), {
      headers: { ...CORS, "Content-Type": "application/json" },
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: String((e as Error).message || e) }), {
      status: 500,
      headers: { ...CORS, "Content-Type": "application/json" },
    });
  }
});
