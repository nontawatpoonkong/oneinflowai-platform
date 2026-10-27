export type PMSSyncMode = "READ_ONLY_IMPORT";
export type PMSInventoryAuthority = "LOCAL" | "PMS";
export type PMSConnectionStatus =
  | "PENDING"
  | "CONNECTED"
  | "ERROR"
  | "DISCONNECTED";
export type PMSEntityType =
  | "PROPERTY"
  | "ROOM_TYPE"
  | "ROOM"
  | "RATE_PLAN"
  | "RESERVATION";
export type PMSSyncRunStatus =
  | "PENDING"
  | "RUNNING"
  | "SUCCEEDED"
  | "PARTIAL"
  | "FAILED";
export type PMSIssueStatus = "OPEN" | "RESOLVED";

export interface PMSProviderCapabilities {
  properties: boolean;
  room_types: boolean;
  physical_rooms: boolean;
  rate_plans: boolean;
  inventory: boolean;
  reservations: boolean;
  incremental_sync: boolean;
  pagination: boolean;
}

export interface PMSProviderSummary {
  name: string;
  capabilities: PMSProviderCapabilities;
}

export interface PMSConnection {
  id: string;
  workspace_id: string;
  provider: string;
  name: string;
  active: boolean;
  status: PMSConnectionStatus;
  external_account_id: string | null;
  sync_mode: PMSSyncMode;
  inventory_authority: PMSInventoryAuthority;
  last_successful_sync_at: string | null;
  last_failed_sync_at: string | null;
  last_error_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface PMSConnectionCreate {
  provider: string;
  name: string;
  credentials: Record<string, string>;
  external_account_id?: string;
  sync_mode: PMSSyncMode;
  inventory_authority: PMSInventoryAuthority;
}

export interface PMSMapping {
  id: string;
  workspace_id: string;
  connection_id: string;
  entity_type: PMSEntityType;
  external_id: string;
  local_entity_id: string;
  external_version: string | null;
  external_updated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PMSMappingCreate {
  connection_id: string;
  entity_type: Exclude<PMSEntityType, "RESERVATION">;
  external_id: string;
  local_entity_id: string;
}

export interface PMSSyncRun {
  id: string;
  workspace_id: string;
  connection_id: string;
  status: PMSSyncRunStatus;
  started_at: string | null;
  completed_at: string | null;
  cursor_before: Record<string, unknown>;
  cursor_after: Record<string, unknown> | null;
  entities_fetched: number;
  entities_applied: number;
  conflict_count: number;
  warning_count: number;
  error_code: string | null;
  initiated_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PMSReconciliationIssue {
  id: string;
  workspace_id: string;
  connection_id: string;
  sync_run_id: string;
  entity_type: PMSEntityType;
  external_id: string;
  local_entity_id: string | null;
  issue_type: string;
  severity: string;
  status: PMSIssueStatus;
  details: Record<string, unknown>;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}
