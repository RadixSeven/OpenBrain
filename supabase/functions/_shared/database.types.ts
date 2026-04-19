export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  graphql_public: {
    Tables: {
      [_ in never]: never
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      graphql: {
        Args: {
          extensions?: Json
          operationName?: string
          query?: string
          variables?: Json
        }
        Returns: Json
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  public: {
    Tables: {
      access_keys: {
        Row: {
          active: boolean
          created_at: string | null
          filters: Json
          id: string
          key: string
          last_used_at: string | null
          name: string
        }
        Insert: {
          active?: boolean
          created_at?: string | null
          filters?: Json
          id?: string
          key: string
          last_used_at?: string | null
          name: string
        }
        Update: {
          active?: boolean
          created_at?: string | null
          filters?: Json
          id?: string
          key?: string
          last_used_at?: string | null
          name?: string
        }
        Relationships: []
      }
      current_prompt: {
        Row: {
          id: string
          note: string | null
          prompt_template_id: string
          prompt_type: string
          starting_at: string
        }
        Insert: {
          id?: string
          note?: string | null
          prompt_template_id: string
          prompt_type: string
          starting_at?: string
        }
        Update: {
          id?: string
          note?: string | null
          prompt_template_id?: string
          prompt_type?: string
          starting_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "current_prompt_prompt_template_id_fkey"
            columns: ["prompt_template_id"]
            isOneToOne: false
            referencedRelation: "prompt_templates"
            referencedColumns: ["id"]
          },
        ]
      }
      prompt_templates: {
        Row: {
          created_at: string
          id: string
          model_string: string
          prompt_template_text: string
          prompt_type: string
        }
        Insert: {
          created_at?: string
          id?: string
          model_string: string
          prompt_template_text: string
          prompt_type: string
        }
        Update: {
          created_at?: string
          id?: string
          model_string?: string
          prompt_template_text?: string
          prompt_type?: string
        }
        Relationships: []
      }
      tag_rules: {
        Row: {
          active: boolean
          id: string
          if_present: string
          note: string | null
          remove_tag: string
        }
        Insert: {
          active?: boolean
          id?: string
          if_present: string
          note?: string | null
          remove_tag: string
        }
        Update: {
          active?: boolean
          id?: string
          if_present?: string
          note?: string | null
          remove_tag?: string
        }
        Relationships: []
      }
      thoughts: {
        Row: {
          content: string
          created_at: string | null
          embedding: string | null
          evidence_basis: string
          id: string
          metadata: Json | null
          submitted_by: string
          updated_at: string | null
          visibility_verified_by_human_at: string | null
        }
        Insert: {
          content: string
          created_at?: string | null
          embedding?: string | null
          evidence_basis?: string
          id?: string
          metadata?: Json | null
          submitted_by?: string
          updated_at?: string | null
          visibility_verified_by_human_at?: string | null
        }
        Update: {
          content?: string
          created_at?: string | null
          embedding?: string | null
          evidence_basis?: string
          id?: string
          metadata?: Json | null
          submitted_by?: string
          updated_at?: string | null
          visibility_verified_by_human_at?: string | null
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      get_current_prompt: {
        Args: { p_type: string }
        Returns: {
          model_string: string
          prompt_template_id: string
          prompt_template_text: string
        }[]
      }
      list_thoughts_filtered: {
        Args: {
          content_pattern?: string
          filter_days?: number
          filter_person?: string
          filter_topic?: string
          filter_type?: string
          result_count?: number
          visibility_filter?: string[]
        }
        Returns: {
          content: string
          created_at: string
          evidence_basis: string
          id: string
          metadata: Json
          submitted_by: string
        }[]
      }
      match_thoughts: {
        Args: {
          filter?: Json
          match_count?: number
          match_threshold?: number
          query_embedding: string
          visibility_filter?: string[]
        }
        Returns: {
          content: string
          created_at: string
          evidence_basis: string
          id: string
          metadata: Json
          similarity: number
          submitted_by: string
        }[]
      }
      validate_access_key: {
        Args: { raw_key: string }
        Returns: {
          filters: Json
          key_id: string
          key_name: string
        }[]
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  graphql_public: {
    Enums: {},
  },
  public: {
    Enums: {},
  },
} as const

// The below hash is used to detect whether the types have
// diverged from the database schemas represented by the
// migrations directory
// migrations-hash: 63210d06fba7a7ac2cb178251413f2875af19e35c33c67b11f7bded3d82b72af
