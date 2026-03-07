


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "hypopg" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "index_advisor" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "vector" WITH SCHEMA "extensions";






CREATE OR REPLACE FUNCTION "public"."list_thoughts_filtered"("result_count" integer DEFAULT 10, "filter_type" "text" DEFAULT NULL::"text", "filter_topic" "text" DEFAULT NULL::"text", "filter_person" "text" DEFAULT NULL::"text", "filter_days" integer DEFAULT NULL::integer, "content_pattern" "text" DEFAULT NULL::"text", "visibility_filter" "text"[] DEFAULT NULL::"text"[]) RETURNS TABLE("id" "uuid", "content" "text", "metadata" "jsonb", "submitted_by" "text", "evidence_basis" "text", "created_at" timestamp with time zone)
    LANGUAGE "plpgsql"
    AS $$
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


ALTER FUNCTION "public"."list_thoughts_filtered"("result_count" integer, "filter_type" "text", "filter_topic" "text", "filter_person" "text", "filter_days" integer, "content_pattern" "text", "visibility_filter" "text"[]) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_thoughts"("query_embedding" "extensions"."vector", "match_threshold" double precision DEFAULT 0.7, "match_count" integer DEFAULT 10, "filter" "jsonb" DEFAULT '{}'::"jsonb", "visibility_filter" "text"[] DEFAULT NULL::"text"[]) RETURNS TABLE("id" "uuid", "content" "text", "metadata" "jsonb", "submitted_by" "text", "evidence_basis" "text", "similarity" double precision, "created_at" timestamp with time zone)
    LANGUAGE "plpgsql"
    AS $$
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


ALTER FUNCTION "public"."match_thoughts"("query_embedding" "extensions"."vector", "match_threshold" double precision, "match_count" integer, "filter" "jsonb", "visibility_filter" "text"[]) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."rls_auto_enable"() RETURNS "event_trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'pg_catalog'
    AS $$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table','partitioned table')
  LOOP
     IF cmd.schema_name IS NOT NULL AND cmd.schema_name IN ('public') AND cmd.schema_name NOT IN ('pg_catalog','information_schema') AND cmd.schema_name NOT LIKE 'pg_toast%' AND cmd.schema_name NOT LIKE 'pg_temp%' THEN
      BEGIN
        EXECUTE format('alter table if exists %s enable row level security', cmd.object_identity);
        RAISE LOG 'rls_auto_enable: enabled RLS on %', cmd.object_identity;
      EXCEPTION
        WHEN OTHERS THEN
          RAISE LOG 'rls_auto_enable: failed to enable RLS on %', cmd.object_identity;
      END;
     ELSE
        RAISE LOG 'rls_auto_enable: skip % (either system schema or not in enforced list: %.)', cmd.object_identity, cmd.schema_name;
     END IF;
  END LOOP;
END;
$$;


ALTER FUNCTION "public"."rls_auto_enable"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."validate_access_key"("raw_key" "text") RETURNS TABLE("key_id" "uuid", "key_name" "text", "filters" "jsonb")
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
begin
  return query
  update access_keys
  set last_used_at = now()
  where key = raw_key
    and active = true
  returning id, name, access_keys.filters;
end;
$$;


ALTER FUNCTION "public"."validate_access_key"("raw_key" "text") OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."access_keys" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "name" "text" NOT NULL,
    "key" "text" NOT NULL,
    "filters" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "last_used_at" timestamp with time zone
);


ALTER TABLE "public"."access_keys" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."tag_rules" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "if_present" "text" NOT NULL,
    "remove_tag" "text" NOT NULL,
    "note" "text",
    "active" boolean DEFAULT true NOT NULL
);


ALTER TABLE "public"."tag_rules" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."thoughts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "content" "text" NOT NULL,
    "embedding" "extensions"."vector"(1536),
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "submitted_by" "text" DEFAULT 'user'::"text" NOT NULL,
    "evidence_basis" "text" DEFAULT 'user typed in web form'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."thoughts" OWNER TO "postgres";


ALTER TABLE ONLY "public"."access_keys"
    ADD CONSTRAINT "access_keys_key_key" UNIQUE ("key");



ALTER TABLE ONLY "public"."access_keys"
    ADD CONSTRAINT "access_keys_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."tag_rules"
    ADD CONSTRAINT "tag_rules_if_present_remove_tag_key" UNIQUE ("if_present", "remove_tag");



ALTER TABLE ONLY "public"."tag_rules"
    ADD CONSTRAINT "tag_rules_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."thoughts"
    ADD CONSTRAINT "thoughts_pkey" PRIMARY KEY ("id");



CREATE POLICY "Service role full access" ON "public"."thoughts" USING (("auth"."role"() = 'service_role'::"text"));



CREATE POLICY "Service role full access on access_keys" ON "public"."access_keys" USING (("auth"."role"() = 'service_role'::"text"));



CREATE POLICY "Service role full access on tag_rules" ON "public"."tag_rules" USING (("auth"."role"() = 'service_role'::"text"));



ALTER TABLE "public"."access_keys" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."tag_rules" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."thoughts" ENABLE ROW LEVEL SECURITY;




ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";



















































































































































































































































































































































































































































































































































GRANT ALL ON FUNCTION "public"."list_thoughts_filtered"("result_count" integer, "filter_type" "text", "filter_topic" "text", "filter_person" "text", "filter_days" integer, "content_pattern" "text", "visibility_filter" "text"[]) TO "anon";
GRANT ALL ON FUNCTION "public"."list_thoughts_filtered"("result_count" integer, "filter_type" "text", "filter_topic" "text", "filter_person" "text", "filter_days" integer, "content_pattern" "text", "visibility_filter" "text"[]) TO "authenticated";
GRANT ALL ON FUNCTION "public"."list_thoughts_filtered"("result_count" integer, "filter_type" "text", "filter_topic" "text", "filter_person" "text", "filter_days" integer, "content_pattern" "text", "visibility_filter" "text"[]) TO "service_role";






GRANT ALL ON FUNCTION "public"."rls_auto_enable"() TO "anon";
GRANT ALL ON FUNCTION "public"."rls_auto_enable"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."rls_auto_enable"() TO "service_role";



GRANT ALL ON FUNCTION "public"."validate_access_key"("raw_key" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."validate_access_key"("raw_key" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."validate_access_key"("raw_key" "text") TO "service_role";




































GRANT ALL ON TABLE "public"."access_keys" TO "anon";
GRANT ALL ON TABLE "public"."access_keys" TO "authenticated";
GRANT ALL ON TABLE "public"."access_keys" TO "service_role";



GRANT ALL ON TABLE "public"."tag_rules" TO "anon";
GRANT ALL ON TABLE "public"."tag_rules" TO "authenticated";
GRANT ALL ON TABLE "public"."tag_rules" TO "service_role";



GRANT ALL ON TABLE "public"."thoughts" TO "anon";
GRANT ALL ON TABLE "public"."thoughts" TO "authenticated";
GRANT ALL ON TABLE "public"."thoughts" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";



































drop extension if exists "pg_net";


