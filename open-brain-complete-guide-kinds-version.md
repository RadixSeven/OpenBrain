# Open Brain — Complete Setup Guide (Privacy-First Edition)

*Based on the [Open Brain guide by Nate B. Jones](https://natebjones.com). Modified to replace Slack with a private web form, add per-key content filtering, and support multiple access keys for different agents.*

---

## What You're Building

A personal knowledge system with semantic search and an open protocol. You type a thought into a web form — it automatically gets embedded, classified, and stored in your database — you see a confirmation showing what was captured. Then an MCP server lets any AI assistant search your brain by meaning — and write to it directly.

The key privacy features in this version:

- **No Slack.** Your thoughts go directly from a password-protected web form to your database. No third-party chat platform sees them.
- **Filtered access.** Each MCP access key maps to a filter profile. You can give a work agent a key that only sees thoughts tagged "sfw," while your personal setup sees everything.
- **Multiple secrets.** Different agents get different keys, stored in your database. You can name them, track usage, and revoke them independently.
- **Works with every MCP client.** Clients that support custom headers use the `x-brain-key` header. Clients that don't (Claude Desktop, Claude Web, ChatGPT Web) pass the key as a URL query parameter instead, using dedicated keys that are easy to audit and revoke as a group.

### What You Need

About 45 minutes and zero coding experience. You'll copy and paste everything.

### Services (All Free Tier)

- **Supabase** — Your database — stores everything, hosts your server functions
- **OpenRouter** — Your AI gateway — generates embeddings and classifies your thoughts
- **GitHub** — Hosts your capture page — one static HTML file served via GitHub Pages

### If You Get Stuck

Supabase has a free built-in AI assistant in every project dashboard. Look for the chat icon in the bottom-right corner. It has access to all of Supabase's documentation and can help with every Supabase-specific step in this guide. It can walk you through where to click, fix SQL errors if you paste the error message, explain terminal commands, interpret Edge Function logs, and explain Supabase concepts in plain English.

### Cost Breakdown

| Service | Cost |
|---|---|
| Supabase (free tier) | $0 |
| GitHub Pages (free tier) | $0 |
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

GITHUB
  Account:            ____________
  Repo name:          ____________  <- Step 7b
  Pages URL:          ____________  <- Step 7b

GENERATED DURING SETUP
  Capture API URL:    ____________  <- Step 7a
  Capture Form Secret:____________  <- Step 6
  MCP Server URL:     ____________  <- Step 10
  MCP Keys:           (stored in access_keys table — Step 9)

--------------------------------------
```

> **Seriously — copy that now.** You'll thank yourself at Step 7.

---

## Two Parts

**Part 1 — Capture (Steps 1–8):** Static HTML page (GitHub Pages) → JSON API (Edge Function) → Supabase. Type a thought, it gets embedded and classified automatically, you see the result on screen.

**Part 2 — Retrieval & MCP Capture (Steps 9–12):** Hosted MCP Server → Any AI. Connect Claude, ChatGPT, or any MCP client to your brain with a URL and a key that controls what they can see. Any connected AI can also write thoughts directly — same pipeline as the web form.

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
  key text not null unique,              -- the access key (random hex string)
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
  where key = raw_key
    and active = true
  returning id, name, access_keys.filters;
end;
$$;
```

#### Create the List Function

New query → paste and Run:

```sql
-- List thoughts with optional filters, all applied server-side.
-- All filter parameters are optional; omitted filters are ignored.
create or replace function list_thoughts_filtered(
  result_count int default 10,
  filter_type text default null,
  filter_topic text default null,
  filter_person text default null,
  filter_days int default null,
  content_pattern text default null,
  visibility_filter text[] default null
)
returns table (
  id uuid,
  content text,
  metadata jsonb,
  submitted_by text,
  evidence_basis text,
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
    t.created_at
  from thoughts t
  where
    -- Visibility: thought must have at least one matching tag
    (visibility_filter is null
      or t.metadata->'visibility' ?| visibility_filter)
    -- Type filter
    and (filter_type is null
      or t.metadata->>'type' = filter_type)
    -- Topic filter: topics array contains the value
    and (filter_topic is null
      or t.metadata->'topics' ? filter_topic)
    -- Person filter: people array contains the value
    and (filter_person is null
      or t.metadata->'people' ? filter_person)
    -- Days filter
    and (filter_days is null
      or t.created_at >= now() - (filter_days || ' days')::interval)
    -- Regex filter on content (case-insensitive)
    and (content_pattern is null
      or t.content ~* content_pattern)
  order by t.created_at desc
  limit result_count;
end;
$$;
```

> This function powers the MCP server's `list_thoughts` tool, which supports filtering by type, topic, person, time range, and regex content matching. All filtering happens in Postgres — the regex uses Postgres's native `~*` (case-insensitive match) operator with the pattern bound as a parameter (not string-concatenated), so there is no injection risk.

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

**Table Editor** should show three tables: `thoughts`, `access_keys`, and `tag_rules`. The `thoughts` table should have columns: id, content, embedding, metadata, submitted_by, evidence_basis, created_at, updated_at. The `tag_rules` table should have your seeded rules (check that they look right). **Database → Functions** should show `match_thoughts`, `validate_access_key`, and `list_thoughts_filtered`.

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

### Step 7: Deploy the Capture System

> **Change from original guide:** This replaces the Slack app, the Slack bot token, the Event Subscriptions, and the `ingest-thought` Edge Function. The capture system has two pieces: a JSON API (Edge Function) and a static HTML page (GitHub Pages). They're split because Supabase's gateway rewrites the `Content-Type` header to `text/plain` for Edge Function responses that try to return HTML — so the UI must be served elsewhere. GitHub Pages serves static files with correct content types, is free, and gives you version-controlled deploys.

#### Step 7a: Deploy the Capture API (Edge Function)

This function accepts JSON, does the embedding/classification/tag-rule work, stores the thought, and returns JSON. No HTML.

##### Create the Function

```bash
supabase functions new capture-api
```

##### Write the Code

Open `supabase/functions/capture-api/index.ts` and replace its entire contents with:

```typescript
import { createClient } from "npm:@supabase/supabase-js@2.47.10";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const OPENROUTER_API_KEY = Deno.env.get("OPENROUTER_API_KEY")!;
const CAPTURE_SECRET = Deno.env.get("CAPTURE_SECRET")!;

const OPENROUTER_BASE = "https://openrouter.ai/api/v1";
const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

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
```

##### Deploy

```bash
supabase functions deploy capture-api --no-verify-jwt
```

The API endpoint is:

```
https://YOUR_PROJECT_REF.supabase.co/functions/v1/capture-api
```

Paste this into your credential tracker as the **Capture API URL**. You won't open this URL in a browser — the static page calls it.

#### Step 7b: Host the Capture Page (GitHub Pages)

The HTML form lives on GitHub Pages, which serves static files with the correct `Content-Type` headers for free.

##### Create a GitHub Repository

1. Go to [github.com](https://github.com) and sign in (or create an account)
2. Click the **+** in the top right → **New repository**
3. Name it `open-brain` (or whatever you want)
4. Set it to **Private** (your capture page has no secrets in it, but private keeps your setup out of search engines)
5. Check **Add a README file**
6. Click **Create repository**

Paste your GitHub username and repo name into the credential tracker.

##### Create the HTML File

In the repository page, click **Add file → Create new file**. Name it `index.html` and paste the following contents. **Before committing**, replace `YOUR_PROJECT_REF` on the line that sets `API_URL` with your actual project ref from the credential tracker.

```html
<!DOCTYPE html>
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
    button:disabled { background: #555; cursor: not-allowed; }
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
    .footer-row {
      margin-top: 1.5rem; text-align: right; font-size: 0.85rem;
    }
    .footer-row a { color: #666; text-decoration: none; }
    .footer-row a:hover { color: #999; }
    .hidden { display: none; }
    .spinner {
      display: inline-block; width: 1em; height: 1em;
      border: 2px solid #555; border-top-color: #4a9eff;
      border-radius: 50%; animation: spin 0.6s linear infinite;
      vertical-align: middle; margin-right: 0.4em;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="container">
    <h1>Open Brain</h1>

    <!-- Login screen -->
    <div id="loginSection">
      <div class="login-form">
        <input type="password" id="secretInput"
               placeholder="Enter capture secret" autofocus />
        <button id="unlockBtn">Unlock</button>
      </div>
    </div>

    <!-- Capture screen (hidden until authenticated) -->
    <div id="captureSection" class="hidden">
      <textarea id="thoughtInput" placeholder="Type a thought..."
                rows="4"></textarea>
      <div class="form-row">
        <label class="viz-label">Override visibility (optional):
          <input type="text" id="vizOverride"
                 placeholder="e.g. sfw, work, technical" />
        </label>
        <button id="captureBtn">Capture</button>
      </div>
      <div id="resultArea"></div>
      <div class="footer-row"><a href="#" id="lockLink">Lock</a></div>
    </div>
  </div>

  <script>
    // ---- CONFIGURATION ----
    // Replace YOUR_PROJECT_REF with your Supabase project ref.
    const API_URL =
      "https://YOUR_PROJECT_REF.supabase.co/functions/v1/capture-api";

    // ---- STATE ----
    function getSecret() { return sessionStorage.getItem("ob_secret") || ""; }
    function setSecret(s) { sessionStorage.setItem("ob_secret", s); }
    function clearSecret() { sessionStorage.removeItem("ob_secret"); }

    // ---- ELEMENTS ----
    const loginSection   = document.getElementById("loginSection");
    const captureSection = document.getElementById("captureSection");
    const secretInput    = document.getElementById("secretInput");
    const unlockBtn      = document.getElementById("unlockBtn");
    const thoughtInput   = document.getElementById("thoughtInput");
    const vizOverride    = document.getElementById("vizOverride");
    const captureBtn     = document.getElementById("captureBtn");
    const resultArea     = document.getElementById("resultArea");
    const lockLink       = document.getElementById("lockLink");

    // ---- SCREEN SWITCHING ----
    function showCapture() {
      loginSection.classList.add("hidden");
      captureSection.classList.remove("hidden");
      thoughtInput.focus();
    }
    function showLogin() {
      captureSection.classList.add("hidden");
      loginSection.classList.remove("hidden");
      secretInput.value = "";
      secretInput.focus();
    }

    // If secret is already in session, skip login
    if (getSecret()) showCapture();

    // ---- LOGIN ----
    unlockBtn.addEventListener("click", () => {
      const s = secretInput.value.trim();
      if (!s) return;
      setSecret(s);
      showCapture();
    });
    secretInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") unlockBtn.click();
    });

    // ---- LOCK ----
    lockLink.addEventListener("click", (e) => {
      e.preventDefault();
      clearSecret();
      resultArea.innerHTML = "";
      showLogin();
    });

    // ---- CAPTURE ----
    captureBtn.addEventListener("click", async () => {
      const thought = thoughtInput.value.trim();
      if (!thought) return;

      captureBtn.disabled = true;
      captureBtn.innerHTML = '<span class="spinner"></span>Capturing…';
      resultArea.innerHTML = "";

      try {
        const resp = await fetch(API_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            secret: getSecret(),
            thought: thought,
            visibility_override: vizOverride.value.trim(),
          }),
        });

        const data = await resp.json();

        if (resp.status === 401) {
          // Bad secret — force re-login
          clearSecret();
          resultArea.innerHTML = renderError("Invalid secret. Please unlock again.");
          showLogin();
          return;
        }

        if (!resp.ok || !data.success) {
          resultArea.innerHTML = renderError(data.error || "Unknown error");
          return;
        }

        // Success
        resultArea.innerHTML = renderSuccess(thought, data.metadata);
        thoughtInput.value = "";
        vizOverride.value = "";
        thoughtInput.focus();

      } catch (err) {
        resultArea.innerHTML = renderError(
          "Network error — is the Edge Function deployed? " + err.message
        );
      } finally {
        captureBtn.disabled = false;
        captureBtn.textContent = "Capture";
      }
    });

    // Ctrl/Cmd+Enter to submit
    thoughtInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) captureBtn.click();
    });

    // ---- RENDERERS ----
    function esc(s) {
      const d = document.createElement("div");
      d.textContent = s;
      return d.innerHTML;
    }

    function renderSuccess(thought, meta) {
      let html = '<div class="result success"><h3>&#10003; Captured</h3>';
      html += '<p class="thought-echo">' + esc(thought) + "</p>";
      html += '<div class="meta-grid">';
      html += metaItem("Type", meta.type);
      html += metaItem("Topics", arr(meta.topics));
      html += metaItem("Visibility", arr(meta.visibility));
      if (meta.people && meta.people.length)
        html += metaItem("People", arr(meta.people));
      if (meta.action_items && meta.action_items.length)
        html += metaItem("Action items", meta.action_items.join("; "));
      html += "</div></div>";
      return html;
    }

    function renderError(msg) {
      return '<div class="result error"><h3>&#10007; Error</h3><p>'
        + esc(msg) + "</p></div>";
    }

    function metaItem(label, value) {
      return '<div class="meta-item"><span class="label">'
        + esc(label) + '</span><span class="value">'
        + esc(value || "—") + "</span></div>";
    }

    function arr(a) {
      return Array.isArray(a) ? a.join(", ") : (a || "—");
    }
  </script>
</body>
</html>
```

Click **Commit changes** (committing directly to `main` is fine).

##### Enable GitHub Pages

1. In the repository, go to **Settings** → **Pages** (in the left sidebar under "Code and automation")
2. Under **Source**, select **Deploy from a branch**
3. Set Branch to **main** and folder to **/ (root)**
4. Click **Save**
5. Wait 1–2 minutes. GitHub will show the URL at the top of the Pages settings page

Your capture page URL will be:

```
https://YOUR_GITHUB_USERNAME.github.io/open-brain/
```

> **Private repos and GitHub Pages:** GitHub Pages works with private repos on all GitHub plans (including free) as of 2024. The published site is publicly accessible at the Pages URL even though the repo source is private — which is exactly what you want. The HTML contains no secrets; the capture secret is typed at runtime and stored only in `sessionStorage`.

Paste this URL into your credential tracker as the **Capture Page URL**. Bookmark it, add it to your phone's home screen — this is where you'll capture thoughts.

##### Updating the Form Later

To update the capture UI, just edit `index.html` in the GitHub repository (via the web UI or by pushing a commit). GitHub Pages redeploys automatically within a minute or two. No Supabase redeployment needed.

##### Using Git from the Command Line (optional)

If you prefer working locally:

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/open-brain.git
cd open-brain
# Edit index.html
git add index.html
git commit -m "Update capture form"
git push
```

> **Why GitHub Pages instead of Supabase Storage?** Supabase's Edge Function gateway overrides the `Content-Type` to `text/plain` for HTML responses, which causes browsers to show raw source code instead of rendering the page. The previous version of this guide used Supabase Storage to work around this, but GitHub Pages is simpler: you get version control for free, updates are just git commits, and there's no bucket configuration to manage. The HTML page calls the Edge Function API via `fetch()`, which handles JSON just fine.

---

### Step 8: Test Capture

1. Open your **Capture Page URL** (the GitHub Pages URL from Step 7b, NOT the API URL) in a browser
2. Enter your capture secret and click **Unlock**
3. Type a test thought:

```
Sarah mentioned she's thinking about leaving her job to start a consulting business
```

4. Click **Capture** (or press Ctrl/Cmd+Enter)
5. The button will show a spinner while processing. After a few seconds you should see a confirmation on the page:

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

## Part 2 — Retrieval & MCP Capture

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
insert into access_keys (name, key, filters) values (
  'personal-full-access',
  'PASTE-YOUR-64-CHAR-KEY-HERE',
  '{}'::jsonb
);
```

The empty `{}` filter means this key sees all thoughts with no restrictions.

**Work key (SFW content only):**

```sql
insert into access_keys (name, key, filters) values (
  'work-copilot',
  'PASTE-YOUR-OTHER-64-CHAR-KEY-HERE',
  '{"visibility": ["sfw", "work", "technical"]}'::jsonb
);
```

This key only returns thoughts whose `visibility` metadata array contains at least one of `sfw`, `work`, or `technical`.

**URL-exposed key (for clients that can't set custom headers):**

Some clients — Claude Desktop, Claude Web (claude.ai), and OpenAI's ChatGPT web interface — can't send custom HTTP headers. For these, the MCP server also accepts the key as a `?key=` URL query parameter. This is less secure than a header (URLs can appear in browser history, server logs, and referrer headers), so use a dedicated key with a name containing `-in-url-` to make URL-exposed keys easy to audit and revoke as a group:

```sql
insert into access_keys (name, key, filters) values (
  'claude-desktop-in-url-sfw',
  'PASTE-A-DIFFERENT-64-CHAR-KEY-HERE',
  '{"visibility": ["sfw", "work", "technical"]}'::jsonb
);
```

> **Security note:** Never reuse a header-based key in a URL. Generate a separate key for each URL-based agent. If a URL-based key leaks, you can revoke all of them at once:
> ```sql
> update access_keys set active = false where name like '%-in-url-%';
> ```

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

> **Change from original guide:** The original MCP server checked a single env-var key and had four tools. This version keeps all four tools — semantic search, list with filters, stats, and capture — but looks up keys in the `access_keys` table and applies per-key filters to every read query. The capture tool runs the same embedding, metadata extraction, and tag-rule pipeline as the web form, and records provenance (who captured it and how). The list tool delegates all filtering — including regex content matching — to a Postgres RPC function (`list_thoughts_filtered`) rather than doing it client-side.

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

There are two ways to pass the key: in an `x-brain-key` HTTP header (preferred) or as a `?key=` URL query parameter (for clients that can't set custom headers). Use a dedicated `-in-url-` key for the URL approach — see Step 9.

#### Claude Code

Supports custom headers natively:

```bash
claude mcp add open-brain \
  --scope user \
  --transport http open-brain \
  https://YOUR_PROJECT_REF.supabase.co/functions/v1/open-brain-mcp \
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

#### Claude Desktop

Claude Desktop only supports OAuth, no-auth, and STDIO for MCP — it can't send custom headers on remote HTTP servers. Use the URL query parameter approach with a dedicated `-in-url-` key:

Settings → Developer → Edit Config:

```json
{
  "mcpServers": {
    "open-brain": {
      "type": "streamable-http",
      "url": "https://YOUR_PROJECT_REF.supabase.co/functions/v1/open-brain-mcp?key=your-in-url-key-here"
    }
  }
}
```

Restart Claude Desktop. You should see "open-brain" appear in the MCP tools indicator (the hammer icon).

#### Claude Web (claude.ai) and OpenAI Web (ChatGPT)

These browser-based clients also can't set custom headers. Use the same URL query parameter approach with a dedicated `-in-url-` key:

```
https://YOUR_PROJECT_REF.supabase.co/functions/v1/open-brain-mcp?key=your-in-url-key-here
```

Add this as a remote MCP server in the client's settings. For Claude Web, go to Settings → Connected MCP Servers. For ChatGPT, check OpenAI's current MCP documentation for where to add remote servers.

#### Other Clients (Cursor, VS Code Copilot, Windsurf)

If the client supports custom headers, use the `x-brain-key` header approach. If not, use the `?key=` URL approach with a dedicated `-in-url-` key. Check the client's MCP documentation for where to add remote HTTP servers.

---

### Step 12: Use It

Ask your AI naturally. It picks the right tool automatically:

| Prompt | Tool Used |
|---|---|
| "What did I capture about career changes?" | Semantic search |
| "What did I capture this week?" | List (days filter) |
| "How many thoughts do I have?" | Stats |
| "Find my notes about the API redesign" | Semantic search |
| "Show me my recent ideas" | List (type filter) |
| "Who do I mention most?" | Stats |
| "Show me thoughts mentioning Sarah" | List (person filter) |
| "Find thoughts matching 'Q[1-4] revenue'" | List (regex pattern) |
| "Save this: decided to move the launch to March 15 because of the QA blockers" | Capture thought |
| "Remember that Marcus wants to move to the platform team" | Capture thought |

> The capture tool means you're not limited to the web form for input. Any MCP-connected AI can write directly to your brain — Claude Desktop, ChatGPT, Claude Code, Cursor. Wherever you're working, you can save a thought without switching apps. Captured thoughts go through the same embedding, metadata extraction, and tag-rule pipeline as the web form. The `submitted_by` field records which MCP key was used, and `evidence_basis` defaults to automatic provenance tracking but can be overridden by the AI (e.g., "summarized from meeting notes").

---

## Managing Access Keys

### See all keys and last usage

```sql
select name, key, active, created_at, last_used_at, filters
from access_keys
order by created_at;
```

### Generate and register a new key

```bash
openssl rand -hex 32
```

```sql
insert into access_keys (name, key, filters) values (
  'new-agent-name',
  'paste-the-64-char-key-here',
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

### Audit URL-exposed keys

Keys passed via URL query parameter are higher risk. If you followed the naming convention, you can see them all:

```sql
select name, active, last_used_at, filters
from access_keys
where name like '%-in-url-%'
order by last_used_at desc;
```

Revoke all URL-exposed keys at once if you suspect a leak:

```sql
update access_keys set active = false where name like '%-in-url-%';
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

### Capture Issues

**Page shows raw HTML source instead of a form**

You're probably opening the Edge Function URL directly instead of the GitHub Pages URL. The capture page lives at `https://YOUR_GITHUB_USERNAME.github.io/open-brain/`. The Edge Function URL (`/functions/v1/capture-api`) is a JSON API and should not be opened in a browser.

**Unlock does nothing / secret doesn't work**

Open your browser's developer console (F12 → Console tab). If you see a CORS error, the Edge Function is blocking the request. Check that the function is deployed with `--no-verify-jwt` and that the `CORS_HEADERS` in the function include `Access-Control-Allow-Origin: *`. Also verify your capture secret matches what's in `CAPTURE_SECRET`:

```bash
supabase secrets list
```

**Capture button spins and then shows "Network error"**

The `API_URL` in your `index.html` file has the wrong project ref. Edit the file in your GitHub repository, fix the URL, and commit. GitHub Pages will redeploy within a minute or two. You can also test the API directly with curl:

```bash
curl -X POST https://YOUR_PROJECT_REF.supabase.co/functions/v1/capture-api \
  -H "Content-Type: application/json" \
  -d '{"secret":"your-capture-secret","thought":"test thought"}'
```

You should get back JSON with `{"success":true,...}`.

**Capture returns an error about the database**

Check Edge Function logs: Supabase dashboard → Edge Functions → capture-api → Logs. Most likely the OpenRouter key is wrong or has no credits.

**Metadata extraction seems off**

That's normal — the LLM is making its best guess with limited context. The metadata is a convenience layer on top of semantic search, not the primary retrieval mechanism. The embedding handles fuzzy matching regardless. You can always override visibility tags manually on the form.

**Need to update the form UI**

Just edit `index.html` in your GitHub repository and commit. GitHub Pages redeploys automatically. No Supabase function redeployment needed.

### MCP Server Issues

**AI client says "server disconnected" or tools don't appear**

Check that your URL is exactly right — including `https://` and no trailing slash. The project ref must match your actual project. Try opening the URL in a browser with a POST request to confirm the function is deployed.

**Getting 401 errors**

The access key doesn't match any active key in the `access_keys` table. Verify that:
1. The key you're using matches what's stored in the `key` column
2. The key's `active` column is `true`
3. The key is being sent as either the `x-brain-key` header (lowercase, with the dash) or the `?key=` URL query parameter — the server checks both, header first
4. If using the URL approach, make sure the key isn't being URL-encoded incorrectly (hex strings are URL-safe, so this shouldn't happen with `openssl rand -hex 32` keys)

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

**Capture tool saves but metadata is wrong**

The metadata extraction is best-effort — the LLM is making its best guess from limited context. The embedding is what powers semantic search, and that works regardless of how the metadata gets classified. You can always override visibility manually on the web form, or adjust the system prompt in the MCP server's `extractMetadata` function to give the LLM better instructions for your content.

**List tool regex returns an error**

The `pattern` parameter uses Postgres's `~*` operator (POSIX regex, case-insensitive). Syntax is slightly different from JavaScript regex. Common gotchas: `\b` for word boundaries isn't supported (use `\y` instead), and `\d` works but `\w` may not match Unicode as expected. If in doubt, stick to simple patterns like `Q[1-4]|revenue` or `sarah.*job`.

---

## How It Works Under the Hood

When you type a thought in the form: the GitHub Pages site sends a JSON request to the capture Edge Function → the function generates an embedding (1536-dimensional vector of meaning) AND extracts metadata via LLM in parallel → deterministic tag rules are applied → everything is stored as a single row in Supabase along with the submitter identity (`user`) and evidence basis (`user typed in web form`) → the function returns JSON → the page renders a confirmation showing what was captured.

When your AI captures a thought via MCP: your AI client calls the `capture_thought` tool with the text (and optionally an `evidence_basis` describing how the information was sourced) → the MCP server runs the same pipeline as the web form — embedding and metadata extraction in parallel, then deterministic tag rules → the thought is stored with `submitted_by` set to `mcp {key-name}` and `evidence_basis` set to either the provided value or automatic provenance tracking → confirmation returned to your AI. The capturing key's visibility filter does not constrain what can be captured — it only filters reads.

When you ask your AI about it: your AI client sends the query to the MCP Edge Function → the function validates your access key and loads its filter rules → generates an embedding of your question → Supabase matches it against stored thoughts by vector similarity, filtered by the key's visibility rules → results come back ranked by meaning, not keywords, with provenance information (who submitted it and how) included.

The embedding is what makes retrieval powerful. "Sarah's thinking about leaving" and "What did I note about career changes?" match semantically even though they share zero keywords. The metadata and visibility tags are a bonus layer for structured filtering on top.

### Swapping Models Later

Because you're using OpenRouter, you can swap models by editing the model strings in the Edge Function code and redeploying. Browse available models at [openrouter.ai/models](https://openrouter.ai/models). Just make sure embedding dimensions match (1536 for the current setup).

---

## What You Just Built

A personal knowledge system where:

- Thoughts go from your browser directly to your database — no third-party chat platform involved
- The capture UI is a static HTML page served from GitHub Pages; the processing logic is a separate JSON API Edge Function
- Any MCP-connected AI can also capture thoughts directly — same embedding, classification, and tag-rule pipeline as the web form, with automatic provenance tracking
- Every thought gets semantic embeddings and automatic metadata including visibility classification
- Every thought records who submitted it and how the information was sourced, laying groundwork for provenance tracking
- Deterministic tag rules enforce privacy boundaries regardless of LLM classification
- Thoughts can be listed with structured filters (type, topic, person, time range) and regex content matching, all evaluated server-side in Postgres
- Multiple AI agents can connect via MCP, each seeing only what their key allows
- Keys are tracked and independently revocable
- Everything runs on Supabase's free tier with no local servers to maintain

*Based on [Open Brain by Nate B. Jones](https://natebjones.com). Original guide uses Slack for capture and a single access key. This version replaces Slack with a web form, adds per-key content filtering, and supports multiple access keys for different agent contexts.*
