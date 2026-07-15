"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { conversationService } from "@/services/conversation/conversation.service";
import type {
  ConversationAiModeDTO,
  ConversationDTO,
  Paginated,
} from "@/types/api";

export function useUpdateConversation(conversationId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (aiMode: ConversationAiModeDTO) => {
      if (!conversationId) {
        throw new Error("A conversation must be selected before updating");
      }

      return conversationService.update(conversationId, { ai_mode: aiMode });
    },
    onSuccess: async (updatedConversation) => {
      queryClient.setQueriesData<Paginated<ConversationDTO>>(
        { queryKey: ["conversations"] },
        (current) =>
          current
            ? {
                ...current,
                items: current.items.map((conversation) =>
                  conversation.id === updatedConversation.id
                    ? updatedConversation
                    : conversation,
                ),
              }
            : current,
      );
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
}
