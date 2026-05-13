/**
 * POST /functions/v1/search
 *
 * Hybrid vector + trigram search over embedded OpenClaw docs.
 * Embeds the query text via OpenRouter, calls match_docs RPC which
 * blends cosine similarity (vector) with trigram similarity, returns
 * ranked chunks with citation header.
 *
 * Body: { "query": "telegram setup", "version"?: "latest" | "<ver>", "limit"?: 8 }
 * Returns: { "version": "...", "query": "...", "results": [...] }
 */
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const OPENROUTER_KEY = Deno.env.get("OPENROUTER_API_KEY") || "";
const EMBED_MODEL = Deno.env.get("EMBEDDING_MODEL") || "openai/text-embedding-3-large";
const EMBED_DIMS = Number(Deno.env.get("EMBEDDING_DIMS") || "3072");

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

async function embedQuery(text: string): Promise<number[]> {
  if (!OPENROUTER_KEY) {
    throw new Error("OPENROUTER_API_KEY not set on Edge Function");
  }
  const r = await fetch("https://openrouter.ai/api/v1/embeddings", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${OPENROUTER_KEY}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://github.com/pixelitemedia/openclaw-docs-skill",
      "X-Title": "openclaw-docs-skill",
    },
    body: JSON.stringify({
      model: EMBED_MODEL,
      input: text,
      ...(EMBED_DIMS && EMBED_DIMS < 3072 ? { dimensions: EMBED_DIMS } : {}),
    }),
  });
  if (!r.ok) throw new Error(`embeddings ${r.status}: ${await r.text()}`);
  const j = await r.json();
  return j.data[0].embedding;
}

async function resolveVersion(v: string | undefined): Promise<string> {
  const r = await fetch(`${SUPABASE_URL}/rest/v1/rpc/resolve_version`, {
    method: "POST",
    headers: {
      apikey: SERVICE_ROLE,
      Authorization: `Bearer ${SERVICE_ROLE}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ v: v ?? "latest" }),
  });
  const text = (await r.text()).trim();
  return text.replace(/^"|"$/g, "");
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "POST only" }), {
      status: 405, headers: { ...CORS, "Content-Type": "application/json" },
    });
  }
  try {
    const body = await req.json().catch(() => ({}));
    const query = String(body.query || "").trim();
    if (!query) {
      return new Response(JSON.stringify({ error: "query required" }), {
        status: 400, headers: { ...CORS, "Content-Type": "application/json" },
      });
    }
    const limit = Math.min(Math.max(Number(body.limit ?? 8), 1), 25);
    const version = await resolveVersion(body.version);

    // Embed the query (small, single text → ~1 token batch)
    const queryEmbedding = await embedQuery(query);

    // Call match_docs RPC for hybrid ranking
    const r = await fetch(`${SUPABASE_URL}/rest/v1/rpc/match_docs`, {
      method: "POST",
      headers: {
        apikey: SERVICE_ROLE,
        Authorization: `Bearer ${SERVICE_ROLE}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query_embedding: "[" + queryEmbedding.map((x) => x.toFixed(6)).join(",") + "]",
        query_text: query,
        target_version: version,
        match_count: limit,
      }),
    });
    if (!r.ok) {
      const text = await r.text();
      return new Response(JSON.stringify({ error: "match_docs", body: text }), {
        status: 502, headers: { ...CORS, "Content-Type": "application/json" },
      });
    }
    const rows = await r.json() as Array<{
      id: number; version: string; section_path: string; heading: string | null;
      start_line: number; end_line: number; content: string; content_type: string;
      vector_score: number; trgm_score: number; combined_score: number;
    }>;

    return new Response(JSON.stringify({
      version,
      query,
      result_count: rows.length,
      results: rows.map((r) => ({
        section_path: r.section_path,
        heading: r.heading,
        line_range: `${r.start_line}-${r.end_line}`,
        content_type: r.content_type,
        snippet: r.content.length > 800 ? r.content.slice(0, 800) + "…" : r.content,
        scores: {
          vector: Math.round(r.vector_score * 1000) / 1000,
          trigram: Math.round(r.trgm_score * 1000) / 1000,
          combined: Math.round(r.combined_score * 1000) / 1000,
        },
      })),
      citation: `According to docs for OpenClaw ${version} (top ${rows.length} of vector+trigram search for "${query}")`,
    }), { headers: { ...CORS, "Content-Type": "application/json" } });
  } catch (e) {
    return new Response(JSON.stringify({ error: String((e as Error).message || e) }), {
      status: 500, headers: { ...CORS, "Content-Type": "application/json" },
    });
  }
});
