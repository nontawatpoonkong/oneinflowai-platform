"use client";

import { useQuery } from "@tanstack/react-query";

import { messageService } from "@/services/message/message.service";
import type { MessageListParams } from "@/types/message";

export function useMessages(
  conversationId: string | null,
  params: MessageListParams = {},
) {
  const page = params.page ?? 1;
  const pageSize = params.page_size ?? 50;

  return useQuery({
    queryKey: ["messages", conversationId, page, pageSize],
    queryFn: () =>
      messageService.list(conversationId!, {
        page,
        page_size: pageSize,
      }),
    enabled: Boolean(conversationId),
  });
}
