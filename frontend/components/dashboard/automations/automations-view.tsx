"use client";

import { AlertTriangle, Loader2, Plus, Power, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useAutomationExecutions,
  useAutomationMutations,
  useAutomationStatus,
  useAutomations,
} from "@/hooks/api/use-automations";
import { useMyWorkspace, useWorkspaceMembers } from "@/hooks/api/use-workspace";
import { useAuth } from "@/hooks/use-auth";
import type { AutomationActionType } from "@/types/automation";

const triggers = [
  "hotel.booking.confirmed",
  "hotel.booking.cancelled",
  "hotel.payment.requires_review",
  "hotel.stay.checked_in",
  "hotel.stay.checked_out",
  "hotel.room.dirty",
  "hotel.housekeeping.completed",
  "hotel.room.ready",
];

export function AutomationsView() {
  const t = useTranslations("automations");
  const { user } = useAuth();
  const workspace = useMyWorkspace();
  const members = useWorkspaceMembers(workspace.data?.id);
  const role = members.data?.find((member) => member.user_id === user?.id)?.role;
  const canManage = role === "owner" || role === "admin";
  const status = useAutomationStatus(canManage);
  const automations = useAutomations();
  const executions = useAutomationExecutions();
  const mutations = useAutomationMutations();
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState(triggers[0]);
  const [action, setAction] = useState<AutomationActionType>("internal.notification");
  const [template, setTemplate] = useState("Booking {{booking_reference}} confirmed");

  const create = async () => {
    try {
      await mutations.create.mutateAsync({
        name,
        active: false,
        trigger_event_type: trigger,
        trigger_version: 1,
        conditions: [],
        action_type: action,
        action_config:
          action === "customer.message"
            ? { template }
            : { title: name, body: template, recipient: "administrators" },
        schedule_mode: "IMMEDIATE",
        schedule_config: {},
      });
      setName("");
      toast.success(t("saved"));
    } catch {
      toast.error(t("error"));
    }
  };

  const retry = async (executionId: string) => {
    try {
      await mutations.retry.mutateAsync(executionId);
      toast.success(t("retryQueued"));
    } catch {
      toast.error(t("retryError"));
    }
  };

  if (automations.isLoading || executions.isLoading) {
    return <Loader2 aria-label={t("loading")} className="size-6 animate-spin" />;
  }
  if (automations.isError || executions.isError) {
    return <p role="alert" className="text-destructive">{t("error")}</p>;
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </header>

      {canManage ? (
        <section className="space-y-4 rounded-2xl border bg-card p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-semibold">{t("operations")}</h2>
              <p className="text-sm text-muted-foreground">{t("operationsDescription")}</p>
            </div>
            {status.isLoading ? <Loader2 className="size-5 animate-spin" /> : null}
            {status.data ? (
              <Badge
                variant={status.data.worker.health === "HEALTHY" ? "default" : "outline"}
                className={status.data.worker.health === "HEALTHY" ? undefined : "text-destructive"}
              >
                {t(`worker.${status.data.worker.health}`)}
              </Badge>
            ) : null}
          </div>
          {status.isError ? <p role="alert" className="text-sm text-destructive">{t("statusError")}</p> : null}
          {status.data ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {(["pending", "running", "scheduled", "terminal_failed"] as const).map((key) => (
                  <div key={key} className="rounded-xl border p-3">
                    <p className="text-xs text-muted-foreground">{t(`queue.${key}`)}</p>
                    <p className="text-xl font-semibold">{status.data.queue[key]}</p>
                  </div>
                ))}
              </div>
              {status.data.alerts.length ? (
                <div className="flex flex-wrap gap-2">
                  {status.data.alerts.map((alert) => <Badge key={alert} variant="outline" className="text-destructive">{alert}</Badge>)}
                </div>
              ) : <p className="text-sm text-muted-foreground">{t("noAlerts")}</p>}
              <div>
                <h3 className="text-sm font-medium">{t("recentFailures")}</h3>
                {!status.data.recent_failures.length ? (
                  <p className="mt-2 text-sm text-muted-foreground">{t("noFailures")}</p>
                ) : status.data.recent_failures.map((execution) => (
                  <div key={execution.id} className="mt-2 flex flex-wrap items-center gap-3 border-t pt-2 text-sm">
                    <AlertTriangle className="size-4 text-destructive" />
                    <span>{execution.last_error_code ?? t("unknownError")}</span>
                    <span>{t("attempts", { count: execution.attempt_count })}</span>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={mutations.retry.isPending}
                      onClick={() => retry(execution.id)}
                    >
                      <RefreshCw className="size-4" />{t("retry")}
                    </Button>
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </section>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {(["PENDING", "RUNNING", "SUCCEEDED", "FAILED"] as const).map((status) => (
          <div key={status} className="rounded-2xl border bg-card p-4">
            <p className="text-xs text-muted-foreground">{status}</p>
            <p className="text-2xl font-semibold">{executions.data?.counts[status] ?? 0}</p>
          </div>
        ))}
      </div>

      {canManage ? (
        <section className="space-y-3 rounded-2xl border bg-card p-5">
          <h2 className="font-semibold">{t("create")}</h2>
          <div className="grid gap-3 lg:grid-cols-3">
            <Input value={name} onChange={(event) => setName(event.target.value)} placeholder={t("name")} />
            <select className="h-10 rounded-md border bg-background px-2" value={trigger} onChange={(event) => setTrigger(event.target.value)}>
              {triggers.map((item) => <option key={item}>{item}</option>)}
            </select>
            <select className="h-10 rounded-md border bg-background px-2" value={action} onChange={(event) => setAction(event.target.value as AutomationActionType)}>
              <option value="internal.notification">{t("notification")}</option>
              <option value="customer.message">{t("customerMessage")}</option>
            </select>
          </div>
          <textarea className="min-h-24 w-full rounded-md border bg-background p-3 text-sm" value={template} onChange={(event) => setTemplate(event.target.value)} />
          <Button disabled={!name.trim() || mutations.create.isPending} onClick={create}>
            <Plus className="size-4" />{t("create")}
          </Button>
          <p className="text-xs text-muted-foreground">{t("optIn")}</p>
        </section>
      ) : null}

      <section className="overflow-x-auto rounded-2xl border bg-card">
        <table className="w-full text-left text-sm">
          <thead><tr className="border-b"><th className="p-3">{t("name")}</th><th className="p-3">{t("trigger")}</th><th className="p-3">{t("action")}</th><th className="p-3">{t("status")}</th><th className="p-3">{t("manage")}</th></tr></thead>
          <tbody>{automations.data?.items.map((item) => <tr key={item.id} className="border-b last:border-0"><td className="p-3 font-medium">{item.name}</td><td className="p-3">{item.trigger_event_type}</td><td className="p-3">{item.action_type}</td><td className="p-3"><Badge variant={item.active ? "default" : "outline"}>{item.active ? t("enabled") : t("disabled")}</Badge></td><td className="p-3">{canManage ? <Button size="sm" variant="outline" onClick={() => (item.active ? mutations.disable : mutations.enable).mutate(item.id)}><Power className="size-4" />{item.active ? t("disable") : t("enable")}</Button> : "—"}</td></tr>)}</tbody>
        </table>
        {!automations.data?.total ? <p className="p-8 text-center text-muted-foreground">{t("empty")}</p> : null}
      </section>

      <section className="overflow-x-auto rounded-2xl border bg-card p-5">
        <h2 className="font-semibold">{t("history")}</h2>
        {!executions.data?.items.length ? <p className="mt-4 text-sm text-muted-foreground">{t("noHistory")}</p> : executions.data.items.map((item) => <div key={item.id} className="mt-3 flex flex-wrap items-center gap-3 border-t pt-3 text-sm"><Badge variant="outline" className={item.status === "FAILED" ? "text-destructive" : undefined}>{item.status}</Badge><span>{new Date(item.scheduled_for).toLocaleString()}</span><span>{t("attempts", { count: item.attempt_count })}</span>{item.last_error_code ? <span className="inline-flex items-center gap-1 text-destructive"><AlertTriangle className="size-4" />{item.last_error_code}</span> : null}</div>)}
      </section>
    </div>
  );
}
