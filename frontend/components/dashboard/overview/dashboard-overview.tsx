"use client";

import Link from "next/link";
import { AlertTriangle, Bell, BookOpen, ClipboardList, CreditCard, Inbox, Plug, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { useActions } from "@/hooks/api/use-actions";
import { useChannels } from "@/hooks/api/use-channels";
import { useConversations } from "@/hooks/api/use-conversations";
import { useKnowledgeDocuments } from "@/hooks/api/use-knowledge";
import { useNotifications } from "@/hooks/api/use-notifications";
import { usePayments } from "@/hooks/api/use-payments";

export function DashboardOverview() {
  const t = useTranslations("operations.overview");
  const conversations = useConversations({page:1,page_size:100,sort_by:"last_message_at",order:"desc"});
  const actions = useActions({page:1,page_size:100}); const knowledge = useKnowledgeDocuments();
  const payments = usePayments(); const channels = useChannels(); const notifications = useNotifications();
  const queries = [conversations, actions, knowledge, payments, channels, notifications];
  const loading = queries.some((query) => query.isLoading); const failed = queries.some((query) => query.isError);
  const retry = () => void Promise.all(queries.map((query) => query.refetch()));
  const conversationItems = conversations.data?.items ?? []; const actionItems = actions.data?.items ?? []; const documentItems = knowledge.data?.items ?? [];
  const cards = [
    {label:t("attention"),value:conversationItems.filter((item)=>item.needs_attention).length,href:"/dashboard/inbox",icon:Inbox},
    {label:t("openActions"),value:actionItems.filter((item)=>!["COMPLETED","FAILED","CANCELLED"].includes(item.status)).length,href:"/dashboard/actions",icon:ClipboardList},
    {label:t("knowledgeReady"),value:documentItems.filter((item)=>item.status==="READY").length,href:"/dashboard/knowledge",icon:BookOpen},
    {label:t("pendingPayments"),value:(payments.data??[]).filter((item)=>["PENDING","VERIFYING"].includes(item.status)).length,href:"/dashboard/payments",icon:CreditCard},
    {label:t("connectedChannels"),value:(channels.data??[]).filter((item)=>item.status==="CONNECTED").length+1,href:"/dashboard/integrations",icon:Plug},
    {label:t("unreadNotifications"),value:notifications.data?.unread_count??0,href:"/dashboard/notifications",icon:Bell},
  ];
  return <div className="space-y-7"><header><h1 className="text-2xl font-semibold">{t("title")}</h1><p className="text-sm text-muted-foreground">{t("description")}</p></header>
    {loading ? <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{Array.from({length:6}).map((_,index)=><div key={index} className="h-28 animate-pulse rounded-2xl bg-muted"/>)}</div> : failed ? <div className="rounded-2xl border border-dashed p-8 text-center"><AlertTriangle className="mx-auto mb-3 size-8 text-destructive"/><p>{t("error")}</p><Button className="mt-3" variant="outline" onClick={retry}><RefreshCw className="size-4"/>{t("retry")}</Button></div> : <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{cards.map(({label,value,href,icon:Icon})=><Link key={href} href={href} className="rounded-2xl border bg-card p-5 transition hover:border-brand/40 hover:shadow-sm"><div className="flex items-start justify-between"><div><p className="text-sm text-muted-foreground">{label}</p><p className="mt-2 text-3xl font-semibold tabular-nums">{value}</p></div><Icon className="size-5 text-brand"/></div></Link>)}</div>}
    <section><h2 className="mb-3 text-lg font-semibold">{t("recentConversations")}</h2>{!conversationItems.length&&!loading?<p className="rounded-2xl border border-dashed p-8 text-center text-sm text-muted-foreground">{t("emptyConversations")}</p>:<div className="grid gap-3 md:grid-cols-2">{conversationItems.slice(0,6).map((item)=><Link key={item.id} href={`/dashboard/inbox?conversation=${item.id}`} className="rounded-xl border bg-card p-4"><div className="flex justify-between gap-3"><p className="truncate font-medium">{item.subject||item.customer_id}</p><span className="text-xs uppercase text-muted-foreground">{item.channel}</span></div><div className="mt-2 flex gap-2 text-xs text-muted-foreground"><span>{item.ai_mode}</span>{item.needs_attention?<span className="text-warning">{t("attention")}</span>:null}{item.unread_count?<span>{t("unread",{count:item.unread_count})}</span>:null}</div></Link>)}</div>}</section>
  </div>;
}
