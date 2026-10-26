import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope, CustomerDTO, Paginated } from "@/types/api";
import type {
  BookingCatalogProperty,
  BookingCatalogRatePlan,
  BookingCatalogRoomType,
  BookingHoldPayload,
  BookingRecord,
  ManualQuote,
  ManualQuoteRequest,
} from "@/types/booking";

export const bookingService = {
  properties: async (): Promise<BookingCatalogProperty[]> =>
    unwrap(await api.get<ApiEnvelope<BookingCatalogProperty[]>>("/hotel/properties")),
  roomTypes: async (propertyId: string): Promise<BookingCatalogRoomType[]> =>
    unwrap(await api.get<ApiEnvelope<BookingCatalogRoomType[]>>("/hotel/room-types", { params: { property_id: propertyId } })),
  ratePlans: async (propertyId: string, roomTypeId: string): Promise<BookingCatalogRatePlan[]> =>
    unwrap(await api.get<ApiEnvelope<BookingCatalogRatePlan[]>>("/hotel/rate-plans", { params: { property_id: propertyId, room_type_id: roomTypeId } })),
  searchCustomers: async (q: string): Promise<Paginated<CustomerDTO>> =>
    unwrap(await api.get<ApiEnvelope<Paginated<CustomerDTO>>>("/customers", { params: { q, page_size: 8 } })),
  quote: async (payload: ManualQuoteRequest): Promise<ManualQuote> =>
    unwrap(await api.post<ApiEnvelope<ManualQuote>>("/hotel/bookings/manual-quote", payload)),
  hold: async (payload: BookingHoldPayload): Promise<BookingRecord> =>
    unwrap(await api.post<ApiEnvelope<BookingRecord>>("/hotel/bookings/hold", payload)),
  advanceToPayment: async (id: string): Promise<BookingRecord> =>
    unwrap(await api.post<ApiEnvelope<BookingRecord>>(`/hotel/bookings/${id}/advance-to-payment`)),
  cancel: async (id: string): Promise<BookingRecord> =>
    unwrap(await api.post<ApiEnvelope<BookingRecord>>(`/hotel/bookings/${id}/cancel`)),
};
