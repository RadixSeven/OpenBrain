## Database Migrations

**Migrations in `supabase/migrations/` are append-only. NEVER edit an existing
file.** To change the schema, always create a new migration with
`supabase migration new <name>`. If a previous migration was wrong, write a new
migration that fixes it. This rule is absolute.

Why this rule is absolute:
- Supabase tracks applied migrations by timestamp in
  `supabase_migrations.schema_migrations`. Editing an already-applied file
  makes local and remote silently diverge — the tracking table still says
  "applied" so `supabase db push` is a no-op.
- Reconciling that divergence requires destructive commands. `supabase
  migration repair` + `supabase db push` re-runs the edited migration against
  the live database, and `supabase db reset --linked` drops the remote
  schema entirely. Either path WIPES PRODUCTION DATA — the entire Open Brain
  dataset — if a migration has been edited to contain destructive SQL.
- `supabase db reset` (local) is also destructive: it drops and recreates the
  local database from migrations.

After adding a new migration, run `./check.sh`. It detects the schema change
(via a hash of the migrations directory stored on the last line of
`supabase/functions/_shared/database.types.ts`) and invokes
`./regen-db-types.sh`, which runs `supabase migration up` against the local
DB (non-destructive — only applies pending migrations, preserves data) and
regenerates the shared TypeScript types. Commit the regenerated file.

`./regen-db-types.sh` can also be run standalone.
