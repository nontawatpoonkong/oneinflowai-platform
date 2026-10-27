"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { notificationService } from "@/services/notification/notification.service";

const key = ["notifications"] as const;

export function useNotifications(enabled = true) {
  return useQuery({ queryKey: key, queryFn: notificationService.list, enabled, refetchInterval: enabled ? 5_000 : false });
}

export function useNotificationActions() {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: key });
  return {
    markRead: useMutation({ mutationFn: notificationService.markRead, onSuccess: refresh }),
    markAllRead: useMutation({ mutationFn: notificationService.markAllRead, onSuccess: refresh }),
  };
}
