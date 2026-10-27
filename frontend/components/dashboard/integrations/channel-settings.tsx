"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { useChannelOperations, useChannels } from "@/hooks/api/use-channels";
import { useAuth } from "@/hooks/use-auth";
import { useMyWorkspace, useWorkspaceMembers } from "@/hooks/api/use-workspace";
import type { ChannelConnectionStatus } from "@/types/channel";

type Provider = "line" | "facebook";

export function ChannelSettings() {
  const t = useTranslations("dashboard.integrations");
  const { data = [], isLoading, isError, refetch } = useChannels();
  const workspace = useMyWorkspace();
  const members = useWorkspaceMembers(workspace.data?.id);
  const { user } = useAuth();
  const role = members.data?.find((member) => member.user_id === user?.id)?.role;
  const canManage = role === "owner" || role === "admin";
  const operations = useChannelOperations();
  const [provider, setProvider] = useState<Provider | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const update = (name: string, value: string) =>
    setForm((current) => ({ ...current, [name]: value }));

  async function submit() {
    if (provider === "line") {
      await operations.connectLine.mutateAsync({
        display_name: form.display_name,
        external_account_id: form.external_account_id,
        channel_access_token: form.channel_access_token,
        channel_secret: form.channel_secret,
      });
    } else if (provider === "facebook") {
      await operations.connectFacebook.mutateAsync({
        display_name: form.display_name,
        external_account_id: form.external_account_id,
        page_access_token: form.page_access_token,
        app_secret: form.app_secret,
        verify_token: form.verify_token,
      });
    }
    setForm({});
    setProvider(null);
  }

  const connection = (name: Provider | "web") =>
    data.find((item) => item.provider === name);
  const webchat = connection("web");
  const webchatUrl = workspace.data?.slug
    ? `/webchat/${workspace.data.slug}`
    : undefined;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("description")}</p>
        <p className="mt-2 text-xs text-muted-foreground">{t("textOnly")}</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <ChannelCard
          name="WebChat"
          status={webchat?.status || "DISCONNECTED"}
          detail={
            webchat?.status === "CONNECTED" && webchatUrl
              ? t("webchatConnected")
              : t("webchatSetup")
          }
          webchatUrl={webchat?.status === "CONNECTED" ? webchatUrl : undefined}
          connectLabel={t("connectWebchat")}
          onConnect={
            canManage && !webchat
              ? () => operations.connectWebChat.mutate()
              : canManage && webchat?.status === "DISCONNECTED"
                ? () => operations.connectWebChat.mutate()
                : undefined
          }
          onDisconnect={
            canManage && webchat?.status === "CONNECTED"
              ? () => operations.disconnect.mutate(webchat.id)
              : undefined
          }
          pending={
            operations.connectWebChat.isPending || operations.disconnect.isPending
          }
        />
        {(["line", "facebook"] as const).map((name) => {
          const item = connection(name);
          return (
            <ChannelCard
              key={name}
              name={name === "line" ? "LINE OA" : "Facebook Page"}
              status={item?.status || "DISCONNECTED"}
              detail={item?.external_account_name || item?.display_name || t("notConnected")}
              webhook={
                item
                  ? `/api/v1/channels/webhooks/${name}/${item.id}`
                  : undefined
              }
              onConnect={canManage ? () => setProvider(name) : undefined}
              onDisconnect={item && canManage ? () => operations.disconnect.mutate(item.id) : undefined}
            />
          );
        })}
      </div>
      {!canManage && !isLoading ? <p className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">{t("readOnly")}</p> : null}
      {isError ? <div className="rounded-md border border-destructive/30 p-4 text-sm text-destructive">{t("error")} <button className="underline" onClick={() => refetch()}>{t("retry")}</button></div> : null}
      {provider && canManage ? (
        <div className="max-w-2xl rounded-lg border border-border bg-card p-6">
          <h2 className="font-semibold">{t("connect", { provider })}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("secretNote")}</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {fields(provider).map((field) => (
              <input
                key={field}
                type={field.includes("token") || field.includes("secret") ? "password" : "text"}
                value={form[field] || ""}
                onChange={(event) => update(field, event.target.value)}
                placeholder={t(field)}
                autoComplete="off"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm"
              />
            ))}
          </div>
          <div className="mt-4 flex gap-2">
            <button onClick={submit} className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground">{t("save")}</button>
            <button onClick={() => { setProvider(null); setForm({}); }} className="rounded-md border px-4 py-2 text-sm">{t("cancel")}</button>
          </div>
        </div>
      ) : null}
      {isLoading ? <p className="text-sm text-muted-foreground">{t("loading")}</p> : null}
    </div>
  );
}

function fields(provider: Provider) {
  const shared = ["display_name", "external_account_id"];
  return provider === "line"
    ? [...shared, "channel_access_token", "channel_secret"]
    : [...shared, "page_access_token", "app_secret", "verify_token"];
}

function ChannelCard({ name, status, detail, webhook, webchatUrl, connectLabel, onConnect, onDisconnect, pending = false }: { name: string; status: ChannelConnectionStatus; detail: string; webhook?: string; webchatUrl?: string; connectLabel?: string; onConnect?: () => void; onDisconnect?: () => void; pending?: boolean }) {
  const t = useTranslations("dashboard.integrations");
  return <section className="rounded-lg border border-border bg-card p-5"><div className="flex items-center justify-between"><h2 className="font-semibold">{name}</h2><span className={status === "ERROR" ? "text-xs font-medium text-destructive" : "text-xs font-medium"}>{t(`statuses.${status}`)}</span></div><p className="mt-2 min-h-10 text-sm text-muted-foreground">{detail}</p>{status === "ERROR" ? <p className="text-xs text-destructive">{t("connectionError")}</p> : null}{webhook ? <code className="mt-2 block break-all rounded-lg bg-muted px-2 py-1 text-xs">{webhook}</code> : null}{webchatUrl ? <a className="mt-2 block break-all text-xs text-primary underline" href={webchatUrl} target="_blank" rel="noreferrer">{webchatUrl}</a> : null}{onConnect && !onDisconnect ? <button disabled={pending} onClick={onConnect} className="mt-4 text-sm font-medium text-primary disabled:opacity-50">{connectLabel || t("configure")}</button> : null}{onDisconnect ? <button disabled={pending} onClick={onDisconnect} className="mt-4 text-sm font-medium text-destructive disabled:opacity-50">{t("disconnect")}</button> : null}</section>;
}
