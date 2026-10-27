export type EntitlementKind = "BOOLEAN" | "LIMITED" | "UNLIMITED";
export interface BillingEntitlement { key:string; kind:EntitlementKind; enabled:boolean; limit_value:number|null; overage_allowed:boolean; }
export interface BillingPlan { id:string; key:string; display_name:string; is_active:boolean; billing_interval:"MONTH"|"YEAR"; price_minor:number|null; currency:string|null; pricing_note:string|null; entitlements:BillingEntitlement[]; }
export type SubscriptionStatus = "PENDING_ACTIVATION"|"TRIALING"|"ACTIVE"|"PAST_DUE"|"CANCELED"|"EXPIRED";
export interface WorkspaceSubscription { id:string; billing_account_id:string; workspace_id:string|null; plan:BillingPlan; status:SubscriptionStatus; billing_interval:"MONTH"|"YEAR"; current_period_start:string; current_period_end:string; trial_end:string|null; cancel_at_period_end:boolean; provider:string|null; workspace_limit:number; allocated_workspaces:number; }
export interface BillingAccount { id:string; owner_user_id:string; status:"ACTIVE"|"SUSPENDED"; subscriptions:WorkspaceSubscription[]; }
export interface BillingUsage { key:string; kind:EntitlementKind; enabled:boolean; limit:number|null; used:number|null; remaining:number|null; overage_allowed:boolean; }
