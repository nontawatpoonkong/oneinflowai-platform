import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type { BillingAccount, BillingPlan, BillingEntitlement, BillingUsage, WorkspaceSubscription } from "@/types/billing";

async function get<T>(path:string){return unwrap(await api.get<ApiEnvelope<T>>(path));}
export const billingService={
  plans:()=>get<BillingPlan[]>("/billing/plans"),
  account:()=>get<BillingAccount|null>("/billing/account"),
  createSubscription:async(planId:string)=>unwrap(await api.post<ApiEnvelope<WorkspaceSubscription>>("/billing/subscriptions",{plan_id:planId})),
  subscription:()=>get<WorkspaceSubscription|null>("/billing/subscription"),
  entitlements:()=>get<BillingEntitlement[]>("/billing/entitlements"),
  usage:()=>get<BillingUsage[]>("/billing/usage"),
};
