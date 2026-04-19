#!/bin/bash
set -euo pipefail
shopt -s nullglob

# Ensure that directories and workspaces are in sync
diff \
  <(jq -r '.workspace[] + "/index.ts"' deno.json | sort) \
  <(printf './%s\n' supabase/functions/*/index.ts | sort) \
  || { echo "ERROR: workspace and functions directories out of sync" >&2; exit 1; }

# Ensure generated database types match current migrations.
# The last line of database.types.ts stores a hash of all migration files;
# if it doesn't match, invoke regen-db-types.sh to rebuild the file.
TYPES_FILE="supabase/functions/_shared/database.types.ts"
expected_hash=$(sha256sum supabase/migrations/*.sql | sha256sum | cut -d' ' -f1)
stored_hash=$(tail -n1 "$TYPES_FILE" | sed -n 's|^// migrations-hash: \([a-f0-9]\{64\}\)$|\1|p')
if [ "$expected_hash" != "$stored_hash" ]; then
    echo "Migrations changed since types were last generated." >&2
    if ! ./regen-db-types.sh; then
        echo "" >&2
        echo "Auto-regeneration failed. Fix the environment (e.g. start docker, 'supabase start') and rerun check.sh, or invoke ./regen-db-types.sh directly once ready." >&2
        exit 1
    fi
fi

# Type check all the index files (and dependencies)
rm -f deno.lock # Regenerate lock file when type checking happens
for f in supabase/functions/*/index.ts; do
    deno check "$f"
done
