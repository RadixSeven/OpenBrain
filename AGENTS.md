This is the root AGENTS.md for this repo. Don't look for an AGENTS.md
or CLAUDE.md in any parent directory. There are other AGENTS.md files
in subdirectories with information specific to operations on that
section of the code.

You are not done with a change until all tests pass and all pre-commit checks pass on the modified files.

Run `git add file1 file2 && XDG_CACHE_HOME="$(git rev-parse --show-toplevel)/.cache/" pre-commit` in order to run pre-commit.

## Database migrations

**Migrations in `supabase/migrations/` are append-only. NEVER edit an existing
file.** To change the schema, always create a new migration with
`supabase migration new <name>`. If a previous migration was wrong, write a new
migration that fixes it. This rule is absolute. See `supabase/AGENTS.md`.

After adding a new migration, run `./check.sh`; it updates the schema
definitions in `supabase/functions/_shared/database.types.ts` and
non-destructively applies the new migrations to the local DB. Commit the regenerated file.
