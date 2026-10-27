"use client";

import { ArrowLeft, ArrowRight, BedDouble, ImagePlus, Loader2, Pencil, Plus, Star, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAmenityRegistry, useHotelCatalogMutations, useRoomCatalogDetail } from "@/hooks/api/use-hotel-catalog";
import { useHotelProperties, useHotelRoomTypes } from "@/hooks/api/use-stays";
import { useMyWorkspace, useWorkspaceAccess } from "@/hooks/api/use-workspace";
import { hotelCatalogService } from "@/services/hotel/catalog.service";
import type { AmenityDefinition, RichRoomTypePayload, RoomCatalogDetail, RoomTypeAmenity, RoomTypeBed, RoomTypeImage } from "@/types/hotel-catalog";

const baseForm: RichRoomTypePayload = {
  property_id: "", code: "", name: "", short_description: "", description: "",
  max_adults: 2, max_children: 0, max_occupancy: 2, base_capacity: 2,
  smoking_policy: "NON_SMOKING", accessibility_available: false,
  public_highlights: "", view_type: "NO_SPECIAL_VIEW", active: true,
  beds: [{ bed_type: "KING", quantity: 1, sort_order: 0 }], amenities: [], physical_rooms: [],
};

function AuthenticatedImage({ image }: { image: RoomTypeImage }) {
  const [src, setSrc] = useState<string>();
  useEffect(() => { let active = true; let url = ""; hotelCatalogService.imageBlob(image).then((blob) => { url = URL.createObjectURL(blob); if (active) setSrc(url); }).catch(() => undefined); return () => { active = false; if (url) URL.revokeObjectURL(url); }; }, [image]);
  return src ? <div className="relative h-full w-full"><Image src={src} alt={image.alt_text} fill unoptimized className="object-cover" /></div> : <div className="flex h-full items-center justify-center bg-gradient-to-br from-cyan-500/20 to-pink-500/20 text-xs text-muted-foreground">{image.alt_text}</div>;
}

function valueFor(definition: AmenityDefinition, selected: Map<string, RoomTypeAmenity>) {
  const value = selected.get(definition.code);
  if (!value) return "";
  if (definition.value_type === "NUMBER") return value.number_value ?? "";
  if (definition.value_type === "TEXT") return value.text_value ?? "";
  return value.boolean_value ? "true" : "";
}

