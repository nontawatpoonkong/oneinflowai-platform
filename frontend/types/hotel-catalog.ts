export type BedType = "KING" | "QUEEN" | "DOUBLE" | "TWIN" | "SINGLE" | "BUNK" | "SOFA_BED" | "FUTON" | "OTHER";
export type AmenityValueType = "BOOLEAN" | "NUMBER" | "TEXT";
export type AvailabilityColor = "GREEN" | "YELLOW" | "ORANGE" | "RED";

export interface AmenityDefinition {
  id: string; code: string; category: string; default_name_en: string;
  default_name_th: string; value_type: AmenityValueType; active: boolean; sort_order: number;
}
export interface RoomTypeBed { id?: string; bed_type: BedType; quantity: number; custom_label?: string | null; width_cm?: number | null; length_cm?: number | null; sort_order: number; }
export interface RoomTypeAmenity { id?: string; amenity_definition_id?: string; code: string; category?: string; name_en?: string; name_th?: string; value_type?: AmenityValueType; boolean_value?: boolean | null; number_value?: string | null; text_value?: string | null; }
export interface RoomTypeImage { id: string; room_type_id: string; public_url: string | null; content_url: string; mime_type: string; caption: string | null; alt_text: string; image_category: string; sort_order: number; is_cover: boolean; }
export interface RoomTypeImageOrder { image_id: string; sort_order: number; is_cover: boolean; }
export interface RichRoomType {
  id: string; workspace_id: string; property_id: string; code: string; name: string;
  short_description: string | null; description: string | null; room_size_sqm: string | null;
  max_adults: number; max_children: number; max_occupancy: number; base_capacity: number;
  smoking_policy: string; accessibility_available: boolean; public_highlights: string | null;
  view_type: string; custom_view_label: string | null; active: boolean;
}
export interface RoomCatalogDetail { room_type: RichRoomType; beds: RoomTypeBed[]; amenities: RoomTypeAmenity[]; images: RoomTypeImage[]; physical_room_count: number; }
export interface AvailabilityCell { date: string; total_units: number; reserved_units: number; blocked_units: number; available_units: number; used_units: number; occupancy_ratio: string; color_bucket: AvailabilityColor; authority: "LOCAL" | "PMS"; has_inventory: boolean; }
export interface AvailabilityRow { room_type_id: string; room_type_name: string; cells: AvailabilityCell[]; }
export interface AvailabilityCalendar { property_id: string; start_date: string; days: 7 | 14 | 30; rows: AvailabilityRow[]; }
export interface PhysicalRoomInput { code: string; floor?: string; building?: string; wing?: string; internal_notes?: string; }
export interface RichRoomTypePayload {
  property_id: string; code: string; name: string; short_description?: string; description?: string;
  room_size_sqm?: number; max_adults: number; max_children: number; max_occupancy: number;
  base_capacity: number; smoking_policy: string; accessibility_available: boolean;
  public_highlights?: string; view_type: string; custom_view_label?: string;
  active: boolean; beds: Omit<RoomTypeBed, "id">[]; amenities: RoomTypeAmenity[];
  physical_rooms: PhysicalRoomInput[];
}
