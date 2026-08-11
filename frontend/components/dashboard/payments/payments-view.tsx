"use client";

import { AlertTriangle, CreditCard, Loader2, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { usePaymentDestinations, usePayments } from "@/hooks/api/use-payments";

export function PaymentsView() {
  const t = useTranslations("operations.payments");
  const params = useSearchParams();
  const payments = usePayments();
  const destinations = usePaymentDestinations();
  const [selected, setSelected] = useState<string | null>(params.get("payment"));
  const item = payments.data?.find((payment) => payment.id === selected);

  if (payments.isLoading) return <State icon={Loader2} text={t("loading")} spin />;
  if (payments.isError) return <State icon={AlertTriangle} text={t("error")} action={() => payments.refetch()} />;

  return <div className="space-y-6">
    <header><h1 className="text-2xl font-semibold">{t("title")}</h1><p className="text-sm text-muted-foreground">{t("description")}</p></header>
    {!payments.data?.length ? <State icon={CreditCard} text={t("empty")} /> : <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="overflow-x-auto rounded-2xl border bg-card"><table className="w-full text-left text-sm"><thead className="border-b bg-muted/40"><tr>{["reference","expected","verified","status","created"].map((key) => <th key={key} className="p-3">{t(key)}</th>)}</tr></thead><tbody>{payments.data.map((payment) => <tr key={payment.id} onClick={() => setSelected(payment.id)} className="cursor-pointer border-b hover:bg-muted/30"><td className="p-3">{payment.reference || payment.id.slice(0,8)}</td><td className="p-3">{money(payment.expected_amount,payment.currency)}</td><td className="p-3">{payment.verified_amount ? money(payment.verified_amount,payment.currency) : "—"}</td><td className="p-3"><Badge variant="muted">{payment.status}</Badge></td><td className="p-3">{new Date(payment.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>
      {item ? <aside className="rounded-2xl border bg-card p-5"><h2 className="font-semibold">{t("detail")}</h2><dl className="mt-4 space-y-3 text-sm"><Row label={t("status")} value={item.status}/><Row label={t("destination")} value={destinations.data?.find((d) => d.id === item.payment_destination_id)?.display_name ?? "—"}/><Row label={t("expected")} value={money(item.expected_amount,item.currency)}/><Row label={t("verified")} value={item.verified_amount ? money(item.verified_amount,item.currency) : "—"}/><Row label={t("paidAt")} value={date(item.paid_at)}/><Row label={t("verifiedAt")} value={date(item.verified_at)}/></dl><p className="mt-5 rounded-xl bg-warning/10 p-3 text-xs text-muted-foreground">{t("providerNotice")}</p></aside> : null}
    </div>}
  </div>;
}

const money=(value:string,currency:string)=>new Intl.NumberFormat(undefined,{style:"currency",currency}).format(Number(value));
const date=(value:string|null)=>value?new Date(value).toLocaleString():"—";
function Row({label,value}:{label:string;value:string}){return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd>{value}</dd></div>}
function State({icon:Icon,text,action,spin}:{icon:LucideIcon;text:string;action?:()=>unknown;spin?:boolean}){const common=useTranslations("common");return <div className="grid min-h-64 place-items-center rounded-2xl border border-dashed p-8 text-center"><div><Icon className={`mx-auto mb-3 size-8 text-muted-foreground ${spin?"animate-spin":""}`}/><p className="text-sm text-muted-foreground">{text}</p>{action?<Button className="mt-3" variant="outline" size="sm" onClick={action}>{common("tryAgain")}</Button>:null}</div></div>}