function RoomTypeForm({ existing, onDone }: { existing?: RoomCatalogDetail; onDone: () => void }) {
  const t = useTranslations("hotelCatalog");
  const locale = useLocale();
  const properties = useHotelProperties();
  const registry = useAmenityRegistry();
  const mutations = useHotelCatalogMutations();
  const [form, setForm] = useState<RichRoomTypePayload>(() => existing ? {
    ...baseForm, ...existing.room_type, room_size_sqm: existing.room_type.room_size_sqm ? Number(existing.room_type.room_size_sqm) : undefined,
    short_description: existing.room_type.short_description ?? "",
    description: existing.room_type.description ?? "",
    public_highlights: existing.room_type.public_highlights ?? "",
    custom_view_label: existing.room_type.custom_view_label ?? undefined,
    beds: existing.beds.map((bed) => ({ bed_type: bed.bed_type, quantity: bed.quantity, custom_label: bed.custom_label, width_cm: bed.width_cm, length_cm: bed.length_cm, sort_order: bed.sort_order })),
    amenities: existing.amenities.map((amenity) => ({ code: amenity.code, boolean_value: amenity.boolean_value, number_value: amenity.number_value, text_value: amenity.text_value })), physical_rooms: [],
  } : { ...baseForm });
  const [roomCodes, setRoomCodes] = useState("");
  const selected = useMemo(() => new Map(form.amenities.map((item) => [item.code, item])), [form.amenities]);
  const groups = useMemo(() => Object.entries((registry.data ?? []).reduce<Record<string, AmenityDefinition[]>>((result, item) => { (result[item.category] ??= []).push(item); return result; }, {})), [registry.data]);
  const set = <K extends keyof RichRoomTypePayload>(key: K, value: RichRoomTypePayload[K]) => setForm((current) => ({ ...current, [key]: value }));
  const setAmenity = (definition: AmenityDefinition, raw: string | boolean) => {
    const rest = form.amenities.filter((item) => item.code !== definition.code);
    if (raw === "" || raw === false) return set("amenities", rest);
    const item: RoomTypeAmenity = definition.value_type === "BOOLEAN" ? { code: definition.code, boolean_value: true } : definition.value_type === "NUMBER" ? { code: definition.code, number_value: String(raw) } : { code: definition.code, text_value: String(raw) };
    set("amenities", [...rest, item]);
  };
  const submit = async () => {
    try {
      if (existing) {
        const { beds, amenities } = form;
        const metadata = {
          name: form.name, short_description: form.short_description,
          description: form.description, room_size_sqm: form.room_size_sqm,
          max_adults: form.max_adults, max_children: form.max_children,
          max_occupancy: form.max_occupancy, base_capacity: form.base_capacity,
          smoking_policy: form.smoking_policy,
          accessibility_available: form.accessibility_available,
          public_highlights: form.public_highlights, view_type: form.view_type,
          custom_view_label: form.custom_view_label, active: form.active,
        };
        await mutations.update.mutateAsync({ id: existing.room_type.id, payload: metadata });
        await mutations.beds.mutateAsync({ id: existing.room_type.id, payload: beds });
        await mutations.amenities.mutateAsync({ id: existing.room_type.id, payload: amenities });
      } else {
        const physical_rooms = roomCodes.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => { const [code, floor, building, wing] = line.split(",").map((part) => part.trim()); return { code, floor: floor || undefined, building: building || undefined, wing: wing || undefined }; });
        await mutations.create.mutateAsync({ ...form, physical_rooms });
      }
      toast.success(t("saved")); onDone();
    } catch { toast.error(t("saveError")); }
  };
  const pending = mutations.create.isPending || mutations.update.isPending || mutations.beds.isPending || mutations.amenities.isPending;
  return <Card className="border-cyan-500/30"><CardHeader><CardTitle>{existing ? t("editRoomType") : t("createRoomType")}</CardTitle><CardDescription>{t("formDescription")}</CardDescription></CardHeader><CardContent className="space-y-4">
    <details open className="rounded-lg border p-4"><summary className="cursor-pointer font-semibold">1. {t("sections.basic")}</summary><div className="mt-4 grid gap-3 md:grid-cols-2"><label className="text-sm">{t("property")}<select disabled={Boolean(existing)} className="mt-1 h-10 w-full rounded-md border bg-background px-2" value={form.property_id} onChange={(event) => set("property_id", event.target.value)}><option value="">{t("selectProperty")}</option>{properties.data?.map((property) => <option key={property.id} value={property.id}>{property.name}</option>)}</select></label><label className="text-sm">{t("code")}<Input disabled={Boolean(existing)} className="mt-1" value={form.code} onChange={(event) => set("code", event.target.value.toUpperCase())} /></label><label className="text-sm md:col-span-2">{t("name")}<Input className="mt-1" value={form.name} onChange={(event) => set("name", event.target.value)} /></label><label className="text-sm md:col-span-2">{t("shortDescription")}<Input className="mt-1" value={form.short_description ?? ""} onChange={(event) => set("short_description", event.target.value)} /></label><label className="text-sm md:col-span-2">{t("description")}<textarea className="mt-1 min-h-24 w-full rounded-md border bg-background p-3" value={form.description ?? ""} onChange={(event) => set("description", event.target.value)} /></label></div></details>
    <details className="rounded-lg border p-4"><summary className="cursor-pointer font-semibold">2. {t("sections.capacity")}</summary><div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[["maxAdults", "max_adults"], ["maxChildren", "max_children"], ["maxOccupancy", "max_occupancy"], ["baseCapacity", "base_capacity"]].map(([label, key]) => <label key={key} className="text-sm">{t(label)}<Input className="mt-1" type="number" min={key === "max_children" ? 0 : 1} value={Number(form[key as keyof RichRoomTypePayload])} onChange={(event) => set(key as "max_adults", Number(event.target.value))} /></label>)}<label className="text-sm">{t("roomSize")}<Input className="mt-1" type="number" min="1" step="0.01" value={form.room_size_sqm ?? ""} onChange={(event) => set("room_size_sqm", event.target.value ? Number(event.target.value) : undefined)} /></label></div></details>
    <details className="rounded-lg border p-4"><summary className="cursor-pointer font-semibold">3. {t("sections.beds")}</summary><div className="mt-4 space-y-2">{form.beds.map((bed, index) => <div key={index} className="grid gap-2 sm:grid-cols-[1fr_120px_auto]"><select className="h-10 rounded-md border bg-background px-2" value={bed.bed_type} onChange={(event) => set("beds", form.beds.map((item, itemIndex) => itemIndex === index ? { ...item, bed_type: event.target.value as RoomTypeBed["bed_type"] } : item))}>{["KING", "QUEEN", "DOUBLE", "TWIN", "SINGLE", "BUNK", "SOFA_BED", "FUTON", "OTHER"].map((type) => <option key={type}>{type.replaceAll("_", " ")}</option>)}</select><Input type="number" min="1" value={bed.quantity} onChange={(event) => set("beds", form.beds.map((item, itemIndex) => itemIndex === index ? { ...item, quantity: Number(event.target.value) } : item))} /><Button size="icon" variant="ghost" aria-label={t("remove")} onClick={() => set("beds", form.beds.filter((_, itemIndex) => itemIndex !== index).map((item, sort_order) => ({ ...item, sort_order })))}><X /></Button></div>)}<Button size="sm" variant="outline" onClick={() => set("beds", [...form.beds, { bed_type: "TWIN", quantity: 1, sort_order: form.beds.length }])}><Plus />{t("addBed")}</Button></div></details>
    <details className="rounded-lg border p-4"><summary className="cursor-pointer font-semibold">4. {t("sections.view")}</summary><div className="mt-4 grid gap-3 md:grid-cols-2"><label className="text-sm">{t("view")}<select className="mt-1 h-10 w-full rounded-md border bg-background px-2" value={form.view_type} onChange={(event) => set("view_type", event.target.value)}>{["CITY", "GARDEN", "POOL", "MOUNTAIN", "SEA", "RIVER", "COURTYARD", "NO_SPECIAL_VIEW", "CUSTOM"].map((view) => <option key={view}>{view.replaceAll("_", " ")}</option>)}</select></label>{form.view_type === "CUSTOM" ? <label className="text-sm">{t("customView")}<Input className="mt-1" value={form.custom_view_label ?? ""} onChange={(event) => set("custom_view_label", event.target.value)} /></label> : null}</div></details>
    <details className="rounded-lg border p-4"><summary className="cursor-pointer font-semibold">5. {t("sections.amenities")}</summary><div className="mt-4 space-y-5">{groups.map(([category, items]) => <fieldset key={category}><legend className="mb-2 font-medium">{t.has(`categories.${category}`) ? t(`categories.${category}`) : category.replaceAll("_", " ")}</legend><div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">{items?.map((definition) => <label key={definition.code} className="flex min-h-11 items-center gap-3 rounded-lg border p-3 text-sm">{definition.value_type === "BOOLEAN" ? <input type="checkbox" checked={selected.has(definition.code)} onChange={(event) => setAmenity(definition, event.target.checked)} /> : <input className="h-8 w-24 rounded border bg-background px-2" type={definition.value_type === "NUMBER" ? "number" : "text"} value={valueFor(definition, selected)} onChange={(event) => setAmenity(definition, event.target.value)} />}<span>{locale === "th" ? definition.default_name_th : definition.default_name_en}</span></label>)}</div></fieldset>)}</div></details>
    {!existing ? <details className="rounded-lg border p-4"><summary className="cursor-pointer font-semibold">6. {t("sections.physicalRooms")}</summary><p className="mt-3 text-sm text-muted-foreground">{t("roomCodesHelp")}</p><textarea className="mt-2 min-h-28 w-full rounded-md border bg-background p-3 font-mono text-sm" placeholder={"301, 3, A, East\n302, 3, A, East"} value={roomCodes} onChange={(event) => setRoomCodes(event.target.value)} /></details> : null}
    <div className="flex justify-end gap-2"><Button variant="outline" onClick={onDone}>{t("cancel")}</Button><Button disabled={pending || !form.property_id || !form.code || !form.name} onClick={submit}>{pending ? <Loader2 className="animate-spin" /> : null}{t("save")}</Button></div>
  </CardContent></Card>;
}

function Gallery({ detail, canManage }: { detail: RoomCatalogDetail; canManage: boolean }) {
  const t = useTranslations("hotelCatalog"); const mutations = useHotelCatalogMutations();
  const [file, setFile] = useState<File>(); const [alt, setAlt] = useState("");
  const reorder = async (index: number, target: number, cover = false) => {
    const images = [...detail.images];
    if (!cover) [images[index], images[target]] = [images[target], images[index]];
    try {
      await mutations.imageOrder.mutateAsync({
        id: detail.room_type.id,
        payload: images.map((image, sort_order) => ({
          image_id: image.id,
          sort_order,
          is_cover: cover ? image.id === detail.images[index].id : image.is_cover,
        })),
      });
    } catch { toast.error(t("saveError")); }
  };
  return <section className="space-y-3"><div className="grid auto-rows-32 grid-cols-2 gap-2 md:grid-cols-4">{detail.images.length ? detail.images.map((image, index) => <figure key={image.id} className={`relative ${index === 0 ? "col-span-2 row-span-2" : ""} overflow-hidden rounded-xl border`}><AuthenticatedImage image={image} /><figcaption className="sr-only">{image.caption ?? image.alt_text}</figcaption>{canManage ? <div className="absolute bottom-2 right-2 flex gap-1 rounded-md bg-background/90 p-1"><Button type="button" size="icon" variant="ghost" aria-label={t("movePrevious")} disabled={index === 0 || mutations.imageOrder.isPending} onClick={() => reorder(index, index - 1)}><ArrowLeft /></Button><Button type="button" size="icon" variant="ghost" aria-label={t("setCover")} disabled={image.is_cover || mutations.imageOrder.isPending} onClick={() => reorder(index, index, true)}><Star className={image.is_cover ? "fill-current" : ""} /></Button><Button type="button" size="icon" variant="ghost" aria-label={t("moveNext")} disabled={index === detail.images.length - 1 || mutations.imageOrder.isPending} onClick={() => reorder(index, index + 1)}><ArrowRight /></Button></div> : null}</figure>) : <div className="col-span-full flex min-h-40 items-center justify-center rounded-xl border border-dashed bg-muted/20 text-muted-foreground">{t("noPhotos")}</div>}</div>{canManage ? <div className="flex flex-wrap items-end gap-2 rounded-lg border p-3"><label className="text-sm">{t("photo")}<Input className="mt-1" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => setFile(event.target.files?.[0])} /></label><label className="text-sm">{t("altText")}<Input className="mt-1" value={alt} onChange={(event) => setAlt(event.target.value)} /></label><Button disabled={!file || !alt || mutations.image.isPending} onClick={async () => { if (!file) return; try { await mutations.image.mutateAsync({ id: detail.room_type.id, file, altText: alt, isCover: detail.images.length === 0 }); setFile(undefined); setAlt(""); toast.success(t("saved")); } catch { toast.error(t("saveError")); } }}><ImagePlus />{t("upload")}</Button></div> : null}</section>;
}

