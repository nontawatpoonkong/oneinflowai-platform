"use client";

import { AlertTriangle, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { StatusBadge } from "@/components/dashboard/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { usePMSData, usePMSOperations } from "@/hooks/api/use-pms";
import { useMyWorkspace, useWorkspaceMembers } from "@/hooks/api/use-workspace";
import { useAuth } from "@/hooks/use-auth";
import type {
  PMSInventoryAuthority,
  PMSMappingCreate,
} from "@/types/pms";

const mappingTypes: PMSMappingCreate["entity_type"][] = [
  "PROPERTY",
  "ROOM_TYPE",
  "ROOM",
  "RATE_PLAN",
];

function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

export function PMSView() {
  const t = useTranslations("pms");
  const { user } = useAuth();
  const workspace = useMyWorkspace();
  const members = useWorkspaceMembers(workspace.data?.id);
  const role = members.data?.find((item) => item.user_id === user?.id)?.role;
  const canManage = role === "owner" || role === "admin";
  const [selectedId, setSelectedId] = useState("");
  const initial = usePMSData();
  const connectionId =
    selectedId || initial.connections.data?.[0]?.id || undefined;
  const details = usePMSData(connectionId);
  const operations = usePMSOperations();
  const [name, setName] = useState("");
  const [provider, setProvider] = useState("");
  const [authority, setAuthority] =
    useState<PMSInventoryAuthority>("LOCAL");
  const [entityType, setEntityType] =
    useState<PMSMappingCreate["entity_type"]>("PROPERTY");
  const [externalId, setExternalId] = useState("");
  const [localId, setLocalId] = useState("");

  const selected = useMemo(
    () => initial.connections.data?.find((item) => item.id === connectionId),
    [connectionId, initial.connections.data],
  );
  const providers = initial.providers.data ?? [];
  const providerName = provider || providers[0]?.name || "";
  const pending =
    operations.createConnection.isPending ||
    operations.updateConnection.isPending ||
    operations.testConnection.isPending ||
    operations.sync.isPending ||
    operations.createMapping.isPending;

  const act = async (operation: () => Promise<unknown>, success: string) => {
    try {
      await operation();
      toast.success(success);
    } catch {
      toast.error(t("operationFailed"));
    }
  };

  const createConnection = () =>
    act(async () => {
      const created = await operations.createConnection.mutateAsync({
        provider: providerName,
        name: name.trim(),
        credentials: {},
        sync_mode: "READ_ONLY_IMPORT",
        inventory_authority: authority,
      });
      setSelectedId(created.id);
      setName("");
    }, t("connectionCreated"));

  const createMapping = () =>
    act(async () => {
      await operations.createMapping.mutateAsync({
        connection_id: connectionId!,
        entity_type: entityType,
        external_id: externalId.trim(),
        local_entity_id: localId.trim(),
      });
      setExternalId("");
      setLocalId("");
    }, t("mappingCreated"));

  if (initial.connections.isLoading || initial.providers.isLoading) {
    return <Loader2 className="size-6 animate-spin" />;
  }

  if (initial.connections.isError || initial.providers.isError) {
    return <p className="text-sm text-destructive">{t("loadError")}</p>;
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </header>

      <section className="rounded-lg border bg-card p-5">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 size-5 text-brand" />
          <div>
            <h2 className="font-semibold">{t("readOnlyTitle")}</h2>
            <p className="text-sm text-muted-foreground">{t("readOnlyNotice")}</p>
          </div>
        </div>
      </section>

      {canManage && providers.length ? (
        <section className="grid gap-3 rounded-lg border bg-card p-5 md:grid-cols-4">
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t("connectionName")}
          />
          <select
            aria-label={t("provider")}
            value={providerName}
            onChange={(event) => setProvider(event.target.value)}
            className="h-10 rounded-md border bg-background px-3 text-sm"
          >
            {providers.map((item) => (
              <option key={item.name} value={item.name}>{item.name}</option>
            ))}
          </select>
          <select
            aria-label={t("inventoryAuthority")}
            value={authority}
            onChange={(event) =>
              setAuthority(event.target.value as PMSInventoryAuthority)
            }
            className="h-10 rounded-md border bg-background px-3 text-sm"
          >
            <option value="LOCAL">{t("authority.LOCAL")}</option>
            <option value="PMS">{t("authority.PMS")}</option>
          </select>
          <Button
            disabled={!name.trim() || !providerName || pending}
            onClick={createConnection}
          >
            {t("addConnection")}
          </Button>
        </section>
      ) : canManage ? (
        <p className="rounded-lg border bg-card p-5 text-sm text-muted-foreground">
          {t("noProviders")}
        </p>
      ) : null}

      {!initial.connections.data?.length ? (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          {t("empty")}
        </div>
      ) : (
        <>
          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-semibold">{t("connections")}</h2>
              <select
                aria-label={t("connections")}
                value={connectionId}
                onChange={(event) => setSelectedId(event.target.value)}
                className="h-10 min-w-64 rounded-md border bg-background px-3 text-sm"
              >
                {initial.connections.data.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · {item.provider}
                  </option>
                ))}
              </select>
            </div>
            {selected ? (
              <div className="rounded-lg border bg-card p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-semibold">{selected.name}</h3>
                      <StatusBadge status={selected.status} />
                      {!selected.active ? <Badge variant="muted">{t("inactive")}</Badge> : null}
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {selected.provider} · {selected.sync_mode} · {t("inventoryAuthority")}: {t(`authority.${selected.inventory_authority}`)}
                    </p>
                    <p className="mt-2 text-xs text-muted-foreground">
                      {t("lastSuccess")}: {dateTime(selected.last_successful_sync_at)} · {t("lastFailure")}: {dateTime(selected.last_failed_sync_at)}
                    </p>
                    {selected.last_error_code ? (
                      <p className="mt-1 text-xs text-destructive">{selected.last_error_code}</p>
                    ) : null}
                  </div>
                  {canManage ? (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        disabled={pending}
                        onClick={() => act(
                          () => operations.testConnection.mutateAsync(selected.id),
                          t("testSucceeded"),
                        )}
                      >{t("test")}</Button>
                      <Button
                        disabled={pending || !selected.active}
                        onClick={() => act(
                          () => operations.sync.mutateAsync(selected.id),
                          t("syncStarted"),
                        )}
                      ><RefreshCw className="mr-2 size-4" />{t("sync")}</Button>
                      <Button
                        variant="outline"
                        disabled={pending}
                        onClick={() => act(
                          () => operations.updateConnection.mutateAsync({
                            id: selected.id,
                            payload: { active: !selected.active },
                          }),
                          t("connectionUpdated"),
                        )}
                      >{selected.active ? t("deactivate") : t("activate")}</Button>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}
          </section>

          <section className="grid gap-6 xl:grid-cols-2">
            <div className="rounded-lg border bg-card p-5">
              <h2 className="text-lg font-semibold">{t("mappings")}</h2>
              <p className="text-sm text-muted-foreground">{t("mappingDescription")}</p>
              {canManage ? (
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  <select
                    aria-label={t("entityType")}
                    value={entityType}
                    onChange={(event) =>
                      setEntityType(event.target.value as PMSMappingCreate["entity_type"])
                    }
                    className="h-10 rounded-md border bg-background px-3 text-sm"
                  >
                    {mappingTypes.map((item) => <option key={item}>{item}</option>)}
                  </select>
                  <Input value={externalId} onChange={(event) => setExternalId(event.target.value)} placeholder={t("externalId")} />
                  <Input value={localId} onChange={(event) => setLocalId(event.target.value)} placeholder={t("localId")} />
                  <Button disabled={!externalId.trim() || !localId.trim() || pending} onClick={createMapping}>{t("map")}</Button>
                </div>
              ) : null}
              <div className="mt-4 space-y-2">
                {details.mappings.isLoading ? <Loader2 className="size-5 animate-spin" /> : details.mappings.data?.length ? details.mappings.data.map((item) => (
                  <div key={item.id} className="rounded-md border p-3 text-sm">
                    <div className="flex justify-between gap-2"><span className="font-medium">{item.entity_type}</span><Badge variant="muted">{item.external_id}</Badge></div>
                    <p className="mt-1 break-all text-xs text-muted-foreground">{t("localId")}: {item.local_entity_id}</p>
                  </div>
                )) : <p className="text-sm text-muted-foreground">{t("noMappings")}</p>}
              </div>
            </div>

            <div className="rounded-lg border bg-card p-5">
              <h2 className="text-lg font-semibold">{t("reconciliation")}</h2>
              <p className="text-sm text-muted-foreground">{t("reconciliationDescription")}</p>
              <div className="mt-4 space-y-2">
                {details.issues.isLoading ? <Loader2 className="size-5 animate-spin" /> : details.issues.data?.length ? details.issues.data.map((item) => (
                  <div key={item.id} className="rounded-md border p-3 text-sm">
                    <div className="flex items-center justify-between gap-2"><span className="flex items-center gap-2 font-medium"><AlertTriangle className="size-4 text-warning" />{item.issue_type}</span><StatusBadge status={item.status} /></div>
                    <p className="mt-1 text-xs text-muted-foreground">{item.entity_type} · {item.external_id}</p>
                  </div>
                )) : <p className="text-sm text-muted-foreground">{t("noIssues")}</p>}
              </div>
            </div>
          </section>

          <section className="rounded-lg border bg-card p-5">
            <h2 className="text-lg font-semibold">{t("syncHistory")}</h2>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b bg-muted/40"><tr><th className="p-3">{t("status")}</th><th className="p-3">{t("started")}</th><th className="p-3">{t("fetched")}</th><th className="p-3">{t("applied")}</th><th className="p-3">{t("conflicts")}</th><th className="p-3">{t("error")}</th></tr></thead>
                <tbody>{details.syncRuns.data?.map((run) => <tr key={run.id} className="border-b last:border-0"><td className="p-3"><StatusBadge status={run.status} /></td><td className="p-3">{dateTime(run.started_at)}</td><td className="p-3">{run.entities_fetched}</td><td className="p-3">{run.entities_applied}</td><td className="p-3">{run.conflict_count}</td><td className="p-3">{run.error_code ?? "—"}</td></tr>)}</tbody>
              </table>
              {!details.syncRuns.isLoading && !details.syncRuns.data?.length ? <p className="p-6 text-center text-muted-foreground">{t("noRuns")}</p> : null}
            </div>
          </section>
        </>
      )}
      {!canManage ? <p className="text-sm text-muted-foreground">{t("readOnlyMember")}</p> : null}
    </div>
  );
}
