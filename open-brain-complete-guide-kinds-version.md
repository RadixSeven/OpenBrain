# Open Brain — Complete Setup Guide (Privacy-First Edition)

*Based on the [Open Brain guide by Nate B. Jones](https://natebjones.com). Modified to replace Slack with a private web form, add per-key content filtering, and support multiple access keys for different agents.*

---

## What You're Building

A personal knowledge system with semantic search and an open protocol. You type a thought into a web form — it automatically gets embedded, classified, and stored in your database — you see a confirmation showing what was captured. Then an MCP server lets any AI assistant search your brain by meaning.

The key privacy features in this version:

- **No Slack.** Your thoughts go directly from a password-protected web form to your database. No third-party chat platform sees them.
- **Filtered access.** Each MCP access key maps to a filter profile. You can give a work agent a key that only sees thoughts tagged "sfw," while your personal setup sees everything.
- **Multiple secrets.** Different agents get different keys, stored hashed in your database. You can name them, track usage, and revoke them independently.

### What You Need

About 45 minutes and zero coding experience. You'll copy and paste everything.

### Services (All Free Tier)

- **Supabase** — Your database — stores everything, hosts your server functions
- **OpenRouter** — Your AI gateway — generates embeddings and classifies your thoughts

### If You Get Stuck

Supabase has a free built-in AI assistant in every project dashboard. Look for the chat icon in the bottom-right corner. It has access to all of Supabase's documentation and can help with every Supabase-specific step in this guide. It can walk you through where to click, fix SQL errors if you paste the error message, explain terminal commands, interpret Edge Function logs, and explain Supabase concepts in plain English.

### Cost Breakdown

| Service | Cost |
|---|---|
| Supabase (free tier) | $0 |
| Embeddings (text-embedding-3-small) | ~$0.02 / million tokens |
| Metadata extraction (gpt-4o-mini) | ~$0.15 / million input tokens |

For 20 thoughts/day: roughly $0.10–0.30/month in API costs.

---

## Credential Tracker

You're going to generate API keys, passwords, and IDs across multiple services. Copy the block below into a text editor and fill it in as you go.

```
OPEN BRAIN — CREDENTIAL TRACKER
--------------------------------------

SUPABASE
  Account email:      ____________
  Account password:   ____________
  Database password:  ____________  <- Step 1
  Project name:       ____________
  Project ref:        ____________  <- Step 1
  Project URL:        ____________  <- Step 3
  Service role key:   ____________  <- Step 3

OPENROUTER
  Account email:      ____________
  Account password:   ____________
  API key:            ____________  <- Step 4

GENERATED DURING SETUP
  Capture Form URL:   ____________  <- Step 7
  Capture Form Secret:____________  <- Step 7
  MCP Server URL:     ____________  <- Step 10
  MCP Keys:           (managed in access_keys table — Step 9)

--------------------------------------
```

> **Seriously — copy that now.** You'll thank yourself at Step 7.

---

## Two Parts

**Part 1 — Capture (Steps 1–8):** Web Form → Edge Function → Supabase. Type a thought, it gets embedded and classified automatically, you see the result on screen.

**Part 2 — Retrieval (Steps 9–12):** Hosted MCP Server → Any AI. Connect Claude, ChatGPT, or any MCP client to your brain with a URL and a key that controls what they can see.

---

## Part 1 — Capture

### Step 1: Create Your Supabase Project

Supabase is your database. It stores your thoughts as raw text, vector embeddings, and structured metadata. It also gives you a REST API and serverless functions automatically.

1. Go to [supabase.com](https://supabase.com) and sign up (GitHub login is fastest)
2. Click **New Project** in the dashboard
3. Pick your organization (default is fine)
4. Set Project name: `open-brain` (or whatever you want)
5. Generate a strong **Database password** — paste into credential tracker NOW
6. Pick the **Region** closest to you
7. Click **Create new project** and wait 1–2 minutes

> Grab your **Project ref** — it's the random string in your dashboard URL: `supabase.com/dashboard/project/THIS_PART`. Paste it into the tracker.

---

### Step 2: Set Up the Database

Several SQL commands, pasted one at a time. This creates your storage tables, search functions, and security policies.

#### Enable Extensions

In the left sidebar: **Database → Extensions** → search for "vector" → flip **pgvector** ON.

Then search for "pgcrypto" → flip **pgcrypto** ON. (We need this to hash access keys.)

#### Create the Thoughts Table

In the left sidebar: **SQL Editor → New query** → paste and Run:

```sql
-- Core thoughts table
create table thoughts (
  id uuid primary key default gen_random_uuid(),
  content text not null,
  embedding vector(1536),
  metadata jsonb default '{}'::jsonb,
  submitted_by text not null default 'user',
    -- Who submitted this thought. 'user' for manual web form entry.
    -- Future automated sources might be 'daily-digest-bot', 'meeting-summarizer', etc.
  evidence_basis text not null default 'user typed in web form',
    -- How this information was sourced. Provenance trail.
    -- Examples: 'user typed in web form', 'SuperWorldModel27 summarized from audio',
    -- 'extracted from PDF upload', 'daily journal prompt response'
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
```

> **Design note on truth maintenance.** A memory isn't just a collection of statements — it's a collection of statements that need pruning and updating. There are several distinct ways a stored thought can be or become wrong:
>
> - **Temporal decay.** A statement was true when written but has a natural expiration. "Jim is looking for a new job" is likely false within six months. Some facts are durable ("KC grew up in Indiana"), others are inherently transient ("Sarah is considering leaving her job").
> - **Transcription error.** The source material was misheard or garbled. Automatic dictation software can turn "KC" into "Casey," or "I want to visit Lego Land" into "Carol wants to visit Leland." These were never true — the `evidence_basis` column helps flag thoughts with error-prone provenance (e.g., "summarized from audio" deserves more skepticism than "user typed in web form").
> - **Honest mistake.** The submitter believed something that was wrong. "The meeting is on Thursday" when it was actually Wednesday.
> - **Superseded information.** A newer thought contradicts an older one. "Jim got the new job" supersedes "Jim is looking for a new job."
>
> The `evidence_basis` column is a first step — it tells you *how confident to be* in a thought based on how it was sourced. But a full truth maintenance system would also need to handle corrections, supersession, and expiration. Some possible future additions:
>
> - A `corrections` table linking a correcting thought to the thought it corrects, with a note on what changed.
> - A `status` column on thoughts (e.g., `current`, `superseded`, `retracted`, `expired`) so that search can prefer current information.
> - A `confidence` or `expected_shelf_life` field set at capture time — the LLM could estimate whether a thought describes a transient state or a durable fact.
> - A periodic review process that surfaces old transient thoughts for re-evaluation.
>
> None of this is implemented here. The schema is designed so these additions are non-breaking — they're new columns with defaults or new tables with foreign keys into `thoughts`. The important thing for now is that `submitted_by` and `evidence_basis` are always populated, giving future tooling something to work with.

#### Create the Access Keys Table

> **Change from original guide:** The original used a single environment variable (`MCP_ACCESS_KEY`) for authentication. This version stores keys in the database so you can have multiple keys with different filter rules.

New query → paste and Run:

```sql
-- Access keys for MCP server authentication and filtering
create table access_keys (
  id uuid primary key default gen_random_uuid(),
  name text not null,                    -- human label: "work-copilot", "personal-claude"
  key_hash text not null unique,         -- SHA-256 hash of the actual key
  filters jsonb not null default '{}'::jsonb,
    -- {} means "no restrictions, see everything"
    -- {"visibility": ["sfw"]} means "only thoughts containing 'sfw' in visibility"
    -- {"visibility": ["sfw","work"]} means "sfw OR work"
  active boolean not null default true,
  created_at timestamptz default now(),
  last_used_at timestamptz
);

-- RLS: service role only
alter table access_keys enable row level security;
create policy "Service role full access on access_keys"
  on access_keys for all
  using (auth.role() = 'service_role');
```

#### Create the Tag Rules Table

This table defines deterministic rules that run *after* the LLM classifies a thought's visibility. If a thought has a given tag, another tag is automatically removed. This is a privacy safety net — the LLM might tag something as both `romance` and `sfw`, but the rule engine will strip `sfw` before storage.

New query → paste and Run:

```sql
-- Deterministic tag implication rules.
-- If a thought has if_present, then remove_tag is stripped from visibility.
create table tag_rules (
  id uuid primary key default gen_random_uuid(),
  if_present text not null,    -- tag that triggers the rule
  remove_tag text not null,    -- tag to remove when if_present is found
  note text,                   -- human-readable explanation
  active boolean not null default true,
  unique(if_present, remove_tag)
);

-- RLS: service role only
alter table tag_rules enable row level security;
create policy "Service role full access on tag_rules"
  on tag_rules for all
  using (auth.role() = 'service_role');

-- Seed the initial rules
insert into tag_rules (if_present, remove_tag, note) values
  ('romance',   'sfw', 'Romance content is not safe for work context'),
  ('sexuality', 'sfw', 'Sexual content is not safe for work context'),
  ('health',    'sfw', 'Health details are private by default'),
  ('financial', 'sfw', 'Financial details are private by default');
```

> You can add, remove, or change rules at any time in the Supabase Table Editor or via SQL — no redeployment needed. The capture function reads the active rules on every submission.

> **How it works:** After the LLM returns its metadata (including its best guess at visibility tags), the capture function fetches all active rules, then for each rule, if `if_present` is found in the visibility array, `remove_tag` is stripped. The LLM might tag a thought `["sfw", "personal", "romance"]` — the rule engine will deterministically produce `["personal", "romance"]` before storage. The MCP server's work key (filtering on `sfw`) will never see it.

#### Create the Search Function

New query → paste and Run:

```sql
-- Semantic search function with visibility filtering
create or replace function match_thoughts(
  query_embedding vector(1536),
  match_threshold float default 0.7,
  match_count int default 10,
  filter jsonb default '{}'::jsonb,
  visibility_filter text[] default null
)
returns table (
  id uuid,
  content text,
  metadata jsonb,
  submitted_by text,
  evidence_basis text,
  similarity float,
  created_at timestamptz
)
language plpgsql
as $$
begin
  return query
  select
    t.id,
    t.content,
    t.metadata,
    t.submitted_by,
    t.evidence_basis,
    1 - (t.embedding <=> query_embedding) as similarity,
    t.created_at
  from thoughts t
  where 1 - (t.embedding <=> query_embedding) > match_threshold
    and (filter = '{}'::jsonb or t.metadata @> filter)
    and (
      visibility_filter is null
      or t.metadata->'visibility' ?| visibility_filter
    )
  order by t.embedding <=> query_embedding
  limit match_count;
end;
$$;
```

> **Change from original guide:** The function now accepts an optional `visibility_filter` parameter. The `?|` operator checks whether the thought's `visibility` array overlaps with the filter array. When `null`, no visibility filtering is applied (you see everything).

#### Create the Key Validation Function

New query → paste and Run:

```sql
-- Validate an access key and return its filters
create or replace function validate_access_key(raw_key text)
returns table (key_id uuid, key_name text, filters jsonb)
language plpgsql security definer
as $$
begin
  return query
  update access_keys
  set last_used_at = now()
  where key_hash = encode(digest(raw_key, 'sha256'), 'hex')
    and active = true
  returning id, name, access_keys.filters;
end;
$$;
```

#### Lock Down Security

One more new query:

```sql
-- Enable Row Level Security on thoughts
alter table thoughts enable row level security;

-- Service role full access only
create policy "Service role full access"
  on thoughts
  for all
  using (auth.role() = 'service_role');
```

#### Quick Verification

**Table Editor** should show three tables: `thoughts`, `access_keys`, and `tag_rules`. The `thoughts` table should have columns: id, content, embedding, metadata, submitted_by, evidence_basis, created_at, updated_at. The `tag_rules` table should have your seeded rules (check that they look right). **Database → Functions** should show `match_thoughts` and `validate_access_key`.

---

### Step 3: Save Your Connection Details

In the left sidebar: **Settings** (gear icon) → **API**. Copy these into your credential tracker:

- **Project URL** — Listed at the top as "URL"
- **Service role key** — Under "Project API keys" → click reveal

> **Treat the service role key like a password.** Anyone with it has full access to your data.

---

### Step 4: Get an OpenRouter API Key

OpenRouter is a universal AI API gateway — one account gives you access to every major model. We're using it for embeddings and lightweight LLM metadata extraction.

Why OpenRouter instead of OpenAI directly? One account, one key, one billing relationship — and it future-proofs you for Claude, Gemini, or any other model later.

1. Go to [openrouter.ai](https://openrouter.ai) and sign up
2. Go to [openrouter.ai/keys](https://openrouter.ai/keys)
3. Click **Create Key**, name it `open-brain`
4. Copy the key into your credential tracker immediately
5. Add $5 in credits under **Credits** (lasts months)

---

### Step 5: Install the Supabase CLI and Link Your Project

> **Change from original guide:** The original had Slack setup as Steps 5–6 and the Edge Function as Step 7. Since we're replacing Slack with a web form, the CLI setup moves earlier.

> **New to the terminal?** The "terminal" is the text-based command line on your computer. On Mac, open the app called **Terminal** (search for it in Spotlight). On Windows, open **PowerShell**. Everything below gets typed there, not in your browser.

#### Install the Supabase CLI

```bash
# Mac with Homebrew
brew install supabase/tap/supabase

# Windows with Scoop (recommended)
# Install Scoop first if you don't have it:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
# Then install Supabase:
scoop bucket add supabase https://github.com/supabase/scoop-bucket.git
scoop install supabase

# Linux or Mac without Homebrew
npm install -g supabase
```

Verify it worked:

```bash
supabase --version
```

#### Log In and Link

```bash
supabase login
supabase link --project-ref YOUR_PROJECT_REF
```

Replace `YOUR_PROJECT_REF` with the project ref from your credential tracker (Step 1).

---

### Step 6: Choose a Capture Form Secret

This is a simple password that protects your capture form. It is NOT the same as MCP access keys — it just prevents random people from submitting thoughts to your database.

Pick something you can type easily on your phone (you'll be typing it once per session). Then set it:

```bash
supabase secrets set CAPTURE_SECRET=your-chosen-password-here
```

Also set your OpenRouter key:

```bash
supabase secrets set OPENROUTER_API_KEY=your-openrouter-key-here
```

> `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are automatically available inside Edge Functions — you don't need to set them.

Paste your chosen capture secret into the credential tracker.

---

### Step 7: Deploy the Capture Form

> **Change from original guide:** This replaces the Slack app, the Slack bot token, the Event Subscriptions, and the `ingest-thought` Edge Function. One function serves the HTML form AND processes submissions.

#### Create the Function

```bash
supabase functions new capture-form
```

#### Write the Code

Open `supabase/functions/capture-form/index.ts` and replace its entire contents with:

```typescript
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
  // --- GET: serve the login form ---
  if (req.method === "GET") {
    return new Response(renderHTML(undefined, false), {
      headers: { "Content-Type": "text/html; charset=utf-8" },
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
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }

    // If no thought, they just authenticated — show the capture form
    if (!thought.trim()) {
      return new Response(renderHTML(undefined, true), {
        headers: { "Content-Type": "text/html; charset=utf-8" },
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
          { headers: { "Content-Type": "text/html; charset=utf-8" } }
        );
      }

      return new Response(
        renderHTML({ success: true, thought, metadata }, true),
        { headers: { "Content-Type": "text/html; charset=utf-8" } }
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
        { headers: { "Content-Type": "text/html; charset=utf-8" } }
      );
    }
  }

  return new Response("Method not allowed", { status: 405 });
});
```

#### Deploy

```bash
supabase functions deploy capture-form --no-verify-jwt
```

> The `--no-verify-jwt` flag disables Supabase's built-in JWT check. Authentication is handled by the capture secret in the form instead.

Copy the Edge Function URL immediately after deployment. It looks like:

```
https://YOUR_PROJECT_REF.supabase.co/functions/v1/capture-form
```

Paste it into your credential tracker as the **Capture Form URL**. Bookmark it, add it to your phone's home screen — this is where you'll capture thoughts.

---

### Step 8: Test Capture

1. Open your Capture Form URL in a browser
2. Enter your capture secret to unlock the form
3. Type a test thought:

```
Sarah mentioned she's thinking about leaving her job to start a consulting business
```

4. Click **Capture**
5. You should see a confirmation on the page showing something like:

```
✓ Captured
Type: person_note
Topics: career, consulting
Visibility: personal
People: Sarah
Action items: Check in with Sarah about consulting plans
```

6. Open Supabase dashboard → **Table Editor → thoughts**. You should see one row with your message, an embedding, metadata including the `visibility` array, `submitted_by` set to `user`, and `evidence_basis` set to `user typed in web form`.

> If that works, try a second thought to verify tag rules are working:

```
I've been having some chest pain when I exercise and need to schedule a doctor visit
```

The LLM should classify this with `health` in visibility. The tag rule engine should then strip `sfw` (if the LLM included it). Check that the confirmation shows visibility without `sfw`. If it does, the rule engine is working.

> If both tests pass, Part 1 is done. You have a working private capture system with deterministic privacy enforcement.

---

## Part 2 — Retrieval

### A Quick Note on Architecture

MCP servers can run locally on your computer or hosted in the cloud. Your capture system already runs on Supabase Edge Functions, and the MCP server works the same way — one more Edge Function, deployed to the same project, reachable from anywhere via a URL. No build steps, no local dependencies, no credentials on your machine.

---

### Step 9: Create Access Keys

> **Change from original guide:** The original had one access key stored as an environment variable. This version stores multiple keys in the database, each with its own filter rules.

#### Generate Keys

For each agent or context you want, generate a random key:

```bash
# Mac/Linux
openssl rand -hex 32

# Windows (PowerShell)
-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
```

#### Register Keys in the Database

Go to Supabase dashboard → **SQL Editor** → New query. For each key:

**Personal key (full access to everything):**

```sql
insert into access_keys (name, key_hash, filters) values (
  'personal-full-access',
  encode(digest('PASTE-YOUR-64-CHAR-KEY-HERE', 'sha256'), 'hex'),
  '{}'::jsonb
);
```

The empty `{}` filter means this key sees all thoughts with no restrictions.

**Work key (SFW content only):**

```sql
insert into access_keys (name, key_hash, filters) values (
  'work-copilot',
  encode(digest('PASTE-YOUR-OTHER-64-CHAR-KEY-HERE', 'sha256'), 'hex'),
  '{"visibility": ["sfw", "work", "technical"]}'::jsonb
);
```

This key only returns thoughts whose `visibility` metadata array contains at least one of `sfw`, `work`, or `technical`.

Save the actual (unhashed) keys somewhere safe — you'll paste them into your AI client configs. The database only stores the hash.

#### Other Filter Examples

| Filter | Meaning |
|---|---|
| `'{}'::jsonb` | No restrictions — sees everything |
| `'{"visibility": ["sfw"]}'::jsonb` | Only thoughts tagged `sfw` |
| `'{"visibility": ["sfw", "work"]}'::jsonb` | Thoughts tagged `sfw` OR `work` |
| `'{"visibility": ["sfw", "technical"]}'::jsonb` | Good for coding agents |

The visibility labels are set at capture time by the LLM. The default set is: `sfw`, `personal`, `work`, `technical`, `health`, `financial`, `relationship`. You can change these by editing the system prompt in the capture function.

---

### Step 10: Deploy the MCP Server

> **Change from original guide:** The original MCP server checked a single env-var key. This version looks up keys in the `access_keys` table and applies per-key filters to every query.

#### Create the Function

```bash
supabase functions new open-brain-mcp
```

#### Add Dependencies

Create `supabase/functions/open-brain-mcp/deno.json`:

```json
{
  "imports": {
    "@modelcontextprotocol/sdk/server/mcp.js": "npm:@modelcontextprotocol/sdk@1.25.3/server/mcp.js",
    "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js": "npm:@modelcontextprotocol/sdk@1.25.3/server/webStandardStreamableHttp.js",
    "hono": "npm:hono@4.9.7",
    "zod": "npm:zod@4.1.13",
    "@supabase/supabase-js": "npm:@supabase/supabase-js@2.47.10"
  }
}
```

#### Write the Server

Open `supabase/functions/open-brain-mcp/index.ts` and replace its entire contents with:

```typescript
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
```

#### Deploy

```bash
supabase functions deploy open-brain-mcp --no-verify-jwt
```

Your MCP server is now live at:

```
https://YOUR_PROJECT_REF.supabase.co/functions/v1/open-brain-mcp
```

Paste this into your credential tracker as the **MCP Server URL**.

---

### Step 11: Connect to Your AI

You need two things from your credential tracker: the MCP Server URL (Step 10) and the access key(s) you generated (Step 9). Each agent gets its own key. The URL is the same for all of them — the key determines what they can see.

#### Claude Desktop

Settings → Developer → Edit Config:

```json
{
  "mcpServers": {
    "open-brain": {
      "type": "streamable-http",
      "url": "https://YOUR_PROJECT_REF.supabase.co/functions/v1/open-brain-mcp",
      "headers": {
        "x-brain-key": "your-personal-full-access-key"
      }
    }
  }
}
```

Restart Claude Desktop. You should see "open-brain" appear in the MCP tools indicator (the hammer icon).

#### Claude Code

```bash
claude mcp add open-brain \
  --transport http \
  --url https://YOUR_PROJECT_REF.supabase.co/functions/v1/open-brain-mcp \
  --header "x-brain-key: your-key-here"
```

#### Work Agent (Filtered to SFW)

Same config pattern, different key:

```json
{
  "mcpServers": {
    "open-brain": {
      "type": "streamable-http",
      "url": "https://YOUR_PROJECT_REF.supabase.co/functions/v1/open-brain-mcp",
      "headers": {
        "x-brain-key": "your-work-sfw-only-key"
      }
    }
  }
}
```

#### Other Clients (Cursor, VS Code Copilot, ChatGPT Desktop, Windsurf)

Every MCP-compatible client follows the same pattern: point it at the URL with the `x-brain-key` header. Check their MCP documentation for where to add remote HTTP servers with custom headers.

---

### Step 12: Use It

Ask your AI naturally. It picks the right tool automatically:

| Prompt | Tool Used |
|---|---|
| "What did I capture about career changes?" | Semantic search |
| "What did I capture this week?" | Browse recent |
| "How many thoughts do I have?" | Stats overview |
| "Find my notes about the API redesign" | Semantic search |
| "Show me my recent ideas" | Browse recent |

---

## Managing Access Keys

### See all keys and last usage

```sql
select name, active, created_at, last_used_at, filters
from access_keys
order by created_at;
```

### Generate and register a new key

```bash
openssl rand -hex 32
```

```sql
insert into access_keys (name, key_hash, filters) values (
  'new-agent-name',
  encode(digest('paste-the-64-char-key-here', 'sha256'), 'hex'),
  '{"visibility": ["sfw"]}'::jsonb
);
```

### Revoke a key

```sql
update access_keys set active = false where name = 'work-copilot';
```

### Delete a key permanently

```sql
delete from access_keys where name = 'old-agent';
```

---

## Managing Tag Rules

Tag rules are your deterministic privacy safety net. They run after every LLM classification, so even if the model tags something as `sfw` when it shouldn't be, the rule engine will catch it.

### See current rules

```sql
select if_present, remove_tag, note, active from tag_rules order by if_present;
```

### Add a new rule

```sql
insert into tag_rules (if_present, remove_tag, note) values
  ('relationship', 'sfw', 'Relationship details are private');
```

### Temporarily disable a rule

```sql
update tag_rules set active = false
where if_present = 'health' and remove_tag = 'sfw';
```

### Delete a rule

```sql
delete from tag_rules
where if_present = 'financial' and remove_tag = 'sfw';
```

### Seeded defaults

The setup script seeds these rules:

| If present | Removes | Rationale |
|---|---|---|
| `romance` | `sfw` | Romance content is not safe for work context |
| `sexuality` | `sfw` | Sexual content is not safe for work context |
| `health` | `sfw` | Health details are private by default |
| `financial` | `sfw` | Financial details are private by default |

You can change these to match your own privacy boundaries. The rules are read from the database on every capture, so changes take effect immediately — no redeployment needed.

> **Note:** Tag rules apply at capture time. They don't retroactively change thoughts already in the database. If you add a new rule and want it to apply to existing thoughts, you'll need to run an update query. For example, after adding a rule that `relationship` removes `sfw`:
>
> ```sql
> update thoughts
> set metadata = jsonb_set(
>   metadata,
>   '{visibility}',
>   (select jsonb_agg(elem)
>    from jsonb_array_elements_text(metadata->'visibility') as elem
>    where elem != 'sfw')
> )
> where metadata->'visibility' ? 'relationship'
>   and metadata->'visibility' ? 'sfw';
> ```

---

## Troubleshooting

If the specific suggestions below don't solve your issue, the Supabase AI assistant (chat icon, bottom-right of your dashboard) can help diagnose anything Supabase-related. Paste the error message and tell it what step you're on.

### Capture Form Issues

**Form shows "Unlock" again after entering the password**

The password is wrong. Double-check what you set in `CAPTURE_SECRET`. You can verify with:

```bash
supabase secrets list
```

**Form submits but nothing appears in the database**

Check Edge Function logs: Supabase dashboard → Edge Functions → capture-form → Logs. Most likely the OpenRouter key is wrong or has no credits.

**Metadata extraction seems off**

That's normal — the LLM is making its best guess with limited context. The metadata is a convenience layer on top of semantic search, not the primary retrieval mechanism. The embedding handles fuzzy matching regardless. You can always override visibility tags manually on the form.

### MCP Server Issues

**AI client says "server disconnected" or tools don't appear**

Check that your URL is exactly right — including `https://` and no trailing slash. The project ref must match your actual project. Try opening the URL in a browser with a POST request to confirm the function is deployed.

**Getting 401 errors**

The access key doesn't match any active key in the `access_keys` table. Verify that:
1. The key you're using matches what you hashed when inserting
2. The key's `active` column is `true`
3. The header name is `x-brain-key` (lowercase, with the dash)

You can test key validation directly:

```sql
select * from validate_access_key('paste-your-actual-key-here');
```

**Search returns no results**

Make sure you captured test thoughts in Part 1 first. Try asking the AI to "search with threshold 0.3" for a wider net. If using a filtered key, make sure your test thoughts have matching visibility tags.

**Work key returns nothing even though thoughts exist**

The thoughts might not have the right visibility tags. Check:

```sql
select content, submitted_by, evidence_basis, metadata->'visibility' as viz
from thoughts
order by created_at desc
limit 10;
```

If visibility arrays are missing or don't include `sfw`, the work key won't match them. You can backfill:

```sql
update thoughts
set metadata = jsonb_set(metadata, '{visibility}', '["sfw"]'::jsonb)
where metadata->'visibility' is null;
```

**Tools work but responses are slow**

First call on a cold function takes a few seconds (Edge Function waking up). Subsequent calls are faster. If consistently slow, check your Supabase project region.

---

## How It Works Under the Hood

When you type a thought in the form: the Edge Function generates an embedding (1536-dimensional vector of meaning) AND extracts metadata via LLM in parallel → both get stored as a single row in Supabase along with the submitter identity (`user`) and evidence basis (`user typed in web form`) → the function renders a confirmation showing what was captured.

When you ask your AI about it: your AI client sends the query to the MCP Edge Function → the function validates your access key and loads its filter rules → generates an embedding of your question → Supabase matches it against stored thoughts by vector similarity, filtered by the key's visibility rules → results come back ranked by meaning, not keywords, with provenance information (who submitted it and how) included.

The embedding is what makes retrieval powerful. "Sarah's thinking about leaving" and "What did I note about career changes?" match semantically even though they share zero keywords. The metadata and visibility tags are a bonus layer for structured filtering on top.

### Swapping Models Later

Because you're using OpenRouter, you can swap models by editing the model strings in the Edge Function code and redeploying. Browse available models at [openrouter.ai/models](https://openrouter.ai/models). Just make sure embedding dimensions match (1536 for the current setup).

---

## What You Just Built

A personal knowledge system where:

- Thoughts go from your browser directly to your database — no third-party chat platform involved
- Every thought gets semantic embeddings and automatic metadata including visibility classification
- Every thought records who submitted it and how the information was sourced, laying groundwork for provenance tracking
- Multiple AI agents can connect via MCP, each seeing only what their key allows
- Keys are hashed, tracked, and independently revocable
- Everything runs on Supabase's free tier with no local servers to maintain

*Based on [Open Brain by Nate B. Jones](https://natebjones.com). Original guide uses Slack for capture and a single access key. This version replaces Slack with a web form, adds per-key content filtering, and supports multiple access keys for different agent contexts.*
