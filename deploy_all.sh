#!/bin/bash
# Run this to redeploy everything to Supabase.
# You must have run `supabase login` and `supabase link` before running this.

supabase functions deploy capture-api --no-verify-jwt
supabase storage cp public-site/capture.html \
    ss:///public-site/capture.html \
    --content-type text/html \
    --experimental
