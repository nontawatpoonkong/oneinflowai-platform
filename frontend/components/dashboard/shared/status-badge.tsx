import { cn } from "@/lib/utils";

const SUCCESS = new Set(["READY", "CONFIRMED", "SUCCEEDED", "COMPLETED", "CONNECTED", "VALID", "ACTIVE"]);
const WARNING = new Set(["DIRTY", "HELD", "PENDING", "VERIFYING", "REQUIRES_REVIEW", "WAITING", "PARTIAL"]);
const DANGER = new Set(["FAILED", "ERROR", "OUT_OF_SERVICE", "REJECTED", "INVALID"]);
const INFO = new Set(["EXPECTED", "RUNNING", "IN_PROGRESS", "CLEANING", "PROCESSING", "ASSIGNED"]);

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const value = status.toUpperCase();
  const tone = SUCCESS.has(value)
    ? "border-positive/25 bg-positive/10 text-positive"
    : WARNING.has(value)
      ? "border-warning/30 bg-warning/10 text-foreground"
      : DANGER.has(value)
        ? "border-destructive/25 bg-destructive/10 text-destructive"
        : INFO.has(value)
          ? "border-info/25 bg-info/10 text-info"
          : "border-border bg-muted text-muted-foreground";

  return (
    <span className={cn("inline-flex items-center rounded-md border px-2 py-1 text-[11px] font-semibold", tone)}>
      {label ?? status.replaceAll("_", " ")}
    </span>
  );
}
