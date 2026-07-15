"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { messageService } from "@/services/message/message.service";

export function useSendMessage(conversationId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (content: string) => {
      if (!conversationId) {
        throw new Error("A conversation must be selected before sending");
      }

      return messageService.send(conversationId, {
        sender_type: "agent",
        content,
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["messages", conversationId],
      });
    },
  });
}
