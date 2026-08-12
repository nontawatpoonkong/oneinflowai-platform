"use client";
import { AlertTriangle, CreditCard, Gauge } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { useBilling } from "@/hooks/api/use-billing";

const label=(key:string)=>key.split(".").map((part)=>part[0].toUpperCase()+part.slice(1)).join(" · ");
export function BillingView(){
  const t=useTranslations("billing");const data=useBilling();const queries=Object.values(data);const loading=queries.some((item)=>item.isLoading);const error=queries.some((item)=>item.isError);const subscription=data.subscription.data;
  if(loading)return <div className="grid gap-4 md:grid-cols-2">{[1,2,3,4].map((item)=><div key={item} className="h-36 animate-pulse rounded-2xl bg-muted"/>)}</div>;
  if(error)return <div className="rounded-2xl border border-dashed p-8 text-center"><AlertTriangle className="mx-auto size-8 text-destructive"/><p className="mt-3">{t("error")}</p><Button className="mt-3" variant="outline" onClick={()=>queries.forEach((item)=>item.refetch())}>{t("retry")}</Button></div>;
  return <div className="space-y-7"><header><h1 className="text-2xl font-semibold">{t("title")}</h1><p className="text-sm text-muted-foreground">{t("description")}</p></header>
    <section className="grid gap-4 md:grid-cols-2"><div className="rounded-2xl border bg-card p-5"><CreditCard className="size-5 text-brand"/><p className="mt-3 text-sm text-muted-foreground">{t("currentPlan")}</p><p className="text-2xl font-semibold">{subscription?.plan.display_name??t("noPlan")}</p><p className="mt-2 text-sm">{subscription?.status}</p>{subscription?<p className="text-xs text-muted-foreground">{new Date(subscription.current_period_start).toLocaleDateString()} – {new Date(subscription.current_period_end).toLocaleDateString()}</p>:null}</div><div className="rounded-2xl border bg-card p-5"><Gauge className="size-5 text-brand"/><p className="mt-3 font-medium">{t("checkoutUnavailable")}</p><p className="mt-2 text-sm text-muted-foreground">{t("checkoutExplanation")}</p></div></section>
    <section><h2 className="mb-3 text-lg font-semibold">{t("usage")}</h2><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.usage.data?.filter((item)=>item.enabled).map((item)=><div key={item.key} className="rounded-xl border bg-card p-4"><p className="text-sm font-medium">{label(item.key)}</p><p className="mt-2 text-xl font-semibold">{item.kind==="UNLIMITED"?t("unlimited"):item.used===null?t("notMetered"):`${item.used} / ${item.limit}`}</p>{item.kind==="LIMITED"&&item.remaining!==null?<p className="text-xs text-muted-foreground">{t("remaining",{count:item.remaining})}</p>:null}</div>)}</div></section>
    <section><h2 className="mb-3 text-lg font-semibold">{t("availablePlans")}</h2><p className="mb-3 text-sm text-warning">{t("provisional")}</p><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{data.plans.data?.map((plan)=><article key={plan.id} className="rounded-2xl border bg-card p-5"><h3 className="font-semibold">{plan.display_name}</h3><p className="mt-2 text-sm text-muted-foreground">{plan.pricing_note}</p><p className="mt-4 text-xs">{plan.entitlements.filter((item)=>item.enabled).length} {t("capabilities")}</p></article>)}</div></section>
  </div>;
}
