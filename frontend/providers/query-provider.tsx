"use client";

import {
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { ApiError } from "@/services/api/errors";

export function QueryProvider({ children }: { children: ReactNode }) {
  const t = useTranslations("toasts");

  // Keep the latest translator so the query cache always uses the active locale.
  const handleErrorRef = useRef<(error: unknown) => void>(() => {});
  handleErrorRef.current = (error: unknown) => {
    const status = error instanceof ApiError ? error.status : 0;
    if (status === 401) return; // handled by the auth flow
    const messages: Record<number, string> = {
      403: t("forbidden"),
      404: t("notFound"),
      500: t("serverError"),
      0: t("offline"),
    };
    toast.error(messages[status] ?? t("requestFailed"));
  };

  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 },
        },
        queryCache: new QueryCache({
          onError: (error) => handleErrorRef.current(error),
        }),
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
