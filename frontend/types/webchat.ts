import type { MessageDTO, MessageListData } from "@/types/message";

export interface WebChatSessionCreate {
  workspace_key: string;
  name: string;
  email?: string;
  phone?: string;
  language?: string;
  timezone?: string;
  landing_url?: string;
  referrer?: string;
}

export interface WebChatSessionDTO {
  conversation_id: string;
  session_token: string;
}

export interface StoredWebChatSession {
  conversationId: string;
  token: string;
}

export type WebChatMessageDTO = MessageDTO;
export type WebChatMessageListData = MessageListData;

export interface WebChatMessageCreate {
  content: string;
  client_message_id: string;
}

export type WebChatResponseType =
  | "ANSWER"
  | "ACTION_COLLECTING"
  | "ACTION_CONFIRMATION"
  | "ACTION_CREATED"
  | "ACTION_CANCELLED"
  | "AI_TOOL_CONFIRMATION"
  | "AI_TOOL_RESULT"
  | "AI_TOOL_CANCELLED"
  | "HUMAN_MODE"
  | "HUMAN_HANDOFF"
  | "NO_RESPONSE"
  | "ERROR";

export interface WebChatActionCollection {
  session_id: string;
  missing_fields: string[];
  invalid_fields: Record<string, string>;
  summary: { fields?: Array<{ key: string; label: string; value: unknown }> } | null;
  confirmation_token: string | null;
}

export interface WebChatAIToolAction {
  id: string;
  tool_name: string;
  status: string;
  result: Record<string, unknown> | null;
  confirmation_token: string | null;
  confirmation_expires_at: string | null;
}

export interface WebChatAssistantResult {
  type: WebChatResponseType;
  message: string | null;
  citations: Array<{
    label: string;
    document_id: string;
    chunk_id: string;
    document_name: string;
  }>;
  action_collection: WebChatActionCollection | null;
  action_request_id: string | null;
  ai_tool_action: WebChatAIToolAction | null;
}

export interface WebChatAIResponse {
  conversation_id: string;
  customer_message: MessageDTO;
  assistant: WebChatAssistantResult | null;
}

export interface WebChatActionDecision {
  client_message_id: string;
  confirmation_token?: string;
}

export interface WebChatAIToolDecision {
  client_message_id: string;
  confirmation_token?: string;
}
