import { publicApi, unwrapPublic } from "@/services/api/public-client";
import type { ApiEnvelope } from "@/types/api";
import type {
  WebChatAIResponse,
  WebChatActionDecision,
  WebChatAssistantResult,
  WebChatMessageCreate,
  WebChatMessageListData,
  WebChatSessionCreate,
  WebChatSessionDTO,
} from "@/types/webchat";

const tokenHeaders = (token: string) => ({ "X-WebChat-Token": token });

export const webchatService = {
  async createSession(payload: WebChatSessionCreate): Promise<WebChatSessionDTO> {
    const response = await publicApi.post<ApiEnvelope<WebChatSessionDTO>>(
      "/webchat/sessions",
      payload,
    );
    return unwrapPublic(response);
  },
  async listMessages(
    conversationId: string,
    token: string,
  ): Promise<WebChatMessageListData> {
    const response = await publicApi.get<ApiEnvelope<WebChatMessageListData>>(
      `/webchat/sessions/${encodeURIComponent(conversationId)}/messages`,
      { headers: tokenHeaders(token), params: { page: 1, page_size: 50 } },
    );
    return unwrapPublic(response);
  },
  async sendMessage(
    conversationId: string,
    token: string,
    payload: WebChatMessageCreate,
  ): Promise<WebChatAIResponse> {
    const response = await publicApi.post<ApiEnvelope<WebChatAIResponse>>(
      `/webchat/sessions/${encodeURIComponent(conversationId)}/messages`,
      payload,
      { headers: tokenHeaders(token) },
    );
    return unwrapPublic(response);
  },
  async decideAction(
    conversationId: string,
    collectionId: string,
    token: string,
    decision: "confirm" | "cancel",
    payload: WebChatActionDecision,
  ): Promise<WebChatAssistantResult> {
    const response = await publicApi.post<ApiEnvelope<WebChatAssistantResult>>(
      `/webchat/sessions/${encodeURIComponent(conversationId)}/action-collections/${encodeURIComponent(collectionId)}/${decision}`,
      payload,
      { headers: tokenHeaders(token) },
    );
    return unwrapPublic(response);
  },
};
