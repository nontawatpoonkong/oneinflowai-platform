"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/hooks/use-auth";

export function PlatformGuard({ children }: { children: ReactNode }) {
  const { user, status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
    if (status === "authenticated" && !user?.is_platform_admin) {
      router.replace("/dashboard");
    }
  }, [router, status, user]);

  if (status !== "authenticated" || !user?.is_platform_admin) {
    return (
      <main className="grid min-h-dvh place-items-center bg-background p-6">
        <p role="status" className="text-sm text-muted-foreground">
          Verifying platform authority…
        </p>
      </main>
    );
  }
  return <>{children}</>;
}
