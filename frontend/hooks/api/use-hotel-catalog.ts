"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { hotelCatalogService } from "@/services/hotel/catalog.service";
import type { RichRoomTypePayload, RoomTypeAmenity, RoomTypeBed, RoomTypeImageOrder } from "@/types/hotel-catalog";

export function useAmenityRegistry() { return useQuery({ queryKey: ["hotel", "amenities"], queryFn: hotelCatalogService.amenities }); }
export function useRoomCatalogDetail(id?: string) { return useQuery({ queryKey: ["hotel", "catalog", id], queryFn: () => hotelCatalogService.detail(id!), enabled: Boolean(id) }); }
export function useAvailabilityCalendar(propertyId: string, startDate: string, days: 7 | 14 | 30) {
  return useQuery({ queryKey: ["hotel", "availability-calendar", propertyId, startDate, days], queryFn: () => hotelCatalogService.calendar(propertyId, startDate, days), enabled: Boolean(propertyId) });
}
export function useHotelCatalogMutations() {
  const client = useQueryClient();
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["hotel"] }); };
  return {
    create: useMutation({ mutationFn: (payload: RichRoomTypePayload) => hotelCatalogService.create(payload), onSuccess: refresh }),
    update: useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Partial<RichRoomTypePayload> }) => hotelCatalogService.update(id, payload), onSuccess: refresh }),
    beds: useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Omit<RoomTypeBed, "id">[] }) => hotelCatalogService.beds(id, payload), onSuccess: refresh }),
    amenities: useMutation({ mutationFn: ({ id, payload }: { id: string; payload: RoomTypeAmenity[] }) => hotelCatalogService.roomAmenities(id, payload), onSuccess: refresh }),
    image: useMutation({ mutationFn: ({ id, file, altText, isCover }: { id: string; file: File; altText: string; isCover: boolean }) => hotelCatalogService.uploadImage(id, file, altText, isCover), onSuccess: refresh }),
    imageOrder: useMutation({ mutationFn: ({ id, payload }: { id: string; payload: RoomTypeImageOrder[] }) => hotelCatalogService.reorderImages(id, payload), onSuccess: refresh }),
  };
}
