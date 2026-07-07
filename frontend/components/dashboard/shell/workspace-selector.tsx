"use client";

import { Check, ChevronsUpDown } from "lucide-react";
import { useTranslations } from "next-intl";

import { useDropdown } from "@/components/dashboard/shell/use-dropdown";
import { useMyWorkspace } from "@/hooks/api/use-workspace";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function WorkspaceSelector() {
  const t = useTranslations("dashboard.shell");
  const { data: workspace, isLoading } = useMyWorkspace();
  const { open, setOpen, ref } = useDropdown();

  if (isLoading) return <Skeleton className="h-9 w-40" />;
  if (!workspace) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex max-w-[220px] items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm transition-colors hover:bg-accent"
      >
        <span className="grid size-6 shrink-0 place-items-center rounded-lg bg-brand-gradient text-[10px] font-bold text-brand-foreground">
          {workspace.name.slice(0, 1).toUpperCase()}
        </span>
        <span className="truncate font-medium">{workspace.name}</span>
        <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
      </button>

      <div
        role="listbox"
        className={cn(
          "absolute left-0 mt-2 w-64 origin-top-left rounded-2xl border border-border bg-popover p-1.5 shadow-soft transition-all",
          open
            ? "pointer-events-auto scale-100 opacity-100"
            : "pointer-events-none scale-95 opacity-0",
        )}
      >
        <div className="flex items-center gap-2 rounded-xl bg-accent px-3 py-2">
          <Check className="size-4 text-brand" />
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{workspace.name}</p>
            <p className="truncate text-xs text-muted-foreground">/{workspace.slug}</p>
          </div>
        </div>
        <p className="px-3 py-2 text-xs text-muted-foreground">
          {t("workspaceComingSoon")}
        </p>
      </div>
    </div>
  );
}
