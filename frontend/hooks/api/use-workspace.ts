"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/lib/query-keys";
import { getActiveWorkspaceId } from "@/services/workspace/active-workspace";
import { workspaceService } from "@/services/workspace/workspace.service";

export function useMyWorkspace() {
  return useQuery({
    queryKey: queryKeys.workspaces,
    queryFn: workspaceService.list,
    select: (workspaces) => {
      const activeId = getActiveWorkspaceId();
      return workspaces.find((workspace) => workspace.id === activeId) ?? workspaces[0];
    },
  });
}

export function useWorkspaces(enabled = true) {
  return useQuery({
    queryKey: queryKeys.workspaces,
    queryFn: workspaceService.list,
    enabled,
  });
}

export function useCreateWorkspace() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: workspaceService.create,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: queryKeys.workspaces });
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

export function useWorkspaceAccess(workspaceId?: string) {
  return useQuery({
    queryKey: ["workspace", workspaceId, "access"],
    queryFn: () => workspaceService.access(workspaceId!),
    enabled: Boolean(workspaceId),
    staleTime: 15_000,
  });
}

export function useMyAccessRequests() {
  return useQuery({
    queryKey: ["workspace-access", "mine"],
    queryFn: workspaceService.myAccessRequests,
  });
}

export function useWorkspaceAccessRequests(workspaceId?: string) {
  return useQuery({
    queryKey: ["workspace", workspaceId, "access-requests"],
    queryFn: () => workspaceService.accessRequests(workspaceId!),
    enabled: Boolean(workspaceId),
  });
}

export function useWorkspaceJoinSettings(workspaceId?: string) {
  return useQuery({
    queryKey: ["workspace", workspaceId, "join-settings"],
    queryFn: () => workspaceService.joinSettings(workspaceId!),
    enabled: Boolean(workspaceId),
  });
}
