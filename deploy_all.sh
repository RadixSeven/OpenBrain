#!/bin/bash
# Run this to redeploy everything to Supabase.
# You must have run `supabase login`, `supabase link`, and
# set SUPABASE_DB_PASSWORD environtment variable
# (stored in Lastpass and ~/.env) before running this.

supabase functions deploy capture-api --no-verify-jwt
supabase functions deploy open-brain-mcp --no-verify-jwt
supabase db push