export function RoomCatalogView() {
  const t = useTranslations("hotelCatalog"); const workspace = useMyWorkspace(); const access = useWorkspaceAccess(workspace.data?.id);
  const canManage = access.data?.capabilities.includes("room.manage") ?? false;
  const properties = useHotelProperties(); const [propertyId, setPropertyId] = useState("");
  const roomTypes = useHotelRoomTypes(propertyId || undefined); const [selectedId, setSelectedId] = useState<string>(); const detail = useRoomCatalogDetail(selectedId);
  const [formMode, setFormMode] = useState<"create" | "edit">();
  return <div className="space-y-6"><header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"><div><div className="mb-2 flex size-10 items-center justify-center rounded-xl bg-pink-500/15 text-pink-500"><BedDouble /></div><h1 className="text-2xl font-semibold">{t("title")}</h1><p className="text-sm text-muted-foreground">{t("description")}</p></div>{canManage ? <Button onClick={() => setFormMode("create")}><Plus />{t("createRoomType")}</Button> : null}</header>
    {formMode ? <RoomTypeForm existing={formMode === "edit" ? detail.data : undefined} onDone={() => setFormMode(undefined)} /> : <div className="grid gap-4 lg:grid-cols-[320px_1fr]"><Card><CardHeader><CardTitle>{t("roomTypes")}</CardTitle><CardDescription>{t("catalogHint")}</CardDescription></CardHeader><CardContent className="space-y-3"><select className="h-10 w-full rounded-md border bg-background px-2" value={propertyId} onChange={(event) => { setPropertyId(event.target.value); setSelectedId(undefined); }}><option value="">{t("allProperties")}</option>{properties.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{roomTypes.isLoading ? <Loader2 className="animate-spin" /> : roomTypes.data?.length ? <div className="space-y-2">{roomTypes.data.map((room) => <button key={room.id} type="button" onClick={() => setSelectedId(room.id)} className={`w-full rounded-lg border p-3 text-left transition-colors ${selectedId === room.id ? "border-cyan-500 bg-cyan-500/10" : "hover:bg-muted"}`}><strong className="block">{room.name}</strong><span className="text-xs text-muted-foreground">{room.code}</span></button>)}</div> : <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground"><p>{t("emptyRoomTypes")}</p>{canManage ? <Button className="mt-3" size="sm" onClick={() => setFormMode("create")}>{t("createFirst")}</Button> : null}</div>}</CardContent></Card>
      <div>{!selectedId ? <Card><CardContent className="p-12 text-center text-muted-foreground">{t("selectRoomType")}</CardContent></Card> : detail.isLoading ? <Loader2 className="animate-spin" /> : detail.data ? <Card><CardHeader className="flex-row items-start justify-between"><div><CardTitle className="text-2xl">{detail.data.room_type.name}</CardTitle><CardDescription>{detail.data.room_type.short_description}</CardDescription></div>{canManage ? <Button variant="outline" onClick={() => setFormMode("edit")}><Pencil />{t("edit")}</Button> : null}</CardHeader><CardContent className="space-y-6"><Gallery detail={detail.data} canManage={canManage} /><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[[t("view"), detail.data.room_type.custom_view_label ?? detail.data.room_type.view_type.replaceAll("_", " ")], [t("roomSize"), detail.data.room_type.room_size_sqm ? `${detail.data.room_type.room_size_sqm} m²` : "—"], [t("capacity"), t("guests", { count: detail.data.room_type.max_occupancy })], [t("physicalRoomCount"), detail.data.physical_room_count]].map(([label, value]) => <div key={String(label)} className="rounded-lg border p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-semibold">{value}</p></div>)}</div><section><h3 className="font-semibold">{t("beds")}</h3><div className="mt-2 flex flex-wrap gap-2">{detail.data.beds.map((bed) => <span key={bed.id} className="rounded-full border px-3 py-1 text-sm">{bed.quantity} × {bed.custom_label ?? bed.bed_type.replaceAll("_", " ")}</span>)}</div></section><section><h3 className="font-semibold">{t("amenities")}</h3><div className="mt-2 flex flex-wrap gap-2">{detail.data.amenities.map((amenity) => <span key={amenity.id} className="rounded-full bg-muted px-3 py-1 text-sm">{amenity.name_en ?? amenity.code}{amenity.number_value ? ` · ${amenity.number_value}` : amenity.text_value ? ` · ${amenity.text_value}` : ""}</span>)}</div></section></CardContent></Card> : <Card><CardContent className="p-8 text-center text-destructive">{t("loadError")}</CardContent></Card>}</div></div>}
  </div>;
}
