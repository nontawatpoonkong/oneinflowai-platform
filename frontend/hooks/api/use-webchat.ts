"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { webchatService } from "@/services/webchat/webchat.service";
import type {
  StoredWebChatSession,
  WebChatActionDecision,
  WebChatMessageCreate,
  WebChatSessionCreate,
} from "@/types/webchat";

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
  const hasValidSession = Boolean(session?.conversationId && session?.token);

  return useQuery({
    queryKey: webchatMessagesKey(session),
    queryFn: () => {
      if (!session) throw new Error("WebChat session is required");
      return webchatService.listMessages(session.conversationId, session.token);
    },
    enabled: hasValidSession,
    refetchInterval: hasValidSession ? 3_000 : false,
    refetchIntervalInBackground: false,
  });
}

export function useSendWebChatMessage(session: StoredWebChatSession | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: WebChatMessageCreate) => {
      if (!session) throw new Error("WebChat session is required");
      return webchatService.sendMessage(
        session.conversationId,
        session.token,
        payload,
      );
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: webchatMessagesKey(session) }),
  });
}

export function useDecideWebChatAction(session: StoredWebChatSession | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      collectionId,
      decision,
      payload,
    }: {
      collectionId: string;
      decision: "confirm" | "cancel";
      payload: WebChatActionDecision;
    }) => {
      if (!session) throw new Error("WebChat session is required");
      return webchatService.decideAction(
        session.conversationId,
        collectionId,
        session.token,
        decision,
        payload,
      );
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: webchatMessagesKey(session) }),
  });
}
