"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/lib/query-keys";
import { conversationService } from "@/services/conversation/conversation.service";
import type { ListParams } from "@/types/api";

export function useConversations(params: ListParams = {}) {
  return useQuery({
    queryKey: queryKeys.conversations(params),
    queryFn: () => conversationService.list(params),
  });
}
