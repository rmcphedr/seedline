export type AssistantMessage = { id: string; role: "assistant" | "user"; content: string; target_field: string | null; created_at: string };
export type AssistantSuggestion = { id: string; field: string; resource: string; value: unknown; base_value: unknown;
  confidence: "high" | "medium" | "low"; source_text: string; status: "pending" | "accepted" | "rejected" };
export type AssistantConversation = { id: string; mode: "mock" | "live"; opportunity_id: string | null;
  opportunity_title: string | null; messages: AssistantMessage[]; suggestions: AssistantSuggestion[];
  provenance: Record<string, string>; completion_percent: number };
