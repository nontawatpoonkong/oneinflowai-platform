"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { billingService } from "@/services/billing/billing.service";

export function useBillingOnboarding(){
  const client=useQueryClient();
  return {
    plans:useQuery({queryKey:["billing","plans"],queryFn:billingService.plans}),
    account:useQuery({queryKey:["billing","account"],queryFn:billingService.account}),
    createSubscription:useMutation({
      mutationFn:billingService.createSubscription,
      onSuccess:async()=>{
        await client.invalidateQueries({queryKey:["billing","account"]});
        await client.invalidateQueries({queryKey:["billing","subscription"]});
      },
    }),
  };
}

// Payments shows only the slip-verification quota; payment readers without
// workspace.billing.read receive just that entry from /billing/usage.
export function useBillingUsage(){return useQuery({queryKey:["billing","usage"],queryFn:billingService.usage});}

export function useBilling(){return {
  plans:useQuery({queryKey:["billing","plans"],queryFn:billingService.plans}),
  subscription:useQuery({queryKey:["billing","subscription"],queryFn:billingService.subscription}),
  entitlements:useQuery({queryKey:["billing","entitlements"],queryFn:billingService.entitlements}),
  usage:useQuery({queryKey:["billing","usage"],queryFn:billingService.usage}),
};}
