#!/bin/bash
# Regenerate supabase/functions/_shared/database.types.ts from the current
# local Supabase schema, then append a migrations-hash marker as the last line.
# check.sh uses that marker to decide whether regeneration is needed.
set -euo pipefail

TYPES_FILE="supabase/functions/_shared/database.types.ts"
expected_hash=$(sha256sum supabase/migrations/*.sql | sha256sum | cut -d' ' -f1)

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

echo "Regenerating $TYPES_FILE..." >&2
# Apply any pending migrations to the running local DB without wiping data.
# See supabase/AGENTS.md on why migrations are append-only.
supabase migration up
supabase gen types typescript --local > "$tmp"
cat <<EOF >> "$tmp"
// The below hash is used to detect whether the types have
// diverged from the database schemas represented by the
// migrations directory
// migrations-hash: $expected_hash
EOF
mv "$tmp" "$TYPES_FILE"
echo "Done. Commit $TYPES_FILE." >&2
