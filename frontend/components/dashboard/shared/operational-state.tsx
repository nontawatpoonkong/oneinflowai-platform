import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface OperationalStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  busy?: boolean;
  tone?: "neutral" | "danger";
  className?: string;
}

export function OperationalState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
  busy = false,
  tone = "neutral",
  className,
}: OperationalStateProps) {
  return (
    <div
      className={cn(
        "flex min-h-44 flex-col items-center justify-center rounded-lg border border-dashed bg-card px-6 py-8 text-center",
        tone === "danger" && "border-destructive/35 bg-destructive/5",
        className,
      )}
      role={tone === "danger" ? "alert" : "status"}
    >
      <span className={cn("mb-3 grid size-9 place-items-center rounded-md bg-muted text-muted-foreground", tone === "danger" && "bg-destructive/10 text-destructive")}>
        <Icon className={cn("size-5", busy && "animate-spin")} />
      </span>
      <p className="font-medium">{title}</p>
      {description ? <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p> : null}
      {actionLabel && onAction ? (
        <Button className="mt-4" size="sm" variant="outline" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}
