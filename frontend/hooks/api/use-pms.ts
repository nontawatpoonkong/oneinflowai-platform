"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { pmsService } from "@/services/pms/pms.service";

const rootKey = ["pms"] as const;

export function usePMSData(connectionId?: string) {
  return {
    providers: useQuery({
      queryKey: [...rootKey, "providers"],
      queryFn: pmsService.providers,
    }),
    connections: useQuery({
      queryKey: [...rootKey, "connections"],
      queryFn: pmsService.connections,
    }),
    mappings: useQuery({
      queryKey: [...rootKey, "mappings", connectionId],
      queryFn: () => pmsService.mappings(connectionId),
      enabled: Boolean(connectionId),
    }),
    syncRuns: useQuery({
      queryKey: [...rootKey, "sync-runs", connectionId],
      queryFn: () => pmsService.syncRuns(connectionId),
      enabled: Boolean(connectionId),
    }),
    issues: useQuery({
      queryKey: [...rootKey, "issues", connectionId],
      queryFn: () => pmsService.issues(connectionId),
      enabled: Boolean(connectionId),
    }),
  };
}

export function usePMSOperations() {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: rootKey });
  return {
    createConnection: useMutation({
      mutationFn: pmsService.createConnection,
      onSuccess: refresh,
    }),
    updateConnection: useMutation({
      mutationFn: ({
        id,
        payload,
      }: {
        id: string;
        payload: Parameters<typeof pmsService.updateConnection>[1];
      }) => pmsService.updateConnection(id, payload),
      onSuccess: refresh,
    }),
    testConnection: useMutation({
      mutationFn: pmsService.testConnection,
      onSuccess: refresh,
    }),
    sync: useMutation({ mutationFn: pmsService.sync, onSuccess: refresh }),
    createMapping: useMutation({
      mutationFn: pmsService.createMapping,
      onSuccess: refresh,
    }),
  };
}
