import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type { AmenityDefinition, AvailabilityCalendar, RichRoomType, RichRoomTypePayload, RoomCatalogDetail, RoomTypeAmenity, RoomTypeBed, RoomTypeImage, RoomTypeImageOrder } from "@/types/hotel-catalog";

export const hotelCatalogService = {
  async amenities(): Promise<AmenityDefinition[]> {
    return unwrap(await api.get<ApiEnvelope<AmenityDefinition[]>>("/hotel/catalog/amenities"));
  },
  async detail(id: string): Promise<RoomCatalogDetail> {
    return unwrap(await api.get<ApiEnvelope<RoomCatalogDetail>>(`/hotel/catalog/room-types/${id}`));
  },
  async create(payload: RichRoomTypePayload): Promise<RoomCatalogDetail> {
    return unwrap(await api.post<ApiEnvelope<RoomCatalogDetail>>("/hotel/catalog/room-types", payload));
  },
  async update(id: string, payload: Partial<RichRoomTypePayload>): Promise<RichRoomType> {
    return unwrap(await api.patch<ApiEnvelope<RichRoomType>>(`/hotel/room-types/${id}`, payload));
  },
  async beds(id: string, payload: Omit<RoomTypeBed, "id">[]): Promise<RoomTypeBed[]> {
    return unwrap(await api.put<ApiEnvelope<RoomTypeBed[]>>(`/hotel/catalog/room-types/${id}/beds`, payload));
  },
  async roomAmenities(id: string, payload: RoomTypeAmenity[]): Promise<RoomTypeAmenity[]> {
    return unwrap(await api.put<ApiEnvelope<RoomTypeAmenity[]>>(`/hotel/catalog/room-types/${id}/amenities`, payload));
  },
  async uploadImage(id: string, file: File, altText: string, isCover: boolean): Promise<RoomTypeImage> {
    const body = new FormData(); body.set("file", file); body.set("alt_text", altText); body.set("is_cover", String(isCover));
    return unwrap(await api.post<ApiEnvelope<RoomTypeImage>>(`/hotel/catalog/room-types/${id}/images`, body));
  },
  async imageBlob(image: RoomTypeImage): Promise<Blob> {
    const response = await api.get(image.content_url.replace("/api/v1", ""), { responseType: "blob" });
    return response.data as Blob;
  },
  async reorderImages(id: string, payload: RoomTypeImageOrder[]): Promise<RoomTypeImage[]> {
    return unwrap(await api.put<ApiEnvelope<RoomTypeImage[]>>(`/hotel/catalog/room-types/${id}/images/order`, payload));
  },
  async calendar(propertyId: string, startDate: string, days: 7 | 14 | 30): Promise<AvailabilityCalendar> {
    return unwrap(await api.get<ApiEnvelope<AvailabilityCalendar>>("/hotel/availability-calendar", { params: { property_id: propertyId, start_date: startDate, days } }));
  },
};
