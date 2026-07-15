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
