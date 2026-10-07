import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type { HotelProperty, HotelRoom, HotelRoomType, HotelStay, Paged, RoomListParams, StayListParams } from "@/types/stay";

export const stayService={
  async properties():Promise<HotelProperty[]>{return unwrap(await api.get<ApiEnvelope<HotelProperty[]>>("/hotel/properties"));},
  async roomTypes(propertyId?:string):Promise<HotelRoomType[]>{return unwrap(await api.get<ApiEnvelope<HotelRoomType[]>>("/hotel/room-types",{params:{property_id:propertyId}}));},
  async rooms(params:RoomListParams={}):Promise<Paged<HotelRoom>>{return unwrap(await api.get<ApiEnvelope<Paged<HotelRoom>>>("/hotel/rooms",{params}));},
  async createRoom(payload:{property_id:string;room_type_id:string;code:string;floor?:string}):Promise<HotelRoom>{return unwrap(await api.post<ApiEnvelope<HotelRoom>>("/hotel/rooms",payload));},
  async roomStatus(id:string,status:"available"|"out-of-service"):Promise<HotelRoom>{return unwrap(await api.post<ApiEnvelope<HotelRoom>>(`/hotel/rooms/${id}/${status}`));},
  async stays(params:StayListParams={}):Promise<Paged<HotelStay>>{return unwrap(await api.get<ApiEnvelope<Paged<HotelStay>>>("/hotel/stays",{params}));},
  async stay(id:string):Promise<HotelStay>{return unwrap(await api.get<ApiEnvelope<HotelStay>>(`/hotel/stays/${id}`));},
  async createStay(bookingId:string):Promise<HotelStay>{return unwrap(await api.post<ApiEnvelope<HotelStay>>(`/hotel/bookings/${bookingId}/stay`));},
  async assignRooms(stayId:string,roomIds:string[]):Promise<HotelStay>{return unwrap(await api.post<ApiEnvelope<HotelStay>>(`/hotel/stays/${stayId}/assign-room`,{room_ids:roomIds}));},
  async checkIn(stayId:string,roomIds?:string[]):Promise<HotelStay>{return unwrap(await api.post<ApiEnvelope<HotelStay>>(`/hotel/stays/${stayId}/check-in`,{room_ids:roomIds?.length?roomIds:null}));},
  async checkOut(stayId:string):Promise<HotelStay>{return unwrap(await api.post<ApiEnvelope<HotelStay>>(`/hotel/stays/${stayId}/check-out`));},
  async noShow(stayId:string):Promise<HotelStay>{return unwrap(await api.post<ApiEnvelope<HotelStay>>(`/hotel/stays/${stayId}/no-show`));},
};
