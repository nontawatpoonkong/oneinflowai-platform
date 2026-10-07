"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { PaginationControls } from "@/components/shared/pagination-controls";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useHotelProperties,
  useHotelStays,
  useStayMutations,
} from "@/hooks/api/use-stays";
import { useMyWorkspace, useWorkspaceMembers } from "@/hooks/api/use-workspace";
import { useAuth } from "@/hooks/use-auth";
import type { StayStatus } from "@/types/stay";

export function StaysView() {
  const t = useTranslations("hotelOperations");
  const common = useTranslations("common");
  const [status, setStatus] = useState<StayStatus>();
  const [propertyId, setPropertyId] = useState("");
  const [arrivalDate, setArrivalDate] = useState("");
  const [departureDate, setDepartureDate] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const properties = useHotelProperties();
  const stays = useHotelStays({
    status,
    property_id: propertyId || undefined,
    arrival_date: arrivalDate || undefined,
    departure_date: departureDate || undefined,
    page,
    page_size: pageSize,
  });
  const mutations = useStayMutations();
  const [bookingId, setBookingId] = useState("");
  const { user } = useAuth();
  const workspace = useMyWorkspace();
  const members = useWorkspaceMembers(workspace.data?.id);
  const role = members.data?.find((item) => item.user_id === user?.id)?.role;
  const canManage = role === "owner" || role === "admin";
  const filter = (update: () => void) => { update(); setPage(1); };

  const create = async () => {
    try {
      await mutations.createStay.mutateAsync(bookingId.trim());
      setBookingId("");
      toast.success(t("saved"));
    } catch {
      toast.error(t("error"));
    }
  };

  return (
    <div className="space-y-6">
      <header><h1 className="text-2xl font-semibold">{t("stays.title")}</h1><p className="text-sm text-muted-foreground">{t("stays.description")}</p></header>
      {canManage ? <div className="flex max-w-xl gap-2"><Input value={bookingId} onChange={(event) => setBookingId(event.target.value)} placeholder={t("bookingId")} /><Button disabled={!bookingId.trim()} onClick={create}>{t("createStay")}</Button></div> : null}
      <section className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        <select aria-label={t("property")} className="h-10 rounded-md border bg-background px-2" value={propertyId} onChange={(event) => filter(() => setPropertyId(event.target.value))}><option value="">{t("allProperties")}</option>{properties.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <select aria-label={t("status")} className="h-10 rounded-md border bg-background px-2" value={status ?? ""} onChange={(event) => filter(() => setStatus((event.target.value || undefined) as StayStatus))}><option value="">{t("allStatuses")}</option>{(["EXPECTED", "CHECKED_IN", "CHECKED_OUT", "NO_SHOW"] as const).map((value) => <option key={value}>{value}</option>)}</select>
        <label className="grid gap-1 text-xs text-muted-foreground">{t("arrivalDate")}<Input type="date" value={arrivalDate} onChange={(event) => filter(() => setArrivalDate(event.target.value))} /></label>
        <label className="grid gap-1 text-xs text-muted-foreground">{t("departureDate")}<Input type="date" value={departureDate} onChange={(event) => filter(() => setDepartureDate(event.target.value))} /></label>
      </section>
      {stays.isLoading ? <Loader2 className="size-6 animate-spin" /> : stays.isError ? <p>{t("error")}</p> : (
        <div className="overflow-x-auto rounded-2xl border bg-card">
          <table className="w-full text-left text-sm"><thead className="border-b bg-muted/40"><tr><th className="p-3">{t("guest")}</th><th className="p-3">{t("property")}</th><th className="p-3">{t("dates")}</th><th className="p-3">{t("roomsLabel")}</th><th className="p-3">{t("status")}</th></tr></thead><tbody>{stays.data?.items.map((stay) => <tr key={stay.id} className="border-b last:border-0"><td className="p-3"><Link className="font-medium text-primary" href={`/dashboard/hotel/stays/${stay.id}`}>{stay.guest_name ?? stay.booking_id}</Link></td><td className="p-3">{stay.property_name}</td><td className="p-3">{stay.planned_check_in_date} → {stay.planned_check_out_date}</td><td className="p-3">{stay.rooms.filter((item) => !item.released_at).map((item) => item.code).join(", ") || "—"}</td><td className="p-3"><Badge variant="outline">{stay.status}</Badge></td></tr>)}</tbody></table>
          {stays.data?.total === 0 ? <p className="p-6 text-center text-muted-foreground">{t("empty")}</p> : null}
          {stays.data ? <PaginationControls page={stays.data.page} pageSize={stays.data.page_size} total={stays.data.total} totalPages={stays.data.total_pages} previousLabel={common("previous")} nextLabel={common("next")} pageSizeLabel={common("pageSize")} summaryLabel={common("pageSummary", { page: stays.data.page, totalPages: stays.data.total_pages, total: stays.data.total })} onPageChange={setPage} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} /> : null}
        </div>
      )}
    </div>
  );
}
