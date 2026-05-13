/**
 * POST /functions/v1/field-check
 *
 * Fast structural lookup: "does field X exist in OpenClaw config (optionally
 * scoped to context Y)?" The signature failure case the skill addresses is
 * Codex hallucinating a literal `env` field on `secrets.providers.<name>`
 * — this tool returns a typed "exists: false" with `passEnv` as the real
 * alternative, which is much harder to ignore than a search-result snippet.
 *
 * Body: { "field_name": "env",
 *         "context_path"?: "secrets.providers" | "secrets" | "channels.telegram",
 *         "version"?: "latest" | "<ver>" }
 *
 * Returns: {
 *   "version": "2026.5.8",
 *   "field_name": "env",
 *   "exists": false,
 *   "context_path": "secrets.providers",
 *   "matches": [],
 *   "real_alternatives": [{"name":"passEnv","section_path":"...","heading":"..."}],
 *   "common_confusion"?: "..."
 * }
 */
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

async function db(path: string, body?: unknown) {
  const r = await fetch(`${SUPABASE_URL}${path}`, {
    method: body ? "POST" : "GET",
    headers: {
      apikey: SERVICE_ROLE,
      Authorization: `Bearer ${SERVICE_ROLE}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`db ${r.status}: ${await r.text()}`);
  return r.json();
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
    const fieldName = String(body.field_name || "").trim();
    if (!fieldName) {
      return new Response(JSON.stringify({ error: "field_name required" }), {
        status: 400, headers: { ...CORS, "Content-Type": "application/json" },
      });
    }
    const contextPath = body.context_path ? String(body.context_path) : null;
    const version = await resolveVersion(body.version);

    // 1) Look up in docs_fields (exact match by field_name within version)
    const params = new URLSearchParams({
      select: "field_name,context_path,section_path,description",
      version: `eq.${version}`,
      field_name: `eq.${fieldName}`,
    });
    if (contextPath) {
      params.append("context_path", `ilike.${contextPath}*`);
    }
    const matches = await db(`/rest/v1/docs_fields?${params}`) as Array<{
      field_name: string; context_path: string; section_path: string; description: string | null;
    }>;

    // 2) If matches exist, the field IS real. Return early.
    if (matches.length > 0) {
      return new Response(JSON.stringify({
        version,
        field_name: fieldName,
        exists: true,
        context_path: contextPath,
        matches: matches.slice(0, 10),
        citation: `According to docs for OpenClaw ${version} — \`${fieldName}\` documented at ${matches.map((m) => m.section_path).slice(0, 3).join(", ")}`,
      }), { headers: { ...CORS, "Content-Type": "application/json" } });
    }

    // 3) No match — try to find similar/alternative fields in the same context.
    let alternatives: Array<{ name: string; section_path: string; context_path: string }> = [];
    if (contextPath) {
      // Pull all fields from the requested context. Surface them as
      // candidates so the caller sees what's actually documented there.
      const altParams = new URLSearchParams({
        select: "field_name,section_path,context_path",
        version: `eq.${version}`,
        context_path: `ilike.${contextPath}*`,
        limit: "30",
      });
      const altRows = await db(`/rest/v1/docs_fields?${altParams}`) as Array<{
        field_name: string; section_path: string; context_path: string;
      }>;
      // Dedupe by name; prefer fields whose name contains the queried letters
      const seen = new Set<string>();
      const sorted = altRows.sort((a, b) => {
        const aS = a.field_name.toLowerCase().includes(fieldName.toLowerCase().slice(0, 3)) ? 0 : 1;
        const bS = b.field_name.toLowerCase().includes(fieldName.toLowerCase().slice(0, 3)) ? 0 : 1;
        return aS - bS;
      });
      for (const row of sorted) {
        if (seen.has(row.field_name)) continue;
        seen.add(row.field_name);
        alternatives.push({
          name: row.field_name,
          section_path: row.section_path,
          context_path: row.context_path,
        });
        if (alternatives.length >= 12) break;
      }
    }

    // 4) Backup: also do a free-text mention scan via the SQL helper.
    const mentions = await db("/rest/v1/rpc/find_field_mentions", {
      field_name: fieldName,
      target_version: version,
      context_filter: contextPath,
    }) as Array<{ section_path: string; heading: string | null; content: string; start_line: number; end_line: number }>;

    return new Response(JSON.stringify({
      version,
      field_name: fieldName,
      exists: mentions.length > 0,  // pattern match in code/config blocks
      context_path: contextPath,
      matches: [],
      mentions: mentions.slice(0, 5).map((m) => ({
        section_path: m.section_path,
        heading: m.heading,
        line: m.start_line,
      })),
      real_alternatives: alternatives,
      common_confusion: alternatives.length > 0
        ? `Field "${fieldName}" is not documented in context "${contextPath ?? "(any)"}". Real fields in that context: ${alternatives.slice(0, 6).map((a) => a.name).join(", ")}.`
        : `Field "${fieldName}" is not documented${contextPath ? ` in context "${contextPath}"` : ""} for OpenClaw ${version}.`,
      citation: `According to docs for OpenClaw ${version}: \`${fieldName}\` is not a documented field${contextPath ? ` under \`${contextPath}\`` : ""}.`,
    }), { headers: { ...CORS, "Content-Type": "application/json" } });
  } catch (e) {
    return new Response(JSON.stringify({ error: String((e as Error).message || e) }), {
      status: 500, headers: { ...CORS, "Content-Type": "application/json" },
    });
  }
});
