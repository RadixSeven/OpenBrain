import "jsr:@supabase/functions-js/edge-runtime.d.ts";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { Hono } from "hono";
import { z } from "zod";
import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const OPENROUTER_API_KEY = Deno.env.get("OPENROUTER_API_KEY")!;
const OPENROUTER_BASE = "https://openrouter.ai/api/v1";

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

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
  if (!r.ok) {
    const msg = await r.text().catch(() => "");
    throw new Error(`OpenRouter embeddings failed: ${r.status} ${msg}`);
  }
  const d = await r.json();
  return d.data[0].embedding;
}

async function extractMetadata(
    text: string
): Promise<Record<string, unknown>> {
  const r = await fetch(`${OPENROUTER_BASE}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${OPENROUTER_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "openai/gpt-4o-mini",
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content: `Extract metadata from the user's captured thought. Return JSON with:
- "people": array of people mentioned (empty if none)
- "action_items": array of implied to-dos (empty if none)
- "dates_mentioned": array of dates YYYY-MM-DD (empty if none)
- "topics": array of 1-3 short topic tags (always at least one)
- "type": one of "observation", "task", "idea", "reference", "person_note"
- "visibility": array of applicable labels from: "sfw", "personal", "work",
  "technical", "health", "financial", "romantic_or_sexual_relationship",
  "family_relationship", "other_relationship", "lgbtq_identity", "activism"
  A thought can have multiple labels. "sfw" means safe for a work context with no private/sensitive content.
  The user has two names: Eric David Moyer and Kind Loving Truth. Anything mentioning Kind Loving Truth
  (or just Kind or Kind Truth) is not safe for work.
  Anything related the user's LGBTQIA+ identity is not safe for work.
  Default to ["sfw"] if the thought is clearly innocuous.
  Thoughts should include "sfw" unless they contain genuinely private content.
Only extract what's explicitly there.`,
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
      visibility: ["sfw"],
    };
  }
}

