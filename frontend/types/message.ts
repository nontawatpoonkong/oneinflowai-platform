export type MessageSenderType = "customer" | "agent" | "ai" | "system";

export interface MessageDTO {
  id: string;
  conversation_id: string;
  sender_type: MessageSenderType;
  sender_id: string | null;
  content: string;
  message_type: string;
  metadata: Record<string, unknown>;
  external_message_id: string | null;
  created_at: string;
  delivery?: {
    status: "PENDING" | "SENT" | "FAILED";
    provider_message_id: string | null;
    last_error_code: string | null;
    sent_at: string | null;
  };
}

export interface MessageListData {
  items: MessageDTO[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface MessageListParams {
  page?: number;
  page_size?: number;
}
