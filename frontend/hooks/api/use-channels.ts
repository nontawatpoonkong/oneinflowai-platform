"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { channelService } from "@/services/channel/channel.service";

const key = ["channels"] as const;

export function useChannels() {
  return useQuery({ queryKey: key, queryFn: channelService.list });
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
