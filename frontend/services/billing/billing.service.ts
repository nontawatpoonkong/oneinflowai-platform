import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type { BillingPlan, BillingEntitlement, BillingUsage, WorkspaceSubscription } from "@/types/billing";

async function get<T>(path:string){return unwrap(await api.get<ApiEnvelope<T>>(path));}
export const billingService={
  plans:()=>get<BillingPlan[]>("/billing/plans"),
  subscription:()=>get<WorkspaceSubscription|null>("/billing/subscription"),
  entitlements:()=>get<BillingEntitlement[]>("/billing/entitlements"),
  usage:()=>get<BillingUsage[]>("/billing/usage"),
};
