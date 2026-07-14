"use client";

import { motion } from "framer-motion";
import {
  Activity,
  Bot,
  CheckCircle2,
  UserCog,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/shared/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fadeUp, VIEWPORT } from "@/lib/animations";
import { cn } from "@/lib/utils";

interface ActivityItem {
  id: string;
  name: string;
  action: "aiReplied" | "assigned" | "resolved";
  time: "min2" | "min10" | "min30";
  icon: LucideIcon;
  tone: string;
}

// Mock only (layout-only redesign; no API).
const ITEMS: ActivityItem[] = [
  { id: "1", name: "John", action: "aiReplied", time: "min2", icon: Bot, tone: "bg-brand/10 text-brand" },
  { id: "2", name: "Sarah", action: "assigned", time: "min10", icon: UserCog, tone: "bg-warning/10 text-warning" },
  { id: "3", name: "Booking", action: "resolved", time: "min30", icon: CheckCircle2, tone: "bg-positive/10 text-positive" },
];

export function RecentActivity() {
  const t = useTranslations("dashboard.owner.activity");

  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      whileInView="visible"
      viewport={VIEWPORT}
      className="h-full"
    >
      <Card className="h-full">
        <CardHeader>
          <CardTitle>{t("title")}</CardTitle>
        </CardHeader>
        <CardContent>
          {ITEMS.length === 0 ? (
            <EmptyState
              icon={Activity}
              title={t("emptyTitle")}
              description={t("emptyDesc")}
            />
          ) : (
            <ul className="flex flex-col divide-y divide-border">
              {ITEMS.map((item) => (
                <li key={item.id} className="flex items-center gap-3 py-3">
                  <span
                    className={cn(
                      "grid size-9 shrink-0 place-items-center rounded-full",
                      item.tone,
                    )}
                  >
                    <item.icon className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {t("customer")} {item.name}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {t(`actions.${item.action}`)}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {t(`time.${item.time}`)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
