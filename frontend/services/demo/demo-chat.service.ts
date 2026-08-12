import { publicApi, unwrapPublic } from "@/services/api/public-client";
import type { ApiEnvelope } from "@/types/api";
import type { DemoChatMessage, DemoChatResponse } from "@/types/demo-chat";

export async function sendDemoMessage(
  message: string,
  history: DemoChatMessage[],
): Promise<DemoChatResponse> {
  const response = await publicApi.post<ApiEnvelope<DemoChatResponse>>("/demo/chat", {
    message,
    history: history.slice(-8).map(({ role, content }) => ({ role, content })),
  });
  return unwrapPublic(response);
}
