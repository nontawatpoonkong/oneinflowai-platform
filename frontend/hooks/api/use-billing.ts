"use client";
import { useQuery } from "@tanstack/react-query";
import { billingService } from "@/services/billing/billing.service";
export function useBilling(){return {
  plans:useQuery({queryKey:["billing","plans"],queryFn:billingService.plans}),
  subscription:useQuery({queryKey:["billing","subscription"],queryFn:billingService.subscription}),
  entitlements:useQuery({queryKey:["billing","entitlements"],queryFn:billingService.entitlements}),
  usage:useQuery({queryKey:["billing","usage"],queryFn:billingService.usage}),
};}
