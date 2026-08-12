export type EntitlementKind = "BOOLEAN" | "LIMITED" | "UNLIMITED";
export interface BillingEntitlement { key:string; kind:EntitlementKind; enabled:boolean; limit_value:number|null; overage_allowed:boolean; }
export interface BillingPlan { id:string; key:string; display_name:string; is_active:boolean; billing_interval:"MONTH"|"YEAR"; price_minor:number|null; currency:string|null; pricing_note:string|null; entitlements:BillingEntitlement[]; }
export interface WorkspaceSubscription { id:string; workspace_id:string; plan:BillingPlan; status:"TRIALING"|"ACTIVE"|"PAST_DUE"|"CANCELED"|"EXPIRED"; billing_interval:"MONTH"|"YEAR"; current_period_start:string; current_period_end:string; trial_end:string|null; cancel_at_period_end:boolean; provider:string|null; }
export interface BillingUsage { key:string; kind:EntitlementKind; enabled:boolean; limit:number|null; used:number|null; remaining:number|null; overage_allowed:boolean; }
