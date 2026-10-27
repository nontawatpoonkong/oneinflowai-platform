export type RoomOperationalStatus = "AVAILABLE" | "OCCUPIED" | "OUT_OF_SERVICE";
export type RoomReadinessStatus = "READY" | "DIRTY" | "CLEANING";
export type StayStatus = "EXPECTED" | "CHECKED_IN" | "CHECKED_OUT" | "NO_SHOW";
export interface HotelProperty { id:string; name:string; timezone:string; active:boolean; }
export interface HotelRoomType { id:string; property_id:string; name:string; code:string; active:boolean; }
export interface HotelRoom { id:string; workspace_id:string; property_id:string; property_name:string; room_type_id:string; room_type_name:string; code:string; floor:string|null; building:string|null; wing:string|null; internal_notes:string|null; active:boolean; operational_status:RoomOperationalStatus; readiness_status:RoomReadinessStatus; current_stay_id:string|null; created_at:string; updated_at:string; }
export interface StayRoom { assignment_id:string; room_id:string; code:string; room_type_id:string; operational_status:RoomOperationalStatus; readiness_status:RoomReadinessStatus; assigned_at:string; released_at:string|null; }
export interface StayEvent { id:string; event_type:string; room_id:string|null; actor_user_id:string|null; event_metadata:Record<string,unknown>; sequence:number; created_at:string; }
export interface HotelStay { id:string; workspace_id:string; booking_id:string; property_id:string; property_name:string; room_type_id:string; customer_id:string|null; guest_name:string|null; status:StayStatus; planned_check_in_date:string; planned_check_out_date:string; required_room_count:number; actual_check_in_at:string|null; actual_check_out_at:string|null; rooms:StayRoom[]; events:StayEvent[]; created_at:string; updated_at:string; }
export interface Paged<T> { items:T[]; total:number; page:number; page_size:number; total_pages:number; }
export interface RoomListParams { property_id?:string; room_type_id?:string; floor?:string; building?:string; wing?:string; operational_status?:RoomOperationalStatus; readiness_status?:RoomReadinessStatus; active?:boolean; page?:number; page_size?:number; }
export interface StayListParams { status?:StayStatus; property_id?:string; arrival_date?:string; departure_date?:string; page?:number; page_size?:number; }
