"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { channelService } from "@/services/channel/channel.service";

const key = ["channels"] as const;

export function useChannels(enabled = true) {
  return useQuery({ queryKey: key, queryFn: channelService.list, enabled });
}

export function useChannelOperations() {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: key });
  return {
    connectWebChat: useMutation({
      mutationFn: channelService.connectWebChat,
      onSuccess: refresh,
    }),
    connectLine: useMutation({
      mutationFn: channelService.connectLine,
      onSuccess: refresh,
    }),
    connectFacebook: useMutation({
      mutationFn: channelService.connectFacebook,
      onSuccess: refresh,
    }),
    disconnect: useMutation({
      mutationFn: channelService.disconnect,
      onSuccess: refresh,
    }),
  };
}
