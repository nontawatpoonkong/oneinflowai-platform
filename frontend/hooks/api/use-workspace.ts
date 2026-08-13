"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/lib/query-keys";
import { workspaceService } from "@/services/workspace/workspace.service";

export function useMyWorkspace() {
  return useQuery({
    queryKey: queryKeys.workspaceMe,
    queryFn: workspaceService.me,
  });
}

export function useWorkspaces(enabled = true) {
  return useQuery({
    queryKey: ["workspaces"],
    queryFn: workspaceService.list,
    enabled,
  });
}

export function useCreateWorkspace() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: workspaceService.create,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["workspaces"] });
      await client.invalidateQueries({ queryKey: queryKeys.workspaceMe });
    },
  });
}

export function useWorkspaceAIInstructions(workspaceId?: string) {
  return useQuery({
    queryKey: ["workspace", workspaceId, "ai-instructions"],
    queryFn: () => workspaceService.aiInstructions(workspaceId!),
    enabled: Boolean(workspaceId),
  });
}

export function useUpdateWorkspaceAIInstructions(workspaceId?: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (instructions: string) =>
      workspaceService.updateAIInstructions(workspaceId!, instructions),
    onSuccess: (data) => client.setQueryData(
      ["workspace", workspaceId, "ai-instructions"], data,
    ),
  });
}

export function useWorkspaceMembers(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["workspace", workspaceId, "members"],
    queryFn: () => workspaceService.members(workspaceId!),
    enabled: Boolean(workspaceId),
  });
}
