"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { stayService } from "@/services/hotel/stay.service";
import type { RoomListParams, StayListParams } from "@/types/stay";

export function useHotelProperties() {
  return useQuery({ queryKey: ["hotel", "properties"], queryFn: stayService.properties });
}

export function useHotelRoomTypes(propertyId?: string) {
  return useQuery({
    queryKey: ["hotel", "room-types", propertyId],
    queryFn: () => stayService.roomTypes(propertyId),
  });
}

export function useHotelRooms(params: RoomListParams = {}) {
  return useQuery({
    queryKey: ["hotel", "rooms", params],
    queryFn: () => stayService.rooms(params),
  });
}

export function useHotelStays(params: StayListParams = {}) {
  return useQuery({
    queryKey: ["hotel", "stays", params],
    queryFn: () => stayService.stays(params),
  });
}

export function useHotelStay(id: string) {
  return useQuery({
    queryKey: ["hotel", "stay", id],
    queryFn: () => stayService.stay(id),
    enabled: Boolean(id),
  });
}

export function useStayMutations(stayId?: string) {
  const client = useQueryClient();
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["hotel"] });
  };
  return {
    createRoom: useMutation({ mutationFn: stayService.createRoom, onSuccess: refresh }),
    roomStatus: useMutation({
      mutationFn: ({ id, status }: { id: string; status: "available" | "out-of-service" }) =>
        stayService.roomStatus(id, status),
      onSuccess: refresh,
    }),
    createStay: useMutation({ mutationFn: stayService.createStay, onSuccess: refresh }),
    assign: useMutation({
      mutationFn: (roomIds: string[]) => stayService.assignRooms(stayId!, roomIds),
      onSuccess: refresh,
    }),
    checkIn: useMutation({
      mutationFn: (roomIds: string[]) => stayService.checkIn(stayId!, roomIds),
      onSuccess: refresh,
    }),
    checkOut: useMutation({
      mutationFn: () => stayService.checkOut(stayId!),
      onSuccess: refresh,
    }),
    noShow: useMutation({
      mutationFn: () => stayService.noShow(stayId!),
      onSuccess: refresh,
    }),
  };
}
