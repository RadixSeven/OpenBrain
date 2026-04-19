#!/bin/bash
set -euo pipefail
shopt -s nullglob

# Ensure that directories and workspaces are in sync
diff \
  <(jq -r '.workspace[] + "/index.ts"' deno.json | sort) \
  <(printf './%s\n' supabase/functions/*/index.ts | sort) \
  || { echo "ERROR: workspace and functions directories out of sync" >&2; exit 1; }

# Type check all the index files (and dependencies)
rm -f deno.lock # Regenerate lock file when type checking happens
for f in supabase/functions/*/index.ts; do
    deno check "$f"
done
