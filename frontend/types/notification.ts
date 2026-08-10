export type NotificationEntityType = "CONVERSATION" | "ACTION" | "PAYMENT";

export interface NotificationDTO {
  id: string;
  type: string;
  title: string;
  body: string;
  entity_type: NotificationEntityType;
  entity_id: string;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListDTO {
  items: NotificationDTO[];
  unread_count: number;
}
