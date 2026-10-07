"use client";

import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { PaginationControls } from "@/components/shared/pagination-controls";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useHousekeepingMutations } from "@/hooks/api/use-housekeeping";
import {
  useHotelProperties,
  useHotelRooms,
  useHotelRoomTypes,
  useStayMutations,
} from "@/hooks/api/use-stays";
import { useMyWorkspace, useWorkspaceMembers } from "@/hooks/api/use-workspace";
import { useAuth } from "@/hooks/use-auth";
import type { RoomOperationalStatus, RoomReadinessStatus } from "@/types/stay";

export function RoomsView() {
  const t = useTranslations("hotelOperations");
  const common = useTranslations("common");
  const { user } = useAuth();
  const workspace = useMyWorkspace();
  const members = useWorkspaceMembers(workspace.data?.id);
  const role = members.data?.find((item) => item.user_id === user?.id)?.role;
  const canManage = role === "owner" || role === "admin";
  const properties = useHotelProperties();
  const [propertyId, setPropertyId] = useState("");
  const roomTypes = useHotelRoomTypes(propertyId || undefined);
  const [roomTypeFilter, setRoomTypeFilter] = useState("");
  const [occupancy, setOccupancy] = useState<RoomOperationalStatus>();
  const [readiness, setReadiness] = useState<RoomReadinessStatus>();
  const [active, setActive] = useState<"" | "true" | "false">("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const rooms = useHotelRooms({
    property_id: propertyId || undefined,
    room_type_id: roomTypeFilter || undefined,
    operational_status: occupancy,
    readiness_status: readiness,
    active: active === "" ? undefined : active === "true",
    page,
    page_size: pageSize,
  });
  const mutations = useStayMutations();
  const housekeeping = useHousekeepingMutations();
  const [roomTypeId, setRoomTypeId] = useState("");
  const [code, setCode] = useState("");
  const [floor, setFloor] = useState("");
  const types = useMemo(
    () => roomTypes.data?.filter((item) => !propertyId || item.property_id === propertyId) ?? [],
    [roomTypes.data, propertyId],
  );
  const filter = (update: () => void) => { update(); setPage(1); };

  const create = async () => {
    try {
      await mutations.createRoom.mutateAsync({
        property_id: propertyId,
        room_type_id: roomTypeId,
        code: code.trim(),
        floor: floor.trim() || undefined,
      });
      setCode("");
      setFloor("");
      toast.success(t("saved"));
    } catch {
      toast.error(t("error"));
    }
  };

  const overrideReadiness = async (roomId: string, current: RoomReadinessStatus) => {
    const reason = window.prompt(t("overrideReasonPrompt"));
    if (!reason) return;
    try {
      await housekeeping.overrideReadiness.mutateAsync({
        id: roomId,
        status: current === "READY" ? "DIRTY" : "READY",
        reason,
      });
      toast.success(t("saved"));
    } catch {
      toast.error(t("error"));
    }
  };

  return (
    <div className="space-y-6">
      <header><h1 className="text-2xl font-semibold">{t("rooms.title")}</h1><p className="text-sm text-muted-foreground">{t("rooms.description")}</p></header>
      {canManage ? (
        <section className="grid gap-2 rounded-2xl border bg-card p-4 md:grid-cols-5">
          <select className="h-10 rounded-md border bg-background px-2" value={propertyId} onChange={(event) => { setPropertyId(event.target.value); setRoomTypeId(""); setRoomTypeFilter(""); setPage(1); }}><option value="">{t("selectProperty")}</option>{properties.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          <select className="h-10 rounded-md border bg-background px-2" value={roomTypeId} onChange={(event) => setRoomTypeId(event.target.value)}><option value="">{t("selectRoomType")}</option>{types.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          <Input value={code} onChange={(event) => setCode(event.target.value)} placeholder={t("roomCode")} />
          <Input value={floor} onChange={(event) => setFloor(event.target.value)} placeholder={t("floor")} />
          <Button disabled={!propertyId || !roomTypeId || !code.trim() || mutations.createRoom.isPending} onClick={create}>{t("createRoom")}</Button>
        </section>
      ) : null}
      <section className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
        <select aria-label={t("property")} className="h-10 rounded-md border bg-background px-2" value={propertyId} onChange={(event) => { setPropertyId(event.target.value); setRoomTypeFilter(""); setPage(1); }}><option value="">{t("allProperties")}</option>{properties.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <select aria-label={t("roomType")} className="h-10 rounded-md border bg-background px-2" value={roomTypeFilter} onChange={(event) => filter(() => setRoomTypeFilter(event.target.value))}><option value="">{t("allRoomTypes")}</option>{types.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <select aria-label={t("occupancy")} className="h-10 rounded-md border bg-background px-2" value={occupancy ?? ""} onChange={(event) => filter(() => setOccupancy((event.target.value || undefined) as RoomOperationalStatus))}><option value="">{t("allOccupancy")}</option>{(["AVAILABLE", "OCCUPIED", "OUT_OF_SERVICE"] as const).map((value) => <option key={value}>{value}</option>)}</select>
        <select aria-label={t("readiness")} className="h-10 rounded-md border bg-background px-2" value={readiness ?? ""} onChange={(event) => filter(() => setReadiness((event.target.value || undefined) as RoomReadinessStatus))}><option value="">{t("allReadiness")}</option>{(["READY", "DIRTY", "CLEANING"] as const).map((value) => <option key={value}>{value}</option>)}</select>
        <select aria-label={t("activeFilter")} className="h-10 rounded-md border bg-background px-2" value={active} onChange={(event) => filter(() => setActive(event.target.value as "" | "true" | "false"))}><option value="">{t("allActivity")}</option><option value="true">{t("active")}</option><option value="false">{t("inactive")}</option></select>
      </section>
      {rooms.isLoading ? <Loader2 className="size-6 animate-spin" /> : rooms.isError ? <p>{t("error")}</p> : (
        <div className="overflow-x-auto rounded-2xl border bg-card">
          <table className="w-full text-left text-sm"><thead className="border-b bg-muted/40"><tr><th className="p-3">{t("roomCode")}</th><th className="p-3">{t("property")}</th><th className="p-3">{t("roomType")}</th><th className="p-3">{t("occupancy")}</th><th className="p-3">{t("readiness")}</th><th className="p-3">{t("actions")}</th></tr></thead><tbody>{rooms.data?.items.map((room) => <tr key={room.id} className="border-b last:border-0"><td className="p-3 font-medium">{room.code}</td><td className="p-3">{room.property_name}</td><td className="p-3">{room.room_type_name}</td><td className="p-3"><Badge variant="outline">{room.operational_status}</Badge></td><td className="p-3"><Badge variant="muted">{room.readiness_status}</Badge></td><td className="p-3"><div className="flex flex-wrap gap-2">{canManage && room.operational_status !== "OCCUPIED" ? <><Button size="sm" variant="outline" onClick={() => mutations.roomStatus.mutate({ id: room.id, status: room.operational_status === "OUT_OF_SERVICE" ? "available" : "out-of-service" })}>{room.operational_status === "OUT_OF_SERVICE" ? t("makeAvailable") : t("outOfService")}</Button><Button size="sm" variant="outline" onClick={() => overrideReadiness(room.id, room.readiness_status)}>{room.readiness_status === "READY" ? t("overrideDirty") : t("overrideReady")}</Button></> : "—"}</div></td></tr>)}</tbody></table>
          {rooms.data?.total === 0 ? <p className="p-6 text-center text-muted-foreground">{t("empty")}</p> : null}
          {rooms.data ? <PaginationControls page={rooms.data.page} pageSize={rooms.data.page_size} total={rooms.data.total} totalPages={rooms.data.total_pages} previousLabel={common("previous")} nextLabel={common("next")} pageSizeLabel={common("pageSize")} summaryLabel={common("pageSummary", { page: rooms.data.page, totalPages: rooms.data.total_pages, total: rooms.data.total })} onPageChange={setPage} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} /> : null}
        </div>
      )}
    </div>
  );
}
