import { api, unwrap } from "@/services/api/client";
import type {
  ApiEnvelope,
  ConversationAiModeDTO,
  ConversationDTO,
  ListParams,
  Paginated,
} from "@/types/api";

export interface ConversationUpdatePayload {
  ai_mode: ConversationAiModeDTO;
}

export const conversationService = {
  async list(params: ListParams = {}): Promise<Paginated<ConversationDTO>> {
    const res = await api.get<ApiEnvelope<Paginated<ConversationDTO>>>(
      "/conversations",
      { params },
    );
    return unwrap(res);
  },

  async update(
    conversationId: string,
    payload: ConversationUpdatePayload,
  ): Promise<ConversationDTO> {
    const res = await api.patch<ApiEnvelope<ConversationDTO>>(
      `/conversations/${encodeURIComponent(conversationId)}`,
      payload,
    );
    return unwrap(res);
  },
  async handoff(conversationId: string): Promise<ConversationDTO> {
    const res = await api.post<ApiEnvelope<ConversationDTO>>(
      `/conversations/${encodeURIComponent(conversationId)}/handoff`,
      { reason: "MANUAL_ADMIN" },
    );
    return unwrap(res);
  },
  async assign(
    conversationId: string,
    assignedUserId?: string,
  ): Promise<ConversationDTO> {
    const res = await api.post<ApiEnvelope<ConversationDTO>>(
      `/conversations/${encodeURIComponent(conversationId)}/assign`,
      assignedUserId ? { assigned_user_id: assignedUserId } : {},
    );
    return unwrap(res);
  },
  async returnToAi(conversationId: string): Promise<ConversationDTO> {
    const res = await api.post<ApiEnvelope<ConversationDTO>>(
      `/conversations/${encodeURIComponent(conversationId)}/return-to-ai`,
    );
    return unwrap(res);
  },
  async markRead(conversationId: string): Promise<{ unread_count: number }> {
    const res = await api.post<ApiEnvelope<{ unread_count: number }>>(
      `/conversations/${encodeURIComponent(conversationId)}/read`,
    );
    return unwrap(res);
  },
};
