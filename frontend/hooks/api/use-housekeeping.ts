"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { housekeepingService } from "@/services/hotel/housekeeping.service";
import type { HousekeepingTaskParams } from "@/types/housekeeping";

export function useHousekeepingTasks(params: HousekeepingTaskParams = {}) {
  return useQuery({
    queryKey: ["hotel", "housekeeping", params],
    queryFn: () => housekeepingService.tasks(params),
  });
}

export function useHousekeepingMutations() {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: ["hotel"] });
  return {
    assign: useMutation({
      mutationFn: ({ id, userId }: { id: string; userId: string }) =>
        housekeepingService.assign(id, userId),
      onSuccess: refresh,
    }),
    start: useMutation({
      mutationFn: housekeepingService.start,
      onSuccess: refresh,
    }),
    complete: useMutation({
      mutationFn: housekeepingService.complete,
      onSuccess: refresh,
    }),
    cancel: useMutation({
      mutationFn: housekeepingService.cancel,
      onSuccess: refresh,
    }),
    overrideReadiness: useMutation({
      mutationFn: ({
        id,
        status,
        reason,
      }: {
        id: string;
        status: "READY" | "DIRTY";
        reason: string;
      }) => housekeepingService.overrideReadiness(id, status, reason),
      onSuccess: refresh,
    }),
  };
}
