import { publicApi, unwrapPublic } from "@/services/api/public-client";
import type { ApiEnvelope } from "@/types/api";
import type {
  DemoChatMessage,
  DemoChatResponse,
  DemoLanguage,
} from "@/types/demo-chat";

export async function sendDemoMessage(
  message: string,
  history: DemoChatMessage[],
  preferredLanguage: DemoLanguage | null,
): Promise<DemoChatResponse> {
  const response = await publicApi.post<ApiEnvelope<DemoChatResponse>>("/demo/chat", {
    message,
    history: history.slice(-8).map(({ role, content }) => ({ role, content })),
    preferred_language: preferredLanguage,
  });
  return unwrapPublic(response);
}
