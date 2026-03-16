-- Prompt templates: stores every prompt version with its target model
CREATE TABLE prompt_templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  prompt_type text NOT NULL,
  model_string text NOT NULL,
  prompt_template_text text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE prompt_templates IS 'Stores all prompt template versions, each paired with the model it was designed/optimized for';
COMMENT ON COLUMN prompt_templates.prompt_type IS 'Type of prompt: categorization, relevance, etc.';
COMMENT ON COLUMN prompt_templates.model_string IS 'OpenRouter model identifier this prompt was tuned for';
COMMENT ON COLUMN prompt_templates.prompt_template_text IS 'The full system prompt text sent to the LLM';
COMMENT ON COLUMN prompt_templates.created_at IS 'When this template was created';

-- Current prompt: append-only log of which template is active per type
CREATE TABLE current_prompt (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  prompt_type text NOT NULL,
  prompt_template_id uuid NOT NULL REFERENCES prompt_templates(id),
  starting_at timestamptz NOT NULL DEFAULT now(),
  note text
);

CREATE INDEX idx_current_prompt_type_start ON current_prompt(prompt_type, starting_at DESC);

COMMENT ON TABLE current_prompt IS 'Append-only history of which prompt template is active for each prompt type. Query latest starting_at per prompt_type to get current.';
COMMENT ON COLUMN current_prompt.prompt_type IS 'Type of prompt this entry activates (e.g. categorization, relevance). Must match a prompt_templates.prompt_type value.';
COMMENT ON COLUMN current_prompt.prompt_template_id IS 'References the prompt_templates row to use for this prompt type';
COMMENT ON COLUMN current_prompt.starting_at IS 'When this prompt template became active. The row with the latest starting_at per prompt_type is the current one.';
COMMENT ON COLUMN current_prompt.note IS 'Optional explanation of why this prompt was activated (e.g. dspy optimized run #3, rollback to previous)';

-- RLS: service_role only
ALTER TABLE prompt_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE current_prompt ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON prompt_templates FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON current_prompt FOR ALL USING (true) WITH CHECK (true);

-- Database function to get the current prompt for a given type
CREATE OR REPLACE FUNCTION get_current_prompt(p_type text)
RETURNS TABLE(prompt_template_text text, model_string text, prompt_template_id uuid) AS $$
  SELECT pt.prompt_template_text, pt.model_string, pt.id
  FROM current_prompt cp
  JOIN prompt_templates pt ON pt.id = cp.prompt_template_id
  WHERE cp.prompt_type = p_type
  ORDER BY cp.starting_at DESC
  LIMIT 1;
$$ LANGUAGE sql SECURITY DEFINER;

-- Seed: insert the current hardcoded categorization prompt
INSERT INTO prompt_templates (id, prompt_type, model_string, prompt_template_text)
VALUES (
  'a0a0a0a0-b1b1-c2c2-d3d3-e4e4e4e4e4e4',
  'categorization',
  'openai/gpt-5.2',
  E'Extract metadata from the user''s captured thought. Return JSON with:\n- "people": array of people mentioned (empty if none)\n- "action_items": array of implied to-dos (empty if none)\n- "dates_mentioned": array of dates YYYY-MM-DD (empty if none)\n- "topics": array of 1-3 short topic tags (always at least one)\n- "type": one of "observation", "task", "idea", "reference", "person_note"\n- "visibility": array of applicable labels from: "sfw", "personal", "work",\n  "technical", "health", "financial", "romantic_or_sexual_relationship", "religion",\n  "family_relationship", "other_relationship", "lgbtq_identity", "activism"\n  A thought can have multiple labels. "sfw" means safe for a work context with no private/sensitive content.\n  The user has two names: Eric David Moyer and Kind Loving Truth. Anything mentioning the name Kind Loving Truth\n  (or just Kind or Kind Truth) is private and not safe for work (should not have the "sfw" label).\n  Anything related the user''s LGBTQIA+ identity is private and not safe for work.\n  Default to ["sfw"] if the thought is clearly innocuous.\n  Thoughts labels should include "sfw" unless they contain genuinely private content.\nOnly extract what''s explicitly there.'
);

INSERT INTO current_prompt (prompt_type, prompt_template_id, note)
VALUES ('categorization', 'a0a0a0a0-b1b1-c2c2-d3d3-e4e4e4e4e4e4', 'Initial seed from hardcoded prompt');
