"use client";
import { useQuery } from "@tanstack/react-query";
import { paymentService } from "@/services/payment/payment.service";
export function usePayments() { return useQuery({ queryKey: ["payments"], queryFn: paymentService.list }); }
export function usePaymentDestinations() { return useQuery({ queryKey: ["payments", "destinations"], queryFn: paymentService.destinations }); }
