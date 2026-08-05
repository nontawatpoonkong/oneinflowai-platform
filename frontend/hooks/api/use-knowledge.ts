"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query-keys";
import { knowledgeService } from "@/services/knowledge/knowledge.service";

const params = { page: 1, page_size: 100 };

export function useKnowledgeDocuments() {
  return useQuery({ queryKey: queryKeys.knowledge(params), queryFn: () => knowledgeService.list(params) });
}

export function useUploadKnowledgeDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, onProgress }: { file: File; onProgress: (value: number) => void }) =>
      knowledgeService.upload(file, onProgress),
    onSuccess: () => client.invalidateQueries({ queryKey: ["knowledge"] }),
  });
}

export function useDeleteKnowledgeDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: knowledgeService.remove,
    onSuccess: () => client.invalidateQueries({ queryKey: ["knowledge"] }),
  });
}
