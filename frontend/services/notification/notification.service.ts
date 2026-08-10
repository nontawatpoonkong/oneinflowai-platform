import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type { NotificationDTO, NotificationListDTO } from "@/types/notification";

export const notificationService = {
  async list(): Promise<NotificationListDTO> {
    return unwrap(await api.get<ApiEnvelope<NotificationListDTO>>("/notifications"));
  },
  async markRead(id: string): Promise<NotificationDTO> {
    return unwrap(
      await api.post<ApiEnvelope<NotificationDTO>>(
        `/notifications/${encodeURIComponent(id)}/read`,
      ),
    );
  },
  async markAllRead(): Promise<{ marked_read: number }> {
    return unwrap(
      await api.post<ApiEnvelope<{ marked_read: number }>>("/notifications/read-all"),
    );
  },
};
