import { api, unwrap } from "@/services/api/client";
import type { AuditEvent, AuditEventPage, AuditFilters } from "@/types/audit";
import type { ApiEnvelope } from "@/types/api";

export const auditService = {
  async list(filters: AuditFilters): Promise<AuditEventPage> {
    return unwrap(
      await api.get<ApiEnvelope<AuditEventPage>>("/audit/events", {
        params: filters,
      }),
    );
  },
  async detail(id: string): Promise<AuditEvent> {
    return unwrap(await api.get<ApiEnvelope<AuditEvent>>(`/audit/events/${id}`));
  },
};
