import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type {
  MessageDTO,
  MessageListData,
  MessageListParams,
} from "@/types/message";

export interface SendMessagePayload {
  sender_type: "agent";
  content: string;
}

export const messageService = {
  async list(
    conversationId: string,
    params: MessageListParams = {},
  ): Promise<MessageListData> {
    const response = await api.get<ApiEnvelope<MessageListData>>(
      `/conversations/${encodeURIComponent(conversationId)}/messages`,
      { params },
    );
    return unwrap(response);
  },

  async send(
    conversationId: string,
    payload: SendMessagePayload,
  ): Promise<MessageDTO> {
    const response = await api.post<ApiEnvelope<MessageDTO>>(
      `/conversations/${encodeURIComponent(conversationId)}/messages`,
      payload,
    );
    return unwrap(response);
  },
};
