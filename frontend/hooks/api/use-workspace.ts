"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/lib/query-keys";
import { workspaceService } from "@/services/workspace/workspace.service";

export function useMyWorkspace() {
  return useQuery({
    queryKey: queryKeys.workspaceMe,
    queryFn: workspaceService.me,
  });
}

export function useWorkspaceMembers(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["workspace", workspaceId, "members"],
    queryFn: () => workspaceService.members(workspaceId!),
    enabled: Boolean(workspaceId),
  });
}
