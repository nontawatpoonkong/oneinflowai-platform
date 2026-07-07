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
