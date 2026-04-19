import { createClient } from "npm:@supabase/supabase-js@2.47.10";
import type { Database } from "../_shared/database.types.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const OPENROUTER_API_KEY = Deno.env.get("OPENROUTER_API_KEY")!;
const CAPTURE_SECRET = Deno.env.get("CAPTURE_SECRET")!;

const OPENROUTER_BASE = "https://openrouter.ai/api/v1";
const supabase = createClient<Database>(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, x-capture-secret",
};

async function getEmbedding(text: string): Promise<number[]> {
  const r = await fetch(`${OPENROUTER_BASE}/embeddings`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${OPENROUTER_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "openai/text-embedding-3-small",
      input: text,
    }),
  });
  const d = await r.json();
  return d.data[0].embedding;
}

async function extractMetadata(
    text: string
): Promise<Record<string, unknown>> {
  // Fetch current prompt and model from DB
  const { data: promptData, error: promptError } = await supabase
    .rpc('get_current_prompt', { p_type: 'categorization' })
    .single();

  if (promptError || !promptData) {
    throw new Error('Failed to fetch categorization prompt from database');
  }

  const r = await fetch(`${OPENROUTER_BASE}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${OPENROUTER_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: promptData.model_string,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content: promptData.prompt_template_text,
        },
        { role: "user", content: text },
      ],
    }),
  });
  const d = await r.json();
  try {
    return JSON.parse(d.choices[0].message.content);
  } catch {
    return {
      topics: ["uncategorized"],
      type: "observation",
      visibility: ["uncategorized"],
    };
  }
}

async function applyTagRules(
    visibility: string[]
): Promise<string[]> {
  const { data: rules, error } = await supabase
      .from("tag_rules")
      .select("if_present, remove_tag")
      .eq("active", true);

  if (error || !rules || rules.length === 0) return visibility;

  let result = [...visibility];
  for (const rule of rules) {
    if (result.includes(rule.if_present)) {
      result = result.filter((tag: string) => tag !== rule.remove_tag);
    }
  }
  return result;
}

Deno.serve(async (req: Request): Promise<Response> => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }

  if (req.method !== "POST") {
    return new Response(
        JSON.stringify({ error: "Method not allowed" }),
        { status: 405, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } }
    );
  }

  const headers = { ...CORS_HEADERS, "Content-Type": "application/json" };

  try {
    const body = await req.json();
    const secret = body.secret || req.headers.get("x-capture-secret") || "";
    const thought: string = body.thought || "";
    const vizOverride: string = body.visibility_override || "";

    // Auth check
    if (secret !== CAPTURE_SECRET) {
      return new Response(
          JSON.stringify({ error: "Invalid secret" }),
          { status: 401, headers }
      );
    }

    if (!thought.trim()) {
      return new Response(
          JSON.stringify({ error: "No thought provided" }),
          { status: 400, headers }
      );
    }

    // Embed and classify in parallel
    const [embedding, metadata] = await Promise.all([
      JSON.stringify(getEmbedding(thought)),
      extractMetadata(thought),
    ]);

    // Apply visibility override if provided
    if (vizOverride.trim()) {
      metadata.visibility = vizOverride
          .split(",")
          .map((s: string) => s.trim().toLowerCase())
          .filter(Boolean);
    }

    // Apply deterministic tag rules (e.g., romance removes sfw)
    if (Array.isArray(metadata.visibility)) {
      metadata.visibility = await applyTagRules(
          metadata.visibility as string[]
      );
    }

    const { error } = await supabase.from("thoughts").insert({
      content: thought,
      embedding,
      metadata: { ...metadata, source: "web-form" },
      submitted_by: "user",
      evidence_basis: "user typed in web form",
    });

    if (error) {
      return new Response(
          JSON.stringify({ success: false, error: error.message }),
          { status: 500, headers }
      );
    }

    return new Response(
        JSON.stringify({ success: true, thought, metadata }),
        { status: 200, headers }
    );
  } catch (err) {
    return new Response(
        JSON.stringify({
          success: false,
          error: err instanceof Error ? err.message : "Unknown error",
        }),
        { status: 500, headers }
    );
  }
});