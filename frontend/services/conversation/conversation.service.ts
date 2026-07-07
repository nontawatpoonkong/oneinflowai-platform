import { api, unwrap } from "@/services/api/client";
import type {
  ApiEnvelope,
  ConversationDTO,
  ListParams,
  Paginated,
} from "@/types/api";

export const conversationService = {
  async list(params: ListParams = {}): Promise<Paginated<ConversationDTO>> {
    const res = await api.get<ApiEnvelope<Paginated<ConversationDTO>>>(
      "/conversations",
      { params },
    );
    return unwrap(res);
  },
};
