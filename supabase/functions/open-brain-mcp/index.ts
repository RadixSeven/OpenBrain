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
  const d = await r.json();
  return d.data[0].embedding;
}

// --- Hono app with auth middleware ---

const app = new Hono().basePath("/open-brain-mcp");

app.all("*", async (c) => {
  // 1. Extract and validate the access key
  const brainKey = c.req.header("x-brain-key");
  if (!brainKey) {
    return c.json({ error: "Missing x-brain-key header" }, 401);
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

  // --- Tool: Browse Recent ---
  server.registerTool(
      "browse_recent",
      {
        title: "Browse Recent Thoughts",
        description: "Browse recently captured thoughts in reverse chronological order.",
        inputSchema: {
          count: z
              .number()
              .min(1)
              .max(50)
              .default(10)
              .describe("Number of recent thoughts to fetch"),
        },
      },
      async ({ count }) => {
        let query = supabase
            .from("thoughts")
            .select("id, content, metadata, submitted_by, evidence_basis, created_at")
            .order("created_at", { ascending: false })
            .limit(count || 10);

        // Apply visibility filter from the access key
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
            content: [{ type: "text" as const, text: `Browse error: ${error.message}` }],
          };
        }

        if (!data || data.length === 0) {
          return {
            content: [{ type: "text" as const, text: "No thoughts captured yet." }],
          };
        }

        const results = data
            .map(
                (t: {
                  content: string;
                  metadata: Record<string, unknown>;
                  submitted_by: string;
                  evidence_basis: string;
                  created_at: string;
                }) => {
                  const meta = t.metadata || {};
                  const date = new Date(t.created_at).toLocaleDateString();
                  let entry = `[${date} | by: ${t.submitted_by}] ${t.content}`;
                  if (t.evidence_basis && t.evidence_basis !== "user typed in web form")
                    entry += `\nSource: ${t.evidence_basis}`;
                  if (Array.isArray(meta.topics) && meta.topics.length > 0)
                    entry += `\nTopics: ${(meta.topics as string[]).join(", ")}`;
                  return entry;
                }
            )
            .join("\n\n---\n\n");

        return {
          content: [
            {
              type: "text" as const,
              text: `${data.length} recent thoughts:\n\n${results}`,
            },
          ],
        };
      }
  );

  // --- Tool: Stats ---
  server.registerTool(
      "brain_stats",
      {
        title: "Brain Stats",
        description:
            "Get an overview of your stored thoughts — total count, recent activity, top topics.",
        inputSchema: {},
      },
      async () => {
        // Total count (respecting visibility)
        let countQuery = supabase
            .from("thoughts")
            .select("id", { count: "exact", head: true });

        if (visFilter) {
          countQuery = countQuery.or(
              visFilter
                  .map((v: string) => `metadata->visibility.cs.["${v}"]`)
                  .join(",")
          );
        }

        const { count: total } = await countQuery;

        // Most recent thought
        let recentQuery = supabase
            .from("thoughts")
            .select("created_at")
            .order("created_at", { ascending: false })
            .limit(1);

        if (visFilter) {
          recentQuery = recentQuery.or(
              visFilter
                  .map((v: string) => `metadata->visibility.cs.["${v}"]`)
                  .join(",")
          );
        }

        const { data: recent } = await recentQuery;

        const lastDate = recent?.[0]?.created_at
            ? new Date(recent[0].created_at).toLocaleString()
            : "never";

        return {
          content: [
            {
              type: "text" as const,
              text: `Brain stats:\n- Total thoughts (visible to this key): ${total ?? 0}\n- Most recent: ${lastDate}\n\nKey: ${keyRecord.key_name}`,
            },
          ],
        };
      }
  );

  // 3. Handle the MCP request
  const transport = new WebStandardStreamableHTTPServerTransport();
  await server.connect(transport);
  return transport.handleRequest(c.req.raw);
});

Deno.serve(app.fetch);