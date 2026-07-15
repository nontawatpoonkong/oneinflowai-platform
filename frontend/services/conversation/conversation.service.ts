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
};
