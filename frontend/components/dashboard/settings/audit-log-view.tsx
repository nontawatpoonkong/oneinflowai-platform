"use client";

import { AlertTriangle, ChevronLeft, ChevronRight, Filter, Loader2, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuditEvents } from "@/hooks/api/use-audit";
import type { AuditEvent } from "@/types/audit";

const AREAS = [
  "WORKSPACE", "TEAM", "BOOKINGS", "PAYMENTS", "ROOMS", "STAYS",
  "HOUSEKEEPING", "KNOWLEDGE", "AUTOMATIONS", "PMS", "AI_ACTIONS",
] as const;

export function AuditLogView() {
  const t = useTranslations("auditLog");
  const [page, setPage] = useState(1);
  const [area, setArea] = useState("");
  const [result, setResult] = useState("");
  const [search, setSearch] = useState("");
  const [action, setAction] = useState("");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const filters = useMemo(
    () => ({
      page,
      page_size: 50,
      ...(area ? { area } : {}),
      ...(result ? { result } : {}),
      ...(action.trim() ? { action: action.trim() } : {}),
      ...(search.trim().length >= 2 ? { search: search.trim() } : {}),
      ...(startAt ? { start_at: new Date(`${startAt}T00:00:00Z`).toISOString() } : {}),
      ...(endAt ? { end_at: new Date(`${endAt}T23:59:59Z`).toISOString() } : {}),
    }),
    [action, area, endAt, page, result, search, startAt],
  );
  const query = useAuditEvents(filters);

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-600 dark:text-cyan-300">{t("eyebrow")}</p>
        <h1 className="mt-2 text-2xl font-semibold">{t("title")}</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("description")}</p>
      </header>

      <section className="rounded-xl border border-cyan-500/20 bg-card">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3 text-sm font-medium"><Filter className="size-4 text-cyan-500" />{t("filters")}</div>
        <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
          <Input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder={t("search")} aria-label={t("search")} />
          <Input value={action} onChange={(event) => { setAction(event.target.value); setPage(1); }} placeholder={t("actionFilter")} aria-label={t("actionFilter")} />
          <select className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={area} onChange={(event) => { setArea(event.target.value); setPage(1); }} aria-label={t("area")}>
            <option value="">{t("allAreas")}</option>
            {AREAS.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={result} onChange={(event) => { setResult(event.target.value); setPage(1); }} aria-label={t("result")}>
            <option value="">{t("allResults")}</option>
            {(["SUCCESS", "DENIED", "FAILED"] as const).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <Input type="date" value={startAt} onChange={(event) => { setStartAt(event.target.value); setPage(1); }} aria-label={t("startDate")} />
          <Input type="date" value={endAt} onChange={(event) => { setEndAt(event.target.value); setPage(1); }} aria-label={t("endDate")} />
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border border-border bg-card">
        {query.isLoading ? <State icon={<Loader2 className="animate-spin" />} text={t("loading")} /> : query.isError ? <State icon={<AlertTriangle />} text={t("error")} retry={() => query.refetch()} /> : !query.data?.items.length ? <State icon={<Filter />} text={t("empty")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[840px] text-left text-sm">
              <thead className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="px-4 py-3">{t("time")}</th><th className="px-4 py-3">{t("actor")}</th><th className="px-4 py-3">{t("action")}</th><th className="px-4 py-3">{t("area")}</th><th className="px-4 py-3">{t("resource")}</th><th className="px-4 py-3">{t("result")}</th></tr></thead>
              <tbody className="divide-y divide-border">{query.data.items.map((item) => <tr key={item.id} className="cursor-pointer transition-colors hover:bg-cyan-500/5" onClick={() => setSelected(item)}><td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{new Date(item.occurred_at).toLocaleString()}</td><td className="px-4 py-3"><p className="font-medium">{item.actor.name}</p><p className="text-xs text-muted-foreground">{item.actor.type}</p></td><td className="px-4 py-3 font-medium">{item.action}</td><td className="px-4 py-3">{item.area}</td><td className="px-4 py-3"><p>{item.resource_type}</p>{item.resource_id ? <p className="max-w-36 truncate font-mono text-xs text-muted-foreground">{item.resource_id}</p> : null}</td><td className="px-4 py-3"><ResultBadge value={item.result} /></td></tr>)}</tbody>
            </table>
          </div>
        )}
        <div className="flex items-center justify-between border-t border-border px-4 py-3 text-sm text-muted-foreground"><span>{t("total", { count: query.data?.total ?? 0 })}</span><div className="flex items-center gap-2"><Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage((value) => value - 1)} aria-label={t("previous")}><ChevronLeft /></Button><span>{t("page", { page, pages: query.data?.pages ?? 0 })}</span><Button variant="outline" size="sm" disabled={!query.data || page >= query.data.pages} onClick={() => setPage((value) => value + 1)} aria-label={t("next")}><ChevronRight /></Button></div></div>
      </section>

      {selected ? <AuditDrawer event={selected} close={() => setSelected(null)} /> : null}
    </div>
  );
}

function ResultBadge({ value }: { value: AuditEvent["result"] }) {
  const style = value === "SUCCESS" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : value === "DENIED" ? "bg-amber-500/10 text-amber-700 dark:text-amber-300" : "bg-rose-500/10 text-rose-700 dark:text-rose-300";
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${style}`}>{value}</span>;
}

function AuditDrawer({ event, close }: { event: AuditEvent; close: () => void }) {
  const t = useTranslations("auditLog");
  return <div className="fixed inset-0 z-50 flex justify-end bg-black/35" role="dialog" aria-modal="true" aria-label={t("detail")} onClick={close}><aside className="h-full w-full max-w-lg overflow-y-auto border-l border-pink-500/30 bg-background p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}><div className="flex items-start justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-pink-500">{event.area}</p><h2 className="mt-2 text-xl font-semibold">{event.action}</h2></div><Button variant="ghost" size="icon" onClick={close} aria-label={t("close")}><X /></Button></div><dl className="mt-6 grid gap-4 text-sm"><Detail label={t("time")} value={new Date(event.occurred_at).toLocaleString()} /><Detail label={t("actor")} value={`${event.actor.name} · ${event.actor.type}`} /><Detail label={t("resource")} value={`${event.resource_type}${event.resource_id ? ` · ${event.resource_id}` : ""}`} /><Detail label={t("result")} value={event.result} /><Detail label={t("operation")} value={[event.request_method, event.route].filter(Boolean).join(" ") || "—"} /><Detail label={t("correlation")} value={event.correlation_id || "—"} /></dl>{Object.keys(event.safe_metadata).length ? <div className="mt-6"><h3 className="text-sm font-semibold">{t("safeMetadata")}</h3><dl className="mt-3 divide-y divide-border rounded-lg border border-border">{Object.entries(event.safe_metadata).map(([key, value]) => <div key={key} className="grid grid-cols-[minmax(120px,0.8fr)_1.2fr] gap-3 px-3 py-2 text-sm"><dt className="text-muted-foreground">{key}</dt><dd className="break-words font-medium">{String(value)}</dd></div>)}</dl></div> : null}</aside></div>;
}

function Detail({ label, value }: { label: string; value: string }) { return <div><dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-1 break-words font-medium">{value}</dd></div>; }
function State({ icon, text, retry }: { icon: React.ReactNode; text: string; retry?: () => unknown }) { return <div className="grid min-h-64 place-items-center p-8 text-center"><div className="flex flex-col items-center text-muted-foreground">{icon}<p className="mt-3 text-sm">{text}</p>{retry ? <Button className="mt-3" variant="outline" onClick={retry}>{text}</Button> : null}</div></div>; }
