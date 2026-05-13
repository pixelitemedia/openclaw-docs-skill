/**
 * POST /functions/v1/mcp
 *
 * MCP server (Model Context Protocol). Exposes the OpenClaw docs search +
 * field-check + section-extract + versions tools as MCP tools over JSON-RPC,
 * so MCP-capable AI clients (Claude.ai, Cursor, Cline, Continue, etc.) can
 * be configured with a single URL and call structured tools.
 *
 * MCP Streamable HTTP transport: each request is a JSON-RPC call.
 * Methods: initialize, tools/list, tools/call.
 */
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

// MCP tool definitions — descriptions are deliberately blunt about WHEN to
// call. Models that read these as system-prompt tool docs get clear routing
// rules without us tightening SKILL.md any further.
const TOOLS = [
  {
    name: "openclaw_field_check",
    description: `Check whether a specific OpenClaw config field, CLI flag, or identifier actually exists in the documented schema. Use this BEFORE asserting that a field, flag, or option exists in OpenClaw config — especially in 'secrets.providers', 'channels.*', 'plugins.*', 'gateway.*', or any structured config block. Returns { exists: bool, real_alternatives: [...] } so the caller can avoid hallucinating fields that aren't in the schema.

WHEN TO CALL: Before writing any OpenClaw config example or claiming a field exists. Especially when a similar-looking field exists in other tools (e.g. 'env' on Docker Compose providers — OpenClaw has no such field, only 'passEnv').`,
    inputSchema: {
      type: "object",
      properties: {
        field_name: {
          type: "string",
          description: "Exact field name to check (e.g. 'env', 'passEnv', 'allowSymlinkCommand')."
        },
        context_path: {
          type: "string",
          description: "Optional dot-path to scope the check (e.g. 'secrets.providers', 'channels.telegram', 'plugins'). Helps return relevant alternatives.",
        },
        version: {
          type: "string",
          description: "OpenClaw version to check ('latest' or specific like '2026.5.8'). Defaults to 'latest'.",
        },
      },
      required: ["field_name"],
    },
  },
  {
    name: "openclaw_search",
    description: `Hybrid vector + trigram search across the OpenClaw docs. Returns ranked relevant chunks with section paths, headings, and snippets.

WHEN TO CALL: When the user asks an open-ended OpenClaw question that doesn't reduce to checking one specific field name. Examples: "how do I set up Telegram", "what does the gateway need to start", "where is plugin auth configured".

NOT FOR: Specific field-existence checks (use openclaw_field_check), or extracting a known section (use openclaw_section).`,
    inputSchema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Natural-language query — e.g. 'how do I configure Telegram bot token'.",
        },
        version: { type: "string", description: "OpenClaw version. Defaults to 'latest'." },
        limit: {
          type: "number",
          description: "Number of top results to return (1-25). Default 8.",
        },
      },
      required: ["query"],
    },
  },
  {
    name: "openclaw_section",
    description: `Extract a specific section of the OpenClaw docs by its source path. Returns the full section text (or just one heading sub-block if heading is specified).

WHEN TO CALL: When you already know the section path you need — typically as a follow-up after openclaw_search or openclaw_field_check tells you which section to read in full.

Section paths use the upstream docs/ tree (e.g. 'gateway/secrets.md', 'channels/telegram.md', 'plugins/manifest.md').`,
    inputSchema: {
      type: "object",
      properties: {
        section_path: {
          type: "string",
          description: "Source path of the section (e.g. 'gateway/secrets.md').",
        },
        heading: {
          type: "string",
          description: "Optional H2/H3 within the section to extract just that block.",
        },
        version: { type: "string", description: "OpenClaw version. Defaults to 'latest'." },
        max_chars: { type: "number", description: "Truncate at this many characters (default 30000)." },
      },
      required: ["section_path"],
    },
  },
  {
    name: "openclaw_versions",
    description: `List the OpenClaw documentation versions currently indexed. Use to confirm which versions are available before pinning a query to a specific version, or to discover what 'latest' resolves to.`,
    inputSchema: { type: "object", properties: {} },
  },
];

