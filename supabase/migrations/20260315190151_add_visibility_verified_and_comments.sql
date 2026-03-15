-- Add new column
ALTER TABLE "public"."thoughts"
  ADD COLUMN "visibility_verified_by_human_at" timestamp with time zone DEFAULT NULL;

-- Column comments
COMMENT ON COLUMN "public"."thoughts"."id" IS 'Unique identifier for the thought (auto-generated UUID)';
COMMENT ON COLUMN "public"."thoughts"."content" IS 'The raw text content of the thought as entered by the user or agent';
COMMENT ON COLUMN "public"."thoughts"."embedding" IS 'Vector embedding (1536-dim) of the content, used for semantic similarity search';
COMMENT ON COLUMN "public"."thoughts"."metadata" IS 'LLM-extracted structured metadata: type, topics, people, action_items, dates_mentioned, visibility, source';
COMMENT ON COLUMN "public"."thoughts"."submitted_by" IS 'Who submitted the thought (e.g. user, agent name)';
COMMENT ON COLUMN "public"."thoughts"."evidence_basis" IS 'How this thought was captured (e.g. user typed in web form, dictated via MCP)';
COMMENT ON COLUMN "public"."thoughts"."created_at" IS 'Timestamp when the thought was first created';
COMMENT ON COLUMN "public"."thoughts"."updated_at" IS 'Timestamp when the thought was last modified';
COMMENT ON COLUMN "public"."thoughts"."visibility_verified_by_human_at" IS 'Timestamp when a human most recently verified the LLM-assigned visibility labels. NULL means unverified';
