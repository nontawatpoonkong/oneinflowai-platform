"use client";

import { Card } from "@/components/ui/card";
import { useJitter } from "@/hooks/use-jitter";
import { SERVER_CARDS } from "@/lib/premium-data";
import { cn } from "@/lib/utils";

const STATUS_STYLE: Record<string, string> = {
  healthy: "bg-positive",
  warning: "bg-warning",
  critical: "bg-destructive",
};

/** Realtime server/service cards with gently animated mock values. */
export function ServerCards() {
  const values = useJitter(
    SERVER_CARDS.map((s) => ({ id: s.id, base: s.base })),
  );

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
      {SERVER_CARDS.map((service) => (
        <Card key={service.id} className="p-4">
          <div className="flex items-center justify-between">
            <span className="grid size-8 place-items-center rounded-lg bg-brand/10 text-brand">
              <service.icon className="size-4" />
            </span>
            <span
              className={cn(
                "size-2 rounded-full",
                STATUS_STYLE[service.status],
              )}
              aria-label={service.status}
            />
          </div>
          <p className="mt-3 text-lg font-semibold tabular-nums">
            {values[service.id]}
            <span className="ml-0.5 text-xs font-normal text-muted-foreground">
              {service.unit}
            </span>
          </p>
          <p className="text-xs text-muted-foreground">{service.label}</p>
        </Card>
      ))}
    </div>
  );
}
