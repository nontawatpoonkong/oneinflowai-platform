"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/lib/query-keys";
import { customerService } from "@/services/customer/customer.service";
import type { ListParams } from "@/types/api";

export function useCustomers(params: ListParams = {}) {
  return useQuery({
    queryKey: queryKeys.customers(params),
    queryFn: () => customerService.list(params),
  });
}
