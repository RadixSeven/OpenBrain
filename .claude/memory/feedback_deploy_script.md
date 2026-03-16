---
name: Use deploy_all.sh for Supabase deployments
description: Always use deploy_all.sh (or --no-verify-jwt) when deploying edge functions — they are public endpoints
type: feedback
---

Always deploy edge functions with `--no-verify-jwt` flag. The project has `deploy_all.sh` that does this correctly. Deploying without it causes 401 errors because the endpoints are public (authenticated via x-brain-key / CAPTURE_SECRET, not Supabase JWT).

**Why:** Deployed without the flag once and broke the MCP endpoint with 401 "Missing authorization header" errors.

**How to apply:** Use `./deploy_all.sh` or explicitly pass `--no-verify-jwt` to `supabase functions deploy`.
