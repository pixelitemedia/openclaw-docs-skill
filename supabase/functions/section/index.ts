/**
 * POST /functions/v1/section
 *
 * Body: { "section_path": "gateway/secrets.md", "version"?: "latest" | "<ver>",
 *         "heading"?: "Hooks", "max_chars"?: 30000 }
 * Returns: { "version": "2026.5.8", "section_path": "...",
 *            "heading"?: "...", "content": "...", "citation": "..." }
 */
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

async function resolveVersion(v: string | undefined): Promise<string | null> {
  const r = await fetch(`${SUPABASE_URL}/rest/v1/rpc/resolve_version`, {
    method: "POST",
    headers: {
      apikey: SERVICE_KEY,
      Authorization: `Bearer ${SERVICE_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ v: v ?? "latest" }),
  });
  if (!r.ok) return null;
  const text = (await r.text()).trim();
  return text.replace(/^"|"$/g, "") || null;
}

function trimToHeading(content: string, heading: string): string | null {
  // H2/H3 block-extract: matched-level-aware. H2 includes child H3s; H3 stops
  // at the next H2 or sibling H3.
  const lines = content.split("\n");
  const headingRe = /^(#{2,3})\s+(.+)$/;
  let start = -1;
  let matchedLevel = 0;
  let end = lines.length;
  const needle = heading.toLowerCase();
  for (let i = 0; i < lines.length; i++) {
    const m = headingRe.exec(lines[i]);
    if (!m) continue;
    const level = m[1].length;
    const text = m[2];
    if (start === -1) {
      if (text.toLowerCase().includes(needle)) {
        start = i;
        matchedLevel = level;
      }
    } else if (level <= matchedLevel) {
      end = i;
      break;
    }
  }
  return start === -1 ? null : lines.slice(start, end).join("\n");
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "POST only" }), {
      status: 405,
      headers: { ...CORS, "Content-Type": "application/json" },
    });
  }
  try {
    const body = await req.json().catch(() => ({}));
    const sectionPath = body.section_path as string | undefined;
    if (!sectionPath) {
      return new Response(
        JSON.stringify({ error: "section_path required" }),
        { status: 400, headers: { ...CORS, "Content-Type": "application/json" } },
      );
    }
    const heading = body.heading as string | undefined;
    const maxChars = Math.min(Number(body.max_chars ?? 30000), 100000);
    const version = await resolveVersion(body.version);
    if (!version) {
      return new Response(
        JSON.stringify({ error: "no versions in DB" }),
        { status: 503, headers: { ...CORS, "Content-Type": "application/json" } },
      );
    }

    // Pull all chunks for this section, ordered by start_line
    const params = new URLSearchParams({
      select: "section_path,heading,start_line,end_line,content,content_type",
      version: `eq.${version}`,
      section_path: `eq.${sectionPath}`,
      order: "start_line.asc",
    });
    const r = await fetch(
      `${SUPABASE_URL}/rest/v1/docs_chunks?${params}`,
      { headers: { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}` } },
    );
    let rows = await r.json() as Array<{
      section_path: string; heading: string | null; start_line: number;
      end_line: number; content: string; content_type: string;
    }>;

    if (rows.length === 0) {
      // Try fuzzy: substring/basename match on section_path
      const alt = await fetch(
        `${SUPABASE_URL}/rest/v1/docs_chunks?` + new URLSearchParams({
          select: "section_path",
          version: `eq.${version}`,
          section_path: `ilike.*${sectionPath}*`,
        }),
        { headers: { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}` } },
      );
      const altRows = await alt.json() as Array<{ section_path: string }>;
      const candidates = [...new Set(altRows.map((r) => r.section_path))];
      return new Response(
        JSON.stringify({
          error: `section "${sectionPath}" not found in v${version}`,
          candidates: candidates.slice(0, 10),
        }),
        { status: 404, headers: { ...CORS, "Content-Type": "application/json" } },
      );
    }

    // Reassemble section content in line order
    let content = rows.map((r) => r.content).join("\n");

    if (heading) {
      const trimmed = trimToHeading(content, heading);
      if (!trimmed) {
        return new Response(
          JSON.stringify({
            error: `heading "${heading}" not found in ${sectionPath}`,
            available_headings: [...new Set(rows.map((r) => r.heading).filter(Boolean))],
          }),
          { status: 404, headers: { ...CORS, "Content-Type": "application/json" } },
        );
      }
      content = trimmed;
    }

    let truncated = false;
    if (content.length > maxChars) {
      content = content.slice(0, maxChars) + `\n\n... (truncated at ${maxChars} chars)`;
      truncated = true;
    }

    const citation = heading
      ? `According to docs for OpenClaw ${version} — \`${sectionPath}\` → \`${heading}\``
      : `According to docs for OpenClaw ${version} — \`${sectionPath}\``;

    return new Response(
      JSON.stringify({
        version,
        section_path: sectionPath,
        heading: heading ?? null,
        content,
        citation,
        truncated,
      }),
      { headers: { ...CORS, "Content-Type": "application/json" } },
    );
  } catch (e) {
    return new Response(
      JSON.stringify({ error: String((e as Error)?.message || e) }),
      { status: 500, headers: { ...CORS, "Content-Type": "application/json" } },
    );
  }
});
