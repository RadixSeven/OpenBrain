import { createClient } from "npm:@supabase/supabase-js@2.47.10";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const OPENROUTER_API_KEY = Deno.env.get("OPENROUTER_API_KEY")!;
const CAPTURE_SECRET = Deno.env.get("CAPTURE_SECRET")!;

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
- "visibility": array of applicable labels from: "sfw", "personal", "work", "technical", "health", "financial", "relationship"
  A thought can have multiple labels. "sfw" means safe for a work context with no private/sensitive content.
  Default to ["sfw"] if the thought is clearly innocuous.
  Most thoughts should include "sfw" unless they contain genuinely private content.
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

async function applyTagRules(
  visibility: string[]
): Promise<string[]> {
  // Fetch active rules from the database
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

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderHTML(
  result?: {
    success: boolean;
    thought?: string;
    metadata?: Record<string, unknown>;
    error?: string;
  },
  authed = false
): string {
  const resultHTML = result
    ? result.success
      ? `<div class="result success">
           <h3>&#10003; Captured</h3>
           <p class="thought-echo">${escapeHtml(result.thought || "")}</p>
           <div class="meta-grid">
             <div class="meta-item"><span class="label">Type</span><span class="value">${
               result.metadata?.type || "—"
             }</span></div>
             <div class="meta-item"><span class="label">Topics</span><span class="value">${
               Array.isArray(result.metadata?.topics)
                 ? (result.metadata!.topics as string[]).join(", ")
                 : "—"
             }</span></div>
             <div class="meta-item"><span class="label">Visibility</span><span class="value">${
               Array.isArray(result.metadata?.visibility)
                 ? (result.metadata!.visibility as string[]).join(", ")
                 : "—"
             }</span></div>
             ${
               Array.isArray(result.metadata?.people) &&
               (result.metadata!.people as string[]).length > 0
                 ? `<div class="meta-item"><span class="label">People</span><span class="value">${(
                     result.metadata!.people as string[]
                   ).join(", ")}</span></div>`
                 : ""
             }
             ${
               Array.isArray(result.metadata?.action_items) &&
               (result.metadata!.action_items as string[]).length > 0
                 ? `<div class="meta-item"><span class="label">Action items</span><span class="value">${(
                     result.metadata!.action_items as string[]
                   ).join("; ")}</span></div>`
                 : ""
             }
           </div>
         </div>`
      : `<div class="result error"><h3>&#10007; Error</h3><p>${escapeHtml(
          result.error || "Unknown error"
        )}</p></div>`
    : "";

  const formSection = authed
    ? `<form method="POST" class="capture-form" id="captureForm">
         <input type="hidden" name="secret" id="hiddenSecret" value="">
         <textarea name="thought" placeholder="Type a thought..." rows="4" required autofocus></textarea>
         <div class="form-row">
           <label class="viz-label">Override visibility (optional):
             <input type="text" name="visibility_override"
                    placeholder="e.g. sfw, work, technical" />
           </label>
           <button type="submit">Capture</button>
         </div>
       </form>
       ${resultHTML}
       <div class="history-link"><a href="#" id="logoutLink">Lock</a></div>`
    : `<form method="POST" class="login-form" id="loginForm">
         <input type="password" name="secret" placeholder="Enter capture secret"
                required autofocus />
         <button type="submit">Unlock</button>
       </form>`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Open Brain — Capture</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, system-ui, sans-serif;
      background: #0a0a0a; color: #e0e0e0;
      display: flex; justify-content: center;
      padding: 2rem 1rem; min-height: 100vh;
    }
    .container { max-width: 600px; width: 100%; }
    h1 { font-size: 1.4rem; margin-bottom: 1.5rem; color: #fff; }
    textarea {
      width: 100%; padding: 0.75rem; font-size: 1rem;
      background: #1a1a1a; color: #e0e0e0;
      border: 1px solid #333; border-radius: 6px;
      resize: vertical; font-family: inherit;
    }
    textarea:focus, input:focus { outline: none; border-color: #4a9eff; }
    input[type="password"], input[type="text"] {
      width: 100%; padding: 0.75rem; font-size: 1rem;
      background: #1a1a1a; color: #e0e0e0;
      border: 1px solid #333; border-radius: 6px; font-family: inherit;
    }
    button {
      padding: 0.75rem 1.5rem; font-size: 1rem;
      background: #4a9eff; color: #fff; border: none;
      border-radius: 6px; cursor: pointer; white-space: nowrap;
    }
    button:hover { background: #3a8eef; }
    .form-row {
      display: flex; gap: 0.75rem; margin-top: 0.75rem;
      align-items: flex-end;
    }
    .viz-label { flex: 1; font-size: 0.85rem; color: #888; }
    .viz-label input { margin-top: 0.3rem; }
    .login-form { display: flex; gap: 0.75rem; }
    .login-form input { flex: 1; }
    .result { margin-top: 1.5rem; padding: 1rem; border-radius: 6px; }
    .result.success { background: #0d2818; border: 1px solid #1a5c2e; }
    .result.error { background: #2a0d0d; border: 1px solid #5c1a1a; }
    .result h3 { font-size: 1rem; margin-bottom: 0.5rem; }
    .thought-echo {
      font-style: italic; color: #aaa;
      margin-bottom: 0.75rem; padding-bottom: 0.75rem;
      border-bottom: 1px solid #333;
    }
    .meta-grid {
      display: grid; grid-template-columns: 1fr 1fr;
      gap: 0.4rem 1rem;
    }
    .meta-item { display: flex; flex-direction: column; }
    .meta-item .label {
      font-size: 0.75rem; color: #666;
      text-transform: uppercase; letter-spacing: 0.05em;
    }
    .meta-item .value { font-size: 0.9rem; }
    .history-link {
      margin-top: 1.5rem; text-align: right; font-size: 0.85rem;
    }
    .history-link a { color: #666; text-decoration: none; }
    .history-link a:hover { color: #999; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Open Brain</h1>
    ${formSection}
  </div>
  <script>
    // Persist the secret in sessionStorage so the form keeps working across captures
    const loginForm = document.getElementById('loginForm');
    const captureForm = document.getElementById('captureForm');
    const logoutLink = document.getElementById('logoutLink');

    if (loginForm) {
      loginForm.addEventListener('submit', function() {
        const pw = loginForm.querySelector('input[type="password"]');
        if (pw) sessionStorage.setItem('ob_secret', pw.value);
      });
    }

    if (captureForm) {
      const hidden = document.getElementById('hiddenSecret');
      if (hidden) hidden.value = sessionStorage.getItem('ob_secret') || '';
      captureForm.addEventListener('submit', function() {
        if (hidden) hidden.value = sessionStorage.getItem('ob_secret') || '';
      });
    }

    if (logoutLink) {
      logoutLink.addEventListener('click', function(e) {
        e.preventDefault();
        sessionStorage.removeItem('ob_secret');
        window.location.reload();
      });
    }
  </script>
</body>
</html>`;
}

Deno.serve(async (req: Request): Promise<Response> => {
  const HEADERS = { "Content-Type": "text/html; charset=utf-8" }

  // --- GET: serve the login form ---
  if (req.method === "GET") {
    return new Response(renderHTML(undefined, false), {
      headers: HEADERS,
    });
  }

  // --- POST: authenticate or capture ---
  if (req.method === "POST") {
    const formData = await req.formData();
    const secret = formData.get("secret")?.toString() || "";
    const thought = formData.get("thought")?.toString() || "";
    const vizOverride = formData.get("visibility_override")?.toString() || "";

    // Auth check
    if (secret !== CAPTURE_SECRET) {
      return new Response(renderHTML(undefined, false), {
        headers: HEADERS,
      });
    }

    // If no thought, they just authenticated — show the capture form
    if (!thought.trim()) {
      return new Response(renderHTML(undefined, true), {
        headers: HEADERS,
      });
    }

    // --- Capture the thought ---
    try {
      const [embedding, metadata] = await Promise.all([
        getEmbedding(thought),
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
          renderHTML({ success: false, error: error.message }, true),
          { headers: HEADERS }
        );
      }

      return new Response(
        renderHTML({ success: true, thought, metadata }, true),
        { headers: HEADERS }
      );
    } catch (err) {
      return new Response(
        renderHTML(
          {
            success: false,
            error: err instanceof Error ? err.message : "Unknown error",
          },
          true
        ),
        { headers: HEADERS }
      );
    }
  }

  return new Response("Method not allowed", { status: 405, headers: HEADERS });
});