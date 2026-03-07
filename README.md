This is derived from [Nate B Jones Open Brain](https://natesnewsletter.substack.com/p/every-ai-you-use-forgets-you-heres). I've made some minor improvements, but the initial work of laying it out cleanly was done by him and if this is saving you time, you should toss some resources his way.

Directories:
- `supabase` - edge functions for Supabase
- `public-site` - contents of the Supabase storage bucket named `public-site`

To update the RPC Functions (AKA stored procedures),
1. Ensure you've set `SUPABASE_DB_PASSWORD`
2. Create a new migration (e.g., for match_thoughts)
    ```bash
    supabase migration new update_match_thoughts
    ```
2. Edit the file it created
   e.g., `supabase/migrations/<timestamp>_update_match_thoughts.sql`
   Paste your updated `CREATE OR REPLACE FUNCTION` statement.
3. Deploy
    ```bash
    supabase db push
    ```
   OR
    ```bash
    deploy_all.sh
    ```
