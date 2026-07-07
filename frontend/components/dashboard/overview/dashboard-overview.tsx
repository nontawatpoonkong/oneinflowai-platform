"use client";

import { Boxes, MessageSquare, Users } from "lucide-react";
import { useTranslations } from "next-intl";

import { LatestConversations } from "@/components/dashboard/overview/latest-conversations";
import { LatestCustomers } from "@/components/dashboard/overview/latest-customers";
import { OverviewKpi } from "@/components/dashboard/overview/overview-kpi";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useConversations } from "@/hooks/api/use-conversations";
import { useCustomers } from "@/hooks/api/use-customers";
import { useMyWorkspace } from "@/hooks/api/use-workspace";
import { useAuth } from "@/hooks/use-auth";

const LATEST = { page: 1, page_size: 5, sort_by: "created_at", order: "desc" } as const;

export function DashboardOverview() {
  const t = useTranslations("dashboard.overview");
  const { user } = useAuth();
  const workspace = useMyWorkspace();
  const customers = useCustomers(LATEST);
  const conversations = useConversations(LATEST);

  return (
    <div className="flex flex-col gap-6">
      {workspace.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <Card className="flex flex-col gap-1 p-6">
          <p className="text-sm text-muted-foreground">
            {user?.full_name
              ? t("welcomeNamed", { name: user.full_name })
              : t("welcome")}
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">
              {workspace.data?.name ?? t("workspaceFallback")}
            </h1>
            {workspace.data ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand">
                <Boxes className="size-3" />/{workspace.data.slug}
              </span>
            ) : null}
          </div>
          {user ? (
            <p className="mt-1 text-sm text-muted-foreground">
              {t("signedInAs", { email: user.email })}
            </p>
          ) : null}
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <OverviewKpi
          label={t("customerCount")}
          value={customers.data?.total}
          icon={Users}
          isLoading={customers.isLoading}
        />
        <OverviewKpi
          label={t("conversationCount")}
          value={conversations.data?.total}
          icon={MessageSquare}
          isLoading={conversations.isLoading}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <LatestCustomers />
        <LatestConversations />
      </div>
    </div>
  );
}
