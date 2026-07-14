"use client";

import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";

import { ConversationTrend } from "@/components/dashboard/overview/conversation-trend";
import { DashboardHero } from "@/components/dashboard/overview/dashboard-hero";
import { Greeting } from "@/components/dashboard/overview/greeting";
import { KpiCards } from "@/components/dashboard/overview/kpi-cards";
import { QuickActions } from "@/components/dashboard/overview/quick-actions";
import { RecentActivity } from "@/components/dashboard/overview/recent-activity";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboard } from "@/hooks/use-dashboard";

/** Owner dashboard — greeting, hero, KPIs (live), trend + activity, quick actions. */
export function DashboardOverview() {
  const t = useTranslations();
  const { data, loading, error, refetch } = useDashboard();

  return (
    <div className="flex flex-col gap-6 sm:gap-8">
      <Greeting />
      <DashboardHero />

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[132px] w-full rounded-2xl" />
          ))}
        </div>
      ) : error ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border bg-muted/20 px-6 py-10 text-center">
          <span className="grid size-12 place-items-center rounded-2xl bg-destructive/10 text-destructive">
            <AlertTriangle className="size-6" />
          </span>
          <div>
            <p className="font-semibold">{t("errors.serverTitle")}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("errors.serverDesc")}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="size-4" />
            {t("common.tryAgain")}
          </Button>
        </div>
      ) : !data ? (
        <EmptyState icon={Inbox} title={t("common.noData")} />
      ) : (
        <KpiCards
          values={{
            conversations: data.today_conversations,
            replyRate: data.ai_reply_rate,
            newCustomers: data.new_customers,
            avgResponse: data.avg_response_time,
          }}
        />
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ConversationTrend />
        </div>
        <RecentActivity />
      </div>

      <QuickActions />
    </div>
  );
}
