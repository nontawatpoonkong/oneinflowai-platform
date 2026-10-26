export interface AuditActor {
  id: string | null;
  type: "USER" | "SYSTEM" | "AI" | "AUTOMATION" | "PLATFORM_ADMIN";
  name: string;
}

export interface AuditEvent {
  id: string;
  actor: AuditActor;
  action: string;
  area: string;
  resource_type: string;
  resource_id: string | null;
  route: string | null;
  request_method: string | null;
  result: "SUCCESS" | "DENIED" | "FAILED";
  correlation_id: string | null;
  safe_metadata: Record<string, unknown>;
  occurred_at: string;
}

export interface AuditEventPage {
  items: AuditEvent[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface AuditFilters {
  page: number;
  page_size: number;
  actor_user_id?: string;
  action?: string;
  area?: string;
  result?: string;
  start_at?: string;
  end_at?: string;
  search?: string;
}
