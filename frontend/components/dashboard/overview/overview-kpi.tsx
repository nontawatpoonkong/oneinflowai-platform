"use client";

import type { LucideIcon } from "lucide-react";

import { CountUp } from "@/components/shared/count-up";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface OverviewKpiProps {
  label: string;
  value: number | undefined;
  icon: LucideIcon;
  isLoading: boolean;
}

export function OverviewKpi({ label, value, icon: Icon, isLoading }: OverviewKpiProps) {
  return (
    <Card className="p-5">
      <span className="grid size-9 place-items-center rounded-xl bg-brand/10 text-brand">
        <Icon className="size-4" />
      </span>
      <div className="mt-4 text-2xl font-semibold tracking-tight">
        {isLoading ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <CountUp value={value ?? 0} />
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{label}</p>
    </Card>
  );
}
