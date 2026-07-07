"use client";

import { Boxes, MessageSquare, Users } from "lucide-react";
import { useTranslations } from "next-intl";

import { ChartCard } from "@/components/dashboard/chart-card";
import { MiniChart } from "@/components/dashboard/mini-chart";
import { ServerCards } from "@/components/dashboard/server-cards";
import { CountUp } from "@/components/shared/count-up";
import { Card } from "@/components/ui/card";
import {
  CONVERSATION_TREND,
  CUSTOMER_TREND,
  WORKSPACE_TREND,
} from "@/lib/mock-data";

const WIDGETS = [
  { id: "workspaces", value: 1284, icon: Boxes },
  { id: "conversations", value: 58324, icon: MessageSquare },
  { id: "customers", value: 184203, icon: Users },
];

/** Reusable, animated dashboard content (widgets, charts, realtime servers). */
export function DashboardMock() {
  const t = useTranslations("landing.dashboardPreview");

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-3">
        {WIDGETS.map((w) => (
          <Card key={w.id} className="p-4">
            <span className="grid size-8 place-items-center rounded-lg bg-brand/10 text-brand">
              <w.icon className="size-4" />
            </span>
            <p className="mt-3 text-xl font-semibold tracking-tight">
              <CountUp value={w.value} />
            </p>
            <p className="text-xs text-muted-foreground">{t(`widgets.${w.id}`)}</p>
          </Card>
        ))}
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ChartCard title={t("charts.conversationTrend")} caption={t("charts.last7days")}>
            <MiniChart data={CONVERSATION_TREND} variant="area" />
          </ChartCard>
        </div>
        <ChartCard title={t("charts.workspaceCount")} caption={t("charts.last4weeks")}>
          <MiniChart data={WORKSPACE_TREND} variant="bar" />
        </ChartCard>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <ChartCard title={t("charts.customerCount")} caption={t("charts.last6months")}>
          <MiniChart data={CUSTOMER_TREND} variant="area" />
        </ChartCard>
        <div className="lg:col-span-2">
          <ServerCards />
        </div>
      </div>
    </div>
  );
}
