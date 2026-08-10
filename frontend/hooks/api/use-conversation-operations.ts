"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { conversationService } from "@/services/conversation/conversation.service";

export function useConversationOperations(conversationId: string | null) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["conversations"] });
  const requireId = () => {
    if (!conversationId) throw new Error("A conversation must be selected");
    return conversationId;
  };
  return {
    handoff: useMutation({ mutationFn: () => conversationService.handoff(requireId()), onSuccess: refresh }),
    assign: useMutation({ mutationFn: (userId?: string) => conversationService.assign(requireId(), userId), onSuccess: refresh }),
    returnToAi: useMutation({ mutationFn: () => conversationService.returnToAi(requireId()), onSuccess: refresh }),
    markRead: useMutation({ mutationFn: () => conversationService.markRead(requireId()), onSuccess: refresh }),
  };
}
