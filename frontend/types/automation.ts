export type AutomationActionType = "internal.notification" | "customer.message";
export type AutomationScheduleMode =
  | "IMMEDIATE"
  | "DELAY_AFTER_EVENT"
  | "BEFORE_DATE_FIELD"
  | "AFTER_DATE_FIELD";

export interface AutomationDefinition {
  id: string;
  workspace_id: string;
  name: string;
  active: boolean;
  trigger_event_type: string;
  trigger_version: number;
  conditions: Array<{ field: string; operator: string; value: unknown }>;
  action_type: AutomationActionType;
  action_config: Record<string, unknown>;
  schedule_mode: AutomationScheduleMode;
  schedule_config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AutomationExecution {
  id: string;
  automation_id: string;
  event_id: string;
  status: "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  scheduled_for: string;
  started_at: string | null;
  completed_at: string | null;
  attempt_count: number;
  manual_retry_count: number;
  last_error_code: string | null;
  terminal_failure: boolean;
  claimed_by_worker_id: string | null;
  last_recovered_at: string | null;
  failure_history: Array<{
    error_code: string;
    attempt: number;
    occurred_at: string;
    source: string;
  }>;
  created_at: string;
  updated_at: string;
}

export interface AutomationOperationalStatus {
  worker: {
    health: "HEALTHY" | "STALE" | "NOT_RUNNING";
    worker_id: string | null;
    state: string | null;
    started_at: string | null;
    last_heartbeat_at: string | null;
    last_successful_poll_at: string | null;
    build_identifier: string | null;
  };
  queue: {
    pending: number;
    scheduled: number;
    running: number;
    succeeded: number;
    failed: number;
    terminal_failed: number;
    retry_pending: number;
    stale_running: number;
  };
  oldest_pending_age_seconds: number | null;
  next_scheduled_execution: string | null;
  recent_success_rate: number | null;
  recent_failures: AutomationExecution[];
  alerts: string[];
  timestamp: string;
}

export interface AutomationList {
  items: AutomationDefinition[];
  total: number;
  page: number;
  page_size: number;
}

export interface AutomationExecutionList {
  items: AutomationExecution[];
  total: number;
  page: number;
  page_size: number;
  counts: Record<"PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED", number>;
}

export interface AutomationCreate {
  name: string;
  active: boolean;
  trigger_event_type: string;
  trigger_version: 1;
  conditions: Array<{ field: string; operator: string; value: unknown }>;
  action_type: AutomationActionType;
  action_config: Record<string, unknown>;
  schedule_mode: AutomationScheduleMode;
  schedule_config: Record<string, unknown>;
}
