"use client";

import { CalendarDays, ChevronLeft, ChevronRight, Loader2, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAvailabilityCalendar } from "@/hooks/api/use-hotel-catalog";
import { useHotelProperties } from "@/hooks/api/use-stays";
import { cn } from "@/lib/utils";
import type { AvailabilityCell } from "@/types/hotel-catalog";

const color: Record<string, string> = {
  GREEN: "border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-700 dark:bg-emerald-950/35 dark:text-emerald-100",
  YELLOW: "border-yellow-300 bg-yellow-50 text-yellow-950 dark:border-yellow-700 dark:bg-yellow-950/35 dark:text-yellow-100",
  ORANGE: "border-orange-300 bg-orange-50 text-orange-950 dark:border-orange-700 dark:bg-orange-950/35 dark:text-orange-100",
  RED: "border-red-300 bg-red-50 text-red-950 dark:border-red-700 dark:bg-red-950/35 dark:text-red-100",
};

function isoToday() { return new Date().toISOString().slice(0, 10); }
function shift(value: string, days: number) { const date = new Date(`${value}T00:00:00Z`); date.setUTCDate(date.getUTCDate() + days); return date.toISOString().slice(0, 10); }

export function AvailabilityCalendarView() {
  const t = useTranslations("hotelCatalog");
  const properties = useHotelProperties();
  const [propertyId, setPropertyId] = useState("");
  const [startDate, setStartDate] = useState(isoToday);
  const [days, setDays] = useState<7 | 14 | 30>(7);
  const [selected, setSelected] = useState<{ room: string; cell: AvailabilityCell }>();
  const calendar = useAvailabilityCalendar(propertyId, startDate, days);
  const dates = useMemo(() => calendar.data?.rows[0]?.cells.map((cell) => cell.date) ?? [], [calendar.data]);

  return <div className="space-y-6">
    <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div><div className="mb-2 flex size-10 items-center justify-center rounded-xl bg-cyan-400/15 text-cyan-600"><CalendarDays /></div><h1 className="text-2xl font-semibold">{t("availability.title")}</h1><p className="text-sm text-muted-foreground">{t("availability.description")}</p></div>
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label={t("property")} className="h-10 min-w-48 rounded-md border bg-background px-3" value={propertyId} onChange={(event) => setPropertyId(event.target.value)}><option value="">{t("selectProperty")}</option>{properties.data?.map((property) => <option key={property.id} value={property.id}>{property.name}</option>)}</select>
        <Button variant="outline" size="icon" aria-label={t("previousRange")} onClick={() => setStartDate(shift(startDate, -days))}><ChevronLeft /></Button>
        <input aria-label={t("startDate")} className="h-10 rounded-md border bg-background px-3" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        <Button variant="outline" size="icon" aria-label={t("nextRange")} onClick={() => setStartDate(shift(startDate, days))}><ChevronRight /></Button>
        {[7, 14, 30].map((value) => <Button key={value} size="sm" variant={days === value ? "default" : "outline"} onClick={() => setDays(value as 7 | 14 | 30)}>{t("days", { count: value })}</Button>)}
      </div>
    </header>

    {!propertyId ? <Card><CardContent className="p-10 text-center text-muted-foreground">{t("availability.selectPropertyEmpty")}</CardContent></Card> : calendar.isLoading ? <Loader2 className="size-6 animate-spin" aria-label={t("loading")} /> : calendar.isError ? <Card><CardContent className="p-8 text-center text-destructive">{t("loadError")}</CardContent></Card> : !calendar.data?.rows.length ? <Card><CardContent className="p-10 text-center text-muted-foreground">{t("availability.empty")}</CardContent></Card> : <>
      <div className="hidden overflow-x-auto rounded-xl border bg-card md:block">
        <table className="min-w-max border-collapse text-sm"><thead><tr><th className="sticky left-0 z-20 min-w-56 border-b border-r bg-card p-3 text-left">{t("roomType")}</th>{dates.map((day) => <th key={day} className="min-w-28 border-b p-3 text-center font-medium">{new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" }).format(new Date(`${day}T00:00:00Z`))}</th>)}</tr></thead><tbody>{calendar.data.rows.map((row) => <tr key={row.room_type_id}><th className="sticky left-0 z-10 border-r bg-card p-3 text-left font-medium">{row.room_type_name}</th>{row.cells.map((cell) => <td key={cell.date} className="p-1.5"><button type="button" onClick={() => setSelected({ room: row.room_type_name, cell })} className={cn("w-full rounded-lg border p-2 text-center transition-transform hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500", cell.has_inventory ? color[cell.color_bucket] : "border-dashed bg-muted/35 text-muted-foreground")} aria-label={`${row.room_type_name}, ${cell.date}, ${cell.used_units} / ${cell.total_units} ${t("used")}`}><strong>{cell.used_units} / {cell.total_units}</strong><span className="mt-1 block text-[11px]">{cell.has_inventory ? t("used") : t("noInventory")}</span>{cell.authority === "PMS" ? <span className="mt-1 block text-[10px] font-semibold">PMS</span> : null}</button></td>)}</tr>)}</tbody></table>
      </div>
      <div className="space-y-4 md:hidden">{calendar.data.rows.map((row) => <Card key={row.room_type_id}><CardHeader><CardTitle>{row.room_type_name}</CardTitle></CardHeader><CardContent className="flex snap-x gap-2 overflow-x-auto pb-4">{row.cells.map((cell) => <button key={cell.date} type="button" onClick={() => setSelected({ room: row.room_type_name, cell })} className={cn("min-w-28 snap-start rounded-lg border p-3 text-left", cell.has_inventory ? color[cell.color_bucket] : "border-dashed bg-muted/35")}><span className="text-xs">{cell.date.slice(5)}</span><strong className="mt-2 block">{cell.used_units} / {cell.total_units}</strong><span className="text-[11px]">{cell.authority}</span></button>)}</CardContent></Card>)}</div>
    </>}

    {selected ? <div role="dialog" aria-modal="true" aria-labelledby="availability-detail-title" className="fixed inset-0 z-50 flex justify-end bg-black/35" onClick={() => setSelected(undefined)}><aside className="h-full w-full max-w-md bg-background p-6 shadow-2xl" onClick={(event) => event.stopPropagation()}><div className="flex items-start justify-between"><div><p className="text-sm text-muted-foreground">{selected.cell.date}</p><h2 id="availability-detail-title" className="text-xl font-semibold">{selected.room}</h2></div><Button size="icon" variant="ghost" aria-label={t("close")} onClick={() => setSelected(undefined)}><X /></Button></div><dl className="mt-8 grid grid-cols-2 gap-4">{[[t("total"), selected.cell.total_units], [t("reserved"), selected.cell.reserved_units], [t("blocked"), selected.cell.blocked_units], [t("available"), selected.cell.available_units]].map(([label, value]) => <div key={String(label)} className="rounded-lg border p-4"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-2xl font-semibold">{value}</dd></div>)}</dl><div className="mt-6 rounded-lg border p-4"><p className="text-xs text-muted-foreground">{t("authority")}</p><p className="font-medium">{selected.cell.authority === "PMS" ? t("syncedFromPms") : t("localAuthority")}</p></div></aside></div> : null}
  </div>;
}
