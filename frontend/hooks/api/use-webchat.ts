"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { webchatService } from "@/services/webchat/webchat.service";
import type { StoredWebChatSession, WebChatSessionCreate } from "@/types/webchat";

export const webchatMessagesKey = (session: StoredWebChatSession | null) => [
  "webchat-messages",
  session?.conversationId,
];

export function useCreateWebChatSession() {
  return useMutation({
    mutationFn: (payload: WebChatSessionCreate) =>
      webchatService.createSession(payload),
  });
}

export function useWebChatMessages(session: StoredWebChatSession | null) {
  return useQuery({
    queryKey: webchatMessagesKey(session),
    queryFn: () => {
      if (!session) throw new Error("WebChat session is required");
      return webchatService.listMessages(session.conversationId, session.token);
    },
    enabled: Boolean(session),
  });
}

export function useSendWebChatMessage(session: StoredWebChatSession | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (content: string) => {
      if (!session) throw new Error("WebChat session is required");
      return webchatService.sendMessage(
        session.conversationId,
        session.token,
        content,
      );
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: webchatMessagesKey(session) }),
  });
}
