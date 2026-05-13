/**
 * GET /functions/v1/versions
 *
 * Lists OpenClaw doc versions currently embedded in the docs_chunks table,
 * newest first (numerically by CalVer tuple, not lexically). The newest is
 * what `latest` resolves to.
 *
 * Returns:
 *   { "latest": "2026.5.8",
 *     "versions": [{"version": "2026.5.8", "chunk_count": 6573, "is_latest": true},
 *                  {"version": "2026.5.6", ...}] }
 */
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
// Edge functions run with the service role key by default — fine for read-only
// queries over a table that already has anon-readable RLS, and avoids the
// complexity of forwarding the caller's anon key.
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function versionKey(v: string): number[] {
  return v.split(".").map((p) => Number.isFinite(parseInt(p)) ? parseInt(p) : 0);
}

function compareVersions(a: string, b: string): number {
  const ak = versionKey(a);
  const bk = versionKey(b);
  for (let i = 0; i < Math.max(ak.length, bk.length); i++) {
    const av = ak[i] ?? 0;
    const bv = bk[i] ?? 0;
    if (av !== bv) return bv - av; // descending
  }
  return 0;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: CORS });
  }
  try {
    const url = `${SUPABASE_URL}/rest/v1/rpc/distinct_versions_with_counts`;
    // No RPC for that yet — fall back to a SELECT with grouping.
    const select = `${SUPABASE_URL}/rest/v1/docs_chunks?select=version`;
    const r = await fetch(select, {
      headers: {
        apikey: SERVICE_KEY,
        Authorization: `Bearer ${SERVICE_KEY}`,
        Prefer: "count=exact",
      },
    });
    if (!r.ok) {
      const body = await r.text();
      return new Response(JSON.stringify({ error: "db error", body }), {
        status: 500,
        headers: { ...CORS, "Content-Type": "application/json" },
      });
    }
    const rows = await r.json() as { version: string }[];
    const counts = new Map<string, number>();
    for (const row of rows) counts.set(row.version, (counts.get(row.version) ?? 0) + 1);
    const sorted = [...counts.keys()].sort(compareVersions);
    const latest = sorted[0] ?? null;
    return new Response(
      JSON.stringify({
        latest,
        versions: sorted.map((v) => ({
          version: v,
          chunk_count: counts.get(v),
          is_latest: v === latest,
        })),
      }),
      { headers: { ...CORS, "Content-Type": "application/json" } },
    );
  } catch (e) {
    return new Response(
      JSON.stringify({ error: String(e?.message || e) }),
      { status: 500, headers: { ...CORS, "Content-Type": "application/json" } },
    );
  }
});
