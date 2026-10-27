"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { automationService } from "@/services/automation/automation.service";
import type { AutomationCreate } from "@/types/automation";

export function useAutomations() {
  return useQuery({ queryKey: ["automations"], queryFn: automationService.list });
}

export function useAutomationExecutions() {
  return useQuery({
    queryKey: ["automations", "executions"],
    queryFn: automationService.executions,
  });
}

export function useAutomationStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["automations", "status"],
    queryFn: automationService.status,
    enabled,
    refetchInterval: 30_000,
  });
}

export function useAutomationMutations() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["automations"] });
  return {
    create: useMutation({
      mutationFn: (payload: AutomationCreate) => automationService.create(payload),
      onSuccess: refresh,
    }),
    enable: useMutation({ mutationFn: automationService.enable, onSuccess: refresh }),
    disable: useMutation({ mutationFn: automationService.disable, onSuccess: refresh }),
    retry: useMutation({
      mutationFn: automationService.retryExecution,
      onSuccess: refresh,
    }),
  };
}
