"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { platformService } from "@/services/platform/platform.service";

export function usePlatformOverview() {
  return useQuery({
    queryKey: ["platform", "overview"],
    queryFn: platformService.overview,
  });
}

export function usePlatformPage(path: string, page: number) {
  return useQuery({
    queryKey: ["platform", path, page],
    queryFn: () => platformService.page(path, page),
  });
}

export function usePlatformSnapshot(path: string) {
  return useQuery({
    queryKey: ["platform", path],
    queryFn: () => platformService.snapshot(path),
  });
}

export function usePlatformMutation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ path, reason }: { path: string; reason: string }) =>
      platformService.mutate(path, reason),
    onSuccess: () => client.invalidateQueries({ queryKey: ["platform"] }),
  });
}
