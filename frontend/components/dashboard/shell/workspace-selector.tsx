"use client";

import { Check, ChevronsUpDown } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { useDropdown } from "@/components/dashboard/shell/use-dropdown";
import { useMyWorkspace, useWorkspaces } from "@/hooks/api/use-workspace";
import { setActiveWorkspaceId } from "@/services/workspace/active-workspace";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function WorkspaceSelector() {
  const t = useTranslations("dashboard.shell");
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: workspace, isLoading } = useMyWorkspace();
  const { data: workspaces = [] } = useWorkspaces();
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
        className="flex max-w-[220px] items-center gap-2 rounded-md border border-border bg-card px-2.5 py-2 text-sm transition-colors hover:bg-accent"
      >
        <span className="grid size-6 shrink-0 place-items-center rounded-md bg-brand-soft text-[10px] font-bold text-brand">
          {workspace.name.slice(0, 1).toUpperCase()}
        </span>
        <span className="truncate font-medium">{workspace.name}</span>
        <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
      </button>

      <div
        role="listbox"
        className={cn(
          "absolute left-0 mt-2 w-64 origin-top-left rounded-lg border border-border bg-popover p-1.5 shadow-soft transition-all",
          open
            ? "pointer-events-auto scale-100 opacity-100"
            : "pointer-events-none scale-95 opacity-0",
        )}
      >
        {workspaces.map((item) => (
          <button
            key={item.id}
            type="button"
            role="option"
            aria-selected={item.id === workspace.id}
            onClick={() => {
              setActiveWorkspaceId(item.id);
              setOpen(false);
              queryClient.clear();
              router.push("/dashboard");
              router.refresh();
            }}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left hover:bg-accent",
              item.id === workspace.id && "bg-accent",
            )}
          >
            <Check className={cn("size-4 text-brand", item.id !== workspace.id && "opacity-0")} />
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium">{item.name}</span>
              <span className="block truncate text-xs text-muted-foreground">/{item.slug}</span>
            </span>
          </button>
        ))}
        {workspaces.length > 1 ? (
          <p className="px-3 py-2 text-xs text-muted-foreground">
            {t("workspaceSwitchHint")}
          </p>
        ) : null}
      </div>
    </div>
  );
}
