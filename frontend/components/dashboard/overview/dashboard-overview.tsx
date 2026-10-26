"use client";

import {
  AlertTriangle,
  ArrowRight,
  Bell,
  BookOpen,
  CheckCircle2,
  ClipboardList,
  CreditCard,
  Inbox,
  Plug,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { OperationalState } from "@/components/dashboard/shared/operational-state";
import { PageHeader } from "@/components/dashboard/shared/page-header";
import { StatusBadge } from "@/components/dashboard/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useActions } from "@/hooks/api/use-actions";
import { useChannels } from "@/hooks/api/use-channels";
import { useConversations } from "@/hooks/api/use-conversations";
import { useKnowledgeDocuments } from "@/hooks/api/use-knowledge";
import { useNotifications } from "@/hooks/api/use-notifications";
import { usePayments } from "@/hooks/api/use-payments";
import { useMyWorkspace, useWorkspaceAccess } from "@/hooks/api/use-workspace";

export function DashboardOverview() {
  const t = useTranslations("operations.overview");
  const { data: workspace } = useMyWorkspace();
  const access = useWorkspaceAccess(workspace?.id);
  const allowed = new Set(access.data?.capabilities ?? []);
  const conversations = useConversations({ page: 1, page_size: 100, sort_by: "last_message_at", order: "desc" }, allowed.has("conversation.read"));
  const actions = useActions({ page: 1, page_size: 100 }, allowed.has("action.read"));
  const knowledge = useKnowledgeDocuments(allowed.has("knowledge.read"));
  const payments = usePayments(allowed.has("payment.read"));
  const channels = useChannels(allowed.has("workspace.settings.manage"));
  const notifications = useNotifications(allowed.has("dashboard.view"));
  const queries = [
    access,
    ...(allowed.has("conversation.read") ? [conversations] : []),
    ...(allowed.has("action.read") ? [actions] : []),
    ...(allowed.has("dashboard.view") ? [notifications] : []),
    ...(allowed.has("knowledge.read") ? [knowledge] : []),
    ...(allowed.has("payment.read") ? [payments] : []),
    ...(allowed.has("workspace.settings.manage") ? [channels] : []),
  ];
  const loading = queries.some((query) => query.isLoading);
  const failed = queries.some((query) => query.isError);
  const retry = () => void Promise.all(queries.map((query) => query.refetch()));

  const conversationItems = conversations.data?.items ?? [];
  const actionItems = actions.data?.items ?? [];
  const documentItems = knowledge.data?.items ?? [];
  const attention = [
    { label: t("attention"), value: conversationItems.filter((item) => item.needs_attention).length, href: "/dashboard/inbox", icon: Inbox },
    { label: t("openActions"), value: actionItems.filter((item) => !["COMPLETED", "FAILED", "CANCELLED"].includes(item.status)).length, href: "/dashboard/actions", icon: ClipboardList },
    { label: t("pendingPayments"), value: (payments.data ?? []).filter((item) => ["PENDING", "VERIFYING"].includes(item.status)).length, href: "/dashboard/payments", icon: CreditCard },
    { label: t("unreadNotifications"), value: notifications.data?.unread_count ?? 0, href: "/dashboard/notifications", icon: Bell },
  ].filter((item) => item.href !== "/dashboard/inbox" || allowed.has("conversation.read"))
    .filter((item) => item.href !== "/dashboard/actions" || allowed.has("action.read"))
    .filter((item) => item.href !== "/dashboard/payments" || allowed.has("payment.read"));
  const readiness = [
    { label: t("knowledgeReady"), value: documentItems.filter((item) => item.status === "READY").length, href: "/dashboard/knowledge", icon: BookOpen },
    { label: t("connectedChannels"), value: (channels.data ?? []).filter((item) => item.status === "CONNECTED").length, href: "/dashboard/integrations", icon: Plug },
  ].filter((item) => item.href !== "/dashboard/knowledge" || allowed.has("knowledge.read"))
    .filter((item) => item.href !== "/dashboard/integrations" || allowed.has("workspace.settings.manage"));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
        actions={<Button variant="outline" size="sm" onClick={retry} disabled={loading}><RefreshCw className={loading ? "animate-spin" : undefined} />{t("refresh")}</Button>}
      />

      {loading ? <OverviewSkeleton /> : failed ? (
        <OperationalState icon={AlertTriangle} title={t("error")} description={t("errorDescription")} actionLabel={t("retry")} onAction={retry} tone="danger" />
      ) : (
        <>
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.7fr)]">
            <section className="rounded-lg border border-border bg-card">
              <div className="flex items-center justify-between border-b border-border px-5 py-4">
                <div><h2 className="font-semibold">{t("needsAttention")}</h2><p className="mt-0.5 text-sm text-muted-foreground">{t("needsAttentionDescription")}</p></div>
                <AlertTriangle className="size-5 text-warning" />
              </div>
              <div className="divide-y divide-border">
                {attention.map(({ label, value, href, icon: Icon }) => (
                  <Link key={href} href={href} className="group flex items-center gap-3 px-5 py-4 transition-colors hover:bg-muted/50">
                    <span className="grid size-9 place-items-center rounded-md bg-muted text-muted-foreground group-hover:bg-brand-soft group-hover:text-brand"><Icon className="size-[18px]" /></span>
                    <span className="min-w-0 flex-1 text-sm font-medium">{label}</span>
                    <span className="text-xl font-semibold tabular-nums">{value}</span>
                    <ArrowRight className="size-4 text-muted-foreground" />
                  </Link>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-border bg-card">
              <div className="border-b border-border px-5 py-4"><h2 className="font-semibold">{t("systemReadiness")}</h2><p className="mt-0.5 text-sm text-muted-foreground">{t("systemReadinessDescription")}</p></div>
              <div className="space-y-3 p-5">
                {readiness.map(({ label, value, href, icon: Icon }) => (
                  <Link key={href} href={href} className="flex items-center gap-3 rounded-md border border-border p-3 transition-colors hover:bg-muted/50"><Icon className="size-[18px] text-brand" /><span className="flex-1 text-sm">{label}</span><span className="font-semibold tabular-nums">{value}</span></Link>
                ))}
                <div className="flex items-start gap-3 rounded-md bg-positive/10 p-3 text-sm"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-positive" /><p>{t("liveDataNotice")}</p></div>
              </div>
            </section>
          </div>

          {allowed.has("conversation.read") ? <section className="rounded-lg border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div><h2 className="font-semibold">{t("recentConversations")}</h2><p className="mt-0.5 text-sm text-muted-foreground">{t("recentConversationsDescription")}</p></div>
              <Button asChild variant="ghost" size="sm"><Link href="/dashboard/inbox">{t("viewInbox")}<ArrowRight /></Link></Button>
            </div>
            {!conversationItems.length ? <OperationalState icon={Inbox} title={t("emptyConversations")} className="m-5 min-h-36" /> : (
              <div className="divide-y divide-border">
                {conversationItems.slice(0, 6).map((item) => (
                  <Link key={item.id} href={`/dashboard/inbox?conversation=${item.id}`} className="grid gap-2 px-5 py-4 transition-colors hover:bg-muted/45 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center">
                    <div className="min-w-0"><p className="truncate text-sm font-medium">{item.subject || item.customer_id}</p><p className="mt-0.5 text-xs text-muted-foreground">{item.channel.toUpperCase()}</p></div>
                    <StatusBadge status={item.ai_mode} />
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">{item.needs_attention ? <span className="font-medium text-warning">{t("attentionShort")}</span> : null}{item.unread_count ? <span>{t("unread", { count: item.unread_count })}</span> : null}</div>
                  </Link>
                ))}
              </div>
            )}
          </section> : null}
        </>
      )}
    </div>
  );
}

function OverviewSkeleton() {
  return <div className="grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.7fr)]" aria-label="Loading"><Skeleton className="h-[340px] rounded-lg" /><Skeleton className="h-[340px] rounded-lg" /><Skeleton className="h-72 rounded-lg xl:col-span-2" /></div>;
}
