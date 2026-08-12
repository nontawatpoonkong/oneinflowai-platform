"use client";
import { useQuery } from "@tanstack/react-query";
import { paymentService } from "@/services/payment/payment.service";
export function usePayments() { return useQuery({ queryKey: ["payments"], queryFn: paymentService.list }); }
export function usePaymentDestinations() { return useQuery({ queryKey: ["payments", "destinations"], queryFn: paymentService.destinations }); }
export function usePaymentEvidence(paymentId:string|null) { return useQuery({ queryKey: ["payments", paymentId, "evidence"], queryFn:()=>paymentService.evidence(paymentId!), enabled:Boolean(paymentId), retry:false }); }
export function usePaymentVerifications(paymentId:string|null) { return useQuery({ queryKey: ["payments", paymentId, "verifications"], queryFn:()=>paymentService.verifications(paymentId!), enabled:Boolean(paymentId) }); }
