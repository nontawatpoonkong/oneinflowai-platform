"use client";

import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { PaginationControls } from "@/components/shared/pagination-controls";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  useHousekeepingMutations,
  useHousekeepingTasks,
} from "@/hooks/api/use-housekeeping";
import { useHotelProperties } from "@/hooks/api/use-stays";
import { useMyWorkspace, useWorkspaceMembers } from "@/hooks/api/use-workspace";
import { useAuth } from "@/hooks/use-auth";
import type {
  HousekeepingPriority,
  HousekeepingTaskStatus,
} from "@/types/housekeeping";
import type { RoomReadinessStatus } from "@/types/stay";

const PAGE_SIZES = { initial: 20 };

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

export function HousekeepingView() {
  const t = useTranslations("housekeeping");
  const common = useTranslations("common");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES.initial);
  const [propertyId, setPropertyId] = useState("");
  const [status, setStatus] = useState<HousekeepingTaskStatus>();
  const [priority, setPriority] = useState<HousekeepingPriority>();
  const [readiness, setReadiness] = useState<RoomReadinessStatus>();
  const [assigneeId, setAssigneeId] = useState("");
  const properties = useHotelProperties();
  const workspace = useMyWorkspace();
  const members = useWorkspaceMembers(workspace.data?.id);
  const tasks = useHousekeepingTasks({
    property_id: propertyId || undefined,
    status,
    priority,
    readiness_status: readiness,
    assignee_id: assigneeId || undefined,
    page,
    page_size: pageSize,
  });
  const mutations = useHousekeepingMutations();
  const { user } = useAuth();
  const role = members.data?.find((item) => item.user_id === user?.id)?.role;
  const isAdmin = role === "owner" || role === "admin";

  const updateFilter = (update: () => void) => {
    update();
    setPage(1);
  };
  const act = async (operation: () => Promise<unknown>) => {
    try {
      await operation();
      toast.success(t("saved"));
    } catch {
      toast.error(t("error"));
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </header>

      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
        <select
          aria-label={t("property")}
          className="h-10 rounded-md border bg-background px-2"
          value={propertyId}
          onChange={(event) => updateFilter(() => setPropertyId(event.target.value))}
        >
          <option value="">{t("allProperties")}</option>
          {properties.data?.map((property) => (
            <option key={property.id} value={property.id}>
              {property.name}
            </option>
          ))}
        </select>
        <select
          aria-label={t("status")}
          className="h-10 rounded-md border bg-background px-2"
          value={status ?? ""}
          onChange={(event) =>
            updateFilter(() =>
              setStatus((event.target.value || undefined) as HousekeepingTaskStatus),
            )
          }
        >
          <option value="">{t("allStatuses")}</option>
          {(["PENDING", "IN_PROGRESS", "COMPLETED", "CANCELLED"] as const).map(
            (value) => (
              <option key={value}>{value}</option>
            ),
          )}
        </select>
        <select
          aria-label={t("priority")}
          className="h-10 rounded-md border bg-background px-2"
          value={priority ?? ""}
          onChange={(event) =>
            updateFilter(() =>
              setPriority((event.target.value || undefined) as HousekeepingPriority),
            )
          }
        >
          <option value="">{t("allPriorities")}</option>
          {(["LOW", "NORMAL", "HIGH"] as const).map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        <select
          aria-label={t("readiness")}
          className="h-10 rounded-md border bg-background px-2"
          value={readiness ?? ""}
          onChange={(event) =>
            updateFilter(() =>
              setReadiness((event.target.value || undefined) as RoomReadinessStatus),
            )
          }
        >
          <option value="">{t("allReadiness")}</option>
          {(["READY", "DIRTY", "CLEANING"] as const).map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        <select
          aria-label={t("assignee")}
          className="h-10 rounded-md border bg-background px-2"
          value={assigneeId}
          onChange={(event) => updateFilter(() => setAssigneeId(event.target.value))}
        >
          <option value="">{t("allAssignees")}</option>
          {members.data?.map((member) => (
            <option key={member.user_id} value={member.user_id}>
              {member.full_name ?? member.email}
            </option>
          ))}
        </select>
      </div>

      {tasks.isLoading ? (
        <Loader2 aria-label={t("loading")} className="size-6 animate-spin" />
      ) : tasks.isError ? (
        <p role="alert">{t("error")}</p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border bg-card">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b">
                <th className="p-3">{t("room")}</th>
                <th className="p-3">{t("property")}</th>
                <th className="p-3">{t("readiness")}</th>
                <th className="p-3">{t("status")}</th>
                <th className="p-3">{t("priority")}</th>
                <th className="p-3">{t("assignee")}</th>
                <th className="p-3">{t("checkout")}</th>
                <th className="p-3">{t("started")}</th>
                <th className="p-3">{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {tasks.data?.items.map((task) => {
                const canWork = isAdmin || task.assigned_to_user_id === user?.id;
                return (
                  <tr key={task.id} className="border-b last:border-0">
                    <td className="p-3 font-medium">
                      {task.room_code} · {task.room_type_name}
                    </td>
                    <td className="p-3">{task.property_name}</td>
                    <td className="p-3"><Badge variant="muted">{task.readiness_status}</Badge></td>
                    <td className="p-3"><Badge variant="outline">{task.status}</Badge></td>
                    <td className="p-3">{task.priority}</td>
                    <td className="p-3">
                      <select
                        aria-label={t("assignee")}
                        className="h-9 rounded-md border bg-background px-2"
                        disabled={!isAdmin || ["COMPLETED", "CANCELLED"].includes(task.status)}
                        value={task.assigned_to_user_id ?? ""}
                        onChange={(event) => event.target.value && act(() => mutations.assign.mutateAsync({ id: task.id, userId: event.target.value }))}
                      >
                        <option value="">{t("unassigned")}</option>
                        {members.data?.map((member) => <option key={member.user_id} value={member.user_id}>{member.full_name ?? member.email}</option>)}
                      </select>
                    </td>
                    <td className="p-3 text-xs">{formatDate(task.checkout_at)}</td>
                    <td className="p-3 text-xs">{formatDate(task.started_at)}</td>
                    <td className="p-3">
                      <div className="flex gap-2">
                        {task.status === "PENDING" && canWork ? <Button size="sm" onClick={() => act(() => mutations.start.mutateAsync(task.id))}>{t("start")}</Button> : null}
                        {task.status === "IN_PROGRESS" && canWork ? <Button size="sm" onClick={() => act(() => mutations.complete.mutateAsync(task.id))}>{t("complete")}</Button> : null}
                        {isAdmin && ["PENDING", "IN_PROGRESS"].includes(task.status) ? <Button size="sm" variant="outline" onClick={() => act(() => mutations.cancel.mutateAsync(task.id))}>{t("cancel")}</Button> : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {tasks.data?.total === 0 ? <p className="p-6 text-center text-muted-foreground">{t("empty")}</p> : null}
          {tasks.data ? (
            <PaginationControls
              page={tasks.data.page}
              pageSize={tasks.data.page_size}
              total={tasks.data.total}
              totalPages={tasks.data.total_pages}
              previousLabel={common("previous")}
              nextLabel={common("next")}
              pageSizeLabel={common("pageSize")}
              summaryLabel={common("pageSummary", { page: tasks.data.page, totalPages: tasks.data.total_pages, total: tasks.data.total })}
              onPageChange={setPage}
              onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}
