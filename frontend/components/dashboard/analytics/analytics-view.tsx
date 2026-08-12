"use client";

import { AlertTriangle, BarChart3, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useAnalytics } from "@/hooks/api/use-analytics";
import type { AnalyticsCount } from "@/types/analytics";

export function AnalyticsView() {
  const t = useTranslations("analyticsDashboard");
  const [days, setDays] = useState(30);
  const query = useAnalytics(days);
  if (query.isLoading) return <State icon={<Loader2 className="animate-spin" />} text={t("loading")} />;
  if (query.isError) return <State icon={<AlertTriangle />} text={t("error")} retry={() => query.refetch()} />;
  const data = query.data;
  if (!data) return null;
  const noData = data.kpis.conversations === 0 && data.kpis.actions_created === 0 && data.kpis.payments_created === 0;
  return <div className="space-y-6">
    <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><h1 className="text-2xl font-semibold">{t("title")}</h1><p className="text-sm text-muted-foreground">{t("description")}</p></div><div className="flex gap-2">{[7,30,90].map((value)=><Button key={value} variant={days===value?"default":"outline"} size="sm" onClick={()=>setDays(value)}>{t("days",{count:value})}</Button>)}</div></header>
    {noData ? <State icon={<BarChart3 />} text={t("empty")} /> : <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5"><Kpi label={t("conversations")} value={data.kpis.conversations}/><Kpi label={t("customers")} value={data.kpis.unique_customers}/><Kpi label={t("aiHandled")} value={`${data.kpis.ai_handled_rate}%`} help={t("aiHelp")}/><Kpi label={t("actions")} value={data.kpis.actions_created}/><Kpi label={t("verifiedPayments")} value={data.kpis.verified_payments}/></section>
      <section className="grid gap-4 lg:grid-cols-2"><Panel title={t("trend")}><Bars items={data.conversation_trend.map((item)=>({key:item.date,label:item.date.slice(5),count:item.count}))}/></Panel><Panel title={t("channels")}><Bars items={data.conversations_by_channel}/></Panel></section>
      <section className="grid gap-4 lg:grid-cols-3"><Panel title={t("handling")}><dl className="space-y-3"><Metric label={t("aiHandled")} value={`${data.kpis.ai_handled_rate}%`}/><Metric label={t("handoffRate")} value={`${data.kpis.handoff_rate}%`}/><Metric label={t("handoffs")} value={data.kpis.handoffs}/></dl><Bars items={data.handoff_reasons}/></Panel><Panel title={t("actionOutcomes")}><Metric label={t("completionRate")} value={`${data.kpis.action_completion_rate}%`}/><Bars items={data.action_statuses}/><Bars items={data.actions_by_type}/></Panel><Panel title={t("payments")}><Metric label={t("verificationRate")} value={`${data.kpis.payment_verification_rate}%`}/>{data.verified_amounts.map((item)=><Metric key={item.currency} label={item.currency} value={new Intl.NumberFormat(undefined,{style:"currency",currency:item.currency}).format(Number(item.amount))}/>) }<Bars items={data.payment_statuses}/></Panel></section>
      <Panel title={t("currentQueue")} current><div className="grid gap-3 sm:grid-cols-3"><Kpi label={t("openActions")} value={data.current_queue.open_actions}/><Kpi label={t("unassigned")} value={data.current_queue.unassigned_actions}/><Kpi label={t("attention")} value={data.current_queue.conversations_needing_attention}/></div></Panel>
    </>}
  </div>;
}

function Kpi({label,value,help}:{label:string;value:string|number;help?:string}){return <div className="rounded-2xl border bg-card p-4"><p className="text-xs text-muted-foreground" title={help}>{label}</p><p className="mt-2 text-2xl font-semibold">{value}</p>{help?<p className="mt-1 text-xs text-muted-foreground">{help}</p>:null}</div>}
function Panel({title,children,current}:{title:string;children:React.ReactNode;current?:boolean}){return <section className="rounded-2xl border bg-card p-5"><div className="mb-4 flex items-center justify-between"><h2 className="font-semibold">{title}</h2>{current?<span className="rounded-full bg-muted px-2 py-1 text-xs">Current</span>:null}</div>{children}</section>}
function Metric({label,value}:{label:string;value:string|number}){return <div className="flex justify-between gap-4 text-sm"><dt className="text-muted-foreground">{label}</dt><dd className="font-medium">{value}</dd></div>}
function Bars({items}:{items:AnalyticsCount[]}){const max=Math.max(1,...items.map((item)=>item.count));return <div className="space-y-2">{items.map((item)=><div key={item.key} className="grid grid-cols-[90px_1fr_auto] items-center gap-2 text-xs"><span className="truncate">{item.label||item.key}</span><div className="h-2 rounded-full bg-muted"><div className="h-2 rounded-full bg-primary" style={{width:`${item.count*100/max}%`}}/></div><span>{item.count}</span></div>)}</div>}
function State({icon,text,retry}:{icon:React.ReactNode;text:string;retry?:()=>unknown}){return <div className="grid min-h-64 place-items-center rounded-2xl border border-dashed p-8 text-center"><div>{icon}<p className="mt-3 text-sm text-muted-foreground">{text}</p>{retry?<Button className="mt-3" variant="outline" onClick={retry}>Retry</Button>:null}</div></div>}