async function applyTagRules(visibility: string[]): Promise<string[]> {
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

// --- Hono app with auth middleware ---

const app = new Hono().basePath("/open-brain-mcp");

app.all("*", async (c) => {
  // 1. Extract and validate the access key (header preferred, URL fallback)
  const brainKey =
      c.req.header("x-brain-key") ||
      new URL(c.req.url).searchParams.get("key");
  if (!brainKey) {
    return c.json({ error: "Missing x-brain-key header or ?key= param" }, 401);
  }

  const { data: keyData, error: keyError } = await supabase.rpc(
      "validate_access_key",
      { raw_key: brainKey }
  );

  if (keyError || !keyData || keyData.length === 0) {
    return c.json({ error: "Invalid or revoked key" }, 401);
  }

  const keyRecord = keyData[0];
  const keyFilters = keyRecord.filters || {};
  const visFilter: string[] | null = keyFilters.visibility || null;

  // 2. Create an MCP server scoped to this key's permissions
  const server = new McpServer({
    name: `open-brain (${keyRecord.key_name})`,
    version: "1.0.0",
  });

  // --- Tool: Semantic Search ---
  server.registerTool(
      "search_thoughts",
      {
        title: "Search Thoughts",
        description:
            "Search stored thoughts by semantic meaning. Returns the most relevant matches.",
        inputSchema: {
          query: z.string().describe("What to search for"),
          threshold: z
              .number()
              .min(0)
              .max(1)
              .default(0.5)
              .describe("Minimum similarity (0-1, lower = broader)"),
          count: z
              .number()
              .min(1)
              .max(50)
              .default(10)
              .describe("Max results to return"),
        },
      },
      async ({ query, threshold, count }) => {
        const embedding = await getEmbedding(query);

        const { data, error } = await supabase.rpc("match_thoughts", {
          query_embedding: embedding,
          match_threshold: threshold || 0.5,
          match_count: count || 10,
          filter: {},
          visibility_filter: visFilter,
        });

        if (error) {
          return {
            content: [{ type: "text" as const, text: `Search error: ${error.message}` }],
          };
        }

        if (!data || data.length === 0) {
          return {
            content: [
              {
                type: "text" as const,
                text: "No matching thoughts found. Try a lower threshold or different query.",
              },
            ],
          };
        }

        const results = data
            .map(
                (t: {
                  content: string;
                  similarity: number;
                  metadata: Record<string, unknown>;
                  submitted_by: string;
                  evidence_basis: string;
                  created_at: string;
                }) => {
                  const meta = t.metadata || {};
                  const date = new Date(t.created_at).toLocaleDateString();
                  let entry = `[${date} | similarity: ${t.similarity.toFixed(2)} | by: ${t.submitted_by}]\n${t.content}`;
                  if (t.evidence_basis && t.evidence_basis !== "user typed in web form")
                    entry += `\nSource: ${t.evidence_basis}`;
                  if (Array.isArray(meta.topics) && meta.topics.length > 0)
                    entry += `\nTopics: ${(meta.topics as string[]).join(", ")}`;
                  if (meta.type) entry += ` | Type: ${meta.type}`;
                  return entry;
                }
            )
            .join("\n\n---\n\n");

        return {
          content: [
            {
              type: "text" as const,
              text: `Found ${data.length} matching thoughts:\n\n${results}`,
            },
          ],
        };
      }
  );

  // --- Tool: List Thoughts ---
  server.registerTool(
      "list_thoughts",
      {
        title: "List Recent Thoughts",
        description:
            "List recently captured thoughts with optional filters by type, topic, person, time range, or content pattern.",
        inputSchema: {
          count: z
              .number()
              .min(1)
              .max(50)
              .default(10)
              .describe("Number of thoughts to return"),
          type: z
              .string()
              .optional()
              .describe(
                  "Filter by type: observation, task, idea, reference, person_note"
              ),
          topic: z.string().optional().describe("Filter by topic tag"),
          person: z
              .string()
              .optional()
              .describe("Filter by person mentioned"),
          days: z
              .number()
              .optional()
              .describe("Only thoughts from the last N days"),
          pattern: z
              .string()
              .optional()
              .describe(
                  "Regex pattern to filter thought content (case-insensitive)"
              ),
        },
      },
      async ({ count, type, topic, person, days, pattern }) => {
        try {
          const { data, error } = await supabase.rpc(
              "list_thoughts_filtered",
              {
                result_count: count || 10,
                filter_type: type || null,
                filter_topic: topic || null,
                filter_person: person || null,
                filter_days: days || null,
                content_pattern: pattern || null,
                visibility_filter: visFilter,
              }
          );

          if (error) {
            return {
              content: [
                {
                  type: "text" as const,
                  text: `Error listing thoughts: ${error.message}`,
                },
              ],
              isError: true,
            };
          }

          if (!data || data.length === 0) {
            return {
              content: [
                {
                  type: "text" as const,
                  text: "No thoughts matched the given filters.",
                },
              ],
            };
          }

          const results = (data as {
            content: string;
            metadata: Record<string, unknown>;
            submitted_by: string;
            evidence_basis: string;
            created_at: string;
          }[])
              .map((t, i) => {
                const meta = t.metadata || {};
                const date = new Date(t.created_at).toLocaleDateString();
                const tags = Array.isArray(meta.topics)
                    ? (meta.topics as string[]).join(", ")
                    : "";
                let entry = `${i + 1}. [${date}] (${meta.type || "??"}${tags ? " — " + tags : ""}) [by: ${t.submitted_by}]\n   ${t.content}`;
                if (
                    t.evidence_basis &&
                    t.evidence_basis !== "user typed in web form"
                )
                  entry += `\n   Source: ${t.evidence_basis}`;
                if (Array.isArray(meta.people) && meta.people.length > 0)
                  entry += `\n   People: ${(meta.people as string[]).join(", ")}`;
                if (
                    Array.isArray(meta.action_items) &&
                    meta.action_items.length > 0
                )
                  entry += `\n   Actions: ${(meta.action_items as string[]).join("; ")}`;
                return entry;
              })
              .join("\n\n");

          return {
            content: [
              {
                type: "text" as const,
                text: `${data.length} thought(s):\n\n${results}`,
              },
            ],
          };
        } catch (err: unknown) {
          return {
            content: [
              {
                type: "text" as const,
                text: `Error: ${(err as Error).message}`,
              },
            ],
            isError: true,
          };
        }
      }
  );

  // --- Tool: Thought Stats ---
  server.registerTool(
      "thought_stats",
      {
        title: "Thought Statistics",
        description:
            "Get a summary of stored thoughts: totals, types, top topics, and people mentioned.",
        inputSchema: {},
      },
      async () => {
        try {
          // Fetch all metadata for visible thoughts
          let query = supabase
              .from("thoughts")
              .select("metadata, created_at")
              .order("created_at", { ascending: false });

          if (visFilter) {
            query = query.or(
                visFilter
                    .map((v: string) => `metadata->visibility.cs.["${v}"]`)
                    .join(",")
            );
          }

          const { data, error } = await query;

          if (error) {
            return {
              content: [
                {
                  type: "text" as const,
                  text: `Stats error: ${error.message}`,
                },
              ],
              isError: true,
            };
          }

          const total = data?.length ?? 0;

          if (!data || total === 0) {
            return {
              content: [
                {
                  type: "text" as const,
                  text: "No thoughts captured yet.",
                },
              ],
            };
          }

          const types: Record<string, number> = {};
          const topics: Record<string, number> = {};
          const people: Record<string, number> = {};

          for (const r of data) {
            const m = (r.metadata || {}) as Record<string, unknown>;
            if (m.type)
              types[m.type as string] = (types[m.type as string] || 0) + 1;
            if (Array.isArray(m.topics))
              for (const t of m.topics)
                topics[t as string] = (topics[t as string] || 0) + 1;
            if (Array.isArray(m.people))
              for (const p of m.people)
                people[p as string] = (people[p as string] || 0) + 1;
          }

          const sort = (o: Record<string, number>): [string, number][] =>
              Object.entries(o)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 10);

          const oldest = data[data.length - 1].created_at;
          const newest = data[0].created_at;

          const lines: string[] = [
            `Total thoughts: ${total}`,
            `Date range: ${new Date(oldest).toLocaleDateString()} → ${new Date(newest).toLocaleDateString()}`,
            "",
            "Types:",
            ...sort(types).map(([k, v]) => `  ${k}: ${v}`),
          ];

          if (Object.keys(topics).length) {
            lines.push("", "Top topics:");
            for (const [k, v] of sort(topics)) lines.push(`  ${k}: ${v}`);
          }

          if (Object.keys(people).length) {
            lines.push("", "People mentioned:");
            for (const [k, v] of sort(people)) lines.push(`  ${k}: ${v}`);
          }

          lines.push("", `Key: ${keyRecord.key_name}`);

          return {
            content: [{ type: "text" as const, text: lines.join("\n") }],
          };
        } catch (err: unknown) {
          return {
            content: [
              {
                type: "text" as const,
                text: `Error: ${(err as Error).message}`,
              },
            ],
            isError: true,
          };
        }
      }
  );

  // --- Tool: Capture Thought ---
  server.registerTool(
      "capture_thought",
      {
        title: "Capture Thought",
        description:
            "Save a new thought to the Open Brain, extracting metadata automatically. Use this when the user wants to remember something — notes, insights, decisions, observations about people, or migrated content from other systems. Or you think you may need to remember something in the future.",
        inputSchema: {
          content: z
              .string()
              .describe(
                  "The thought to capture — a clear, standalone statement that will make sense when retrieved later"
              ),
          evidence_basis: z
              .string()
              .optional()
              .describe(
                  "How this information was sourced, e.g. 'summarized from meeting notes', 'user dictated'. Defaults to automatic provenance tracking."
              ),
        },
      },
      async ({ content, evidence_basis }) => {
        try {
          const [embedding, metadata] = await Promise.all([
            getEmbedding(content),
            extractMetadata(content),
          ]);

          // Apply deterministic tag rules
          if (Array.isArray(metadata.visibility)) {
            metadata.visibility = await applyTagRules(
                metadata.visibility as string[]
            );
          }

          const submittedBy = `mcp ${keyRecord.key_name}`;
          const basis =
              evidence_basis || `captured via MCP by ${keyRecord.key_name}`;

          const { error } = await supabase.from("thoughts").insert({
            content,
            embedding,
            metadata: { ...metadata, source: "mcp" },
            submitted_by: submittedBy,
            evidence_basis: basis,
          });

          if (error) {
            return {
              content: [
                {
                  type: "text" as const,
                  text: `Failed to capture: ${error.message}`,
                },
              ],
              isError: true,
            };
          }

          const meta = metadata as Record<string, unknown>;
          let confirmation = `Captured as ${meta.type || "thought"}`;
          if (Array.isArray(meta.topics) && meta.topics.length)
            confirmation += ` — ${(meta.topics as string[]).join(", ")}`;
          if (Array.isArray(meta.people) && meta.people.length)
            confirmation += ` | People: ${(meta.people as string[]).join(", ")}`;
          if (Array.isArray(meta.action_items) && meta.action_items.length)
            confirmation += ` | Actions: ${(meta.action_items as string[]).join("; ")}`;
          if (Array.isArray(meta.visibility))
            confirmation += ` | Visibility: ${(meta.visibility as string[]).join(", ")}`;

          return {
            content: [{ type: "text" as const, text: confirmation }],
          };
        } catch (err: unknown) {
          return {
            content: [
              {
                type: "text" as const,
                text: `Error: ${(err as Error).message}`,
              },
            ],
            isError: true,
          };
        }
      }
  );

  // 3. Handle the MCP request
  const transport = new WebStandardStreamableHTTPServerTransport();
  await server.connect(transport);
  return transport.handleRequest(c.req.raw);
});

Deno.serve(app.fetch);