const FN_BY_TOOL: Record<string, string> = {
  openclaw_field_check: "field-check",
  openclaw_search: "search",
  openclaw_section: "section",
  openclaw_versions: "versions",
};

function jsonRpcError(id: unknown, code: number, message: string, data?: unknown) {
  return { jsonrpc: "2.0", id, error: { code, message, ...(data ? { data } : {}) } };
}
function jsonRpcResult(id: unknown, result: unknown) {
  return { jsonrpc: "2.0", id, result };
}

async function callTool(toolName: string, args: Record<string, unknown>, authHeader: string | null) {
  const fn = FN_BY_TOOL[toolName];
  if (!fn) throw new Error(`unknown tool: ${toolName}`);

  const url = `${SUPABASE_URL}/functions/v1/${fn}`;
  const r = await fetch(url, {
    method: fn === "versions" ? "GET" : "POST",
    headers: {
      ...(authHeader ? { Authorization: authHeader } : {}),
      "Content-Type": "application/json",
    },
    body: fn === "versions" ? undefined : JSON.stringify(args),
  });
  const text = await r.text();
  return {
    content: [{ type: "text", text }],
    isError: !r.ok,
  };
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  // Some clients send GET to discover the endpoint; respond with a friendly hint.
  if (req.method === "GET") {
    return new Response(JSON.stringify({
      jsonrpc: "2.0",
      info: "MCP server. POST JSON-RPC 2.0 with method=initialize|tools/list|tools/call.",
      tools: TOOLS.map((t) => t.name),
    }), {
      headers: { ...CORS, "Content-Type": "application/json" },
    });
  }
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "POST only" }), {
      status: 405, headers: { ...CORS, "Content-Type": "application/json" },
    });
  }

  const auth = req.headers.get("authorization");
  let payload: any;
  try {
    payload = await req.json();
  } catch {
    return new Response(JSON.stringify(jsonRpcError(null, -32700, "Parse error")), {
      status: 400, headers: { ...CORS, "Content-Type": "application/json" },
    });
  }

  const id = payload?.id ?? null;
  const method = payload?.method as string | undefined;
  const params = payload?.params ?? {};

  try {
    if (method === "initialize") {
      return new Response(JSON.stringify(jsonRpcResult(id, {
        protocolVersion: "2024-11-05",
        capabilities: { tools: { listChanged: false } },
        serverInfo: {
          name: "openclaw-docs",
          version: "1.0.0",
          description: "Authoritative OpenClaw docs lookup — vector search, field check, section extract.",
        },
      })), { headers: { ...CORS, "Content-Type": "application/json" } });
    }

    if (method === "tools/list") {
      return new Response(JSON.stringify(jsonRpcResult(id, { tools: TOOLS })), {
        headers: { ...CORS, "Content-Type": "application/json" },
      });
    }

    if (method === "tools/call") {
      const name = params?.name as string | undefined;
      const args = params?.arguments ?? {};
      if (!name) {
        return new Response(JSON.stringify(jsonRpcError(id, -32602, "Missing tool name")), {
          status: 400, headers: { ...CORS, "Content-Type": "application/json" },
        });
      }
      const result = await callTool(name, args, auth);
      return new Response(JSON.stringify(jsonRpcResult(id, result)), {
        headers: { ...CORS, "Content-Type": "application/json" },
      });
    }

    if (method === "notifications/initialized") {
      // No-op acknowledgement
      return new Response(null, { status: 204, headers: CORS });
    }

    return new Response(JSON.stringify(jsonRpcError(id, -32601, `Method not found: ${method}`)), {
      status: 404, headers: { ...CORS, "Content-Type": "application/json" },
    });
  } catch (e) {
    return new Response(
      JSON.stringify(jsonRpcError(id, -32603, "Internal error", String((e as Error).message || e))),
      { status: 500, headers: { ...CORS, "Content-Type": "application/json" } },
    );
  }
});
