export type ActionStatus = "WAITING" | "ASSIGNED" | "IN_PROGRESS" | "COMPLETED" | "FAILED" | "CANCELLED";
export type ActionPriority = "LOW" | "NORMAL" | "HIGH" | "URGENT";

export type ActionFieldType = "string" | "integer" | "number" | "boolean" | "enum";
export interface ActionFieldDefinition { key: string; label: string; type: ActionFieldType; required: boolean; values?: Array<string | number> | null }
export interface ActionDefinitionDTO {
  id: string; workspace_id: string; name: string; key: string; description: string | null;
  execution_mode: "MANUAL" | "AUTOMATED"; is_active: boolean;
  required_fields: ActionFieldDefinition[]; optional_fields: ActionFieldDefinition[];
  created_at: string; updated_at: string;
}
export interface ActionDefinitionInput {
  key: string; name: string; description?: string | null; execution_mode: "MANUAL";
  required_fields: ActionFieldDefinition[]; optional_fields: ActionFieldDefinition[]; is_active: boolean;
}
export type ActionDefinitionUpdate = Omit<ActionDefinitionInput, "key">;
export interface ActionDTO {
  id: string; action_definition_id: string; conversation_id: string | null;
  customer_id: string | null; status: ActionStatus; priority: ActionPriority;
  payload: Record<string, unknown>; assigned_to_user_id: string | null;
  assigned_at: string | null; started_at: string | null; completed_at: string | null;
  cancelled_at: string | null; created_at: string; updated_at: string;
}
