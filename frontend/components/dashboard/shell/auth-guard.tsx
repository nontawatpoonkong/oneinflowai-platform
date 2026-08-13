"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/use-auth";
import { useWorkspaces } from "@/hooks/api/use-workspace";

/**
 * Client-side guard. Middleware already blocks guests without a token cookie;
 * this additionally validates the token via /auth/me and redirects if invalid.
 */
export function AuthGuard({ children, requireWorkspace = true }: { children: ReactNode; requireWorkspace?: boolean }) {
  const { status } = useAuth();
  const router = useRouter();
  const workspaces = useWorkspaces(status === "authenticated");

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
    if (status === "authenticated" && requireWorkspace && workspaces.data?.length === 0) {
      router.replace("/onboarding/workspace");
    }
  }, [status, requireWorkspace, workspaces.data, router]);

  if (status !== "authenticated" || workspaces.isLoading || (requireWorkspace && !workspaces.data?.length)) {
    return (
      <div className="grid min-h-dvh place-items-center p-6">
        <div className="flex w-full max-w-md flex-col gap-4">
          <Skeleton className="h-10 w-40" />
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
