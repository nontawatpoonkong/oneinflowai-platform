"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarPlus, CheckCircle2, Loader2, Lock, Search, Tag, UserRound } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { OperationalState } from "@/components/dashboard/shared/operational-state";
import { PageHeader } from "@/components/dashboard/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMyWorkspace, useWorkspaceAccess } from "@/hooks/api/use-workspace";
import { ApiError } from "@/services/api/errors";
import { bookingService } from "@/services/hotel/booking.service";
import type { CustomerDTO } from "@/types/api";
import type { BookingRecord, ManualQuoteRequest } from "@/types/booking";

const today = () => new Date().toISOString().slice(0, 10);
const addDays = (value: string, days: number) => {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
};
const newKey = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
/** Display only. Money stays an exact server string and is never recalculated here. */
const money = (value: string | null | undefined, currency: string) => (value == null ? "—" : `${currency} ${value}`);
const errorText = (error: unknown) => (error instanceof ApiError ? `${error.message} (${error.code})` : "Unexpected error");

export function BookingComposer() {
  const t = useTranslations("bookingComposer");
  const workspace = useMyWorkspace();
  const access = useWorkspaceAccess(workspace.data?.id);
  const capabilities = access.data?.capabilities ?? [];
  const canCreate = capabilities.includes("booking.create");
  const canManage = capabilities.includes("booking.manage");
  const canCancel = capabilities.includes("booking.cancel");
  const canReadCatalog = capabilities.includes("room.read");
  const canReadGuests = capabilities.includes("guest.read");

  const [propertyId, setPropertyId] = useState("");
  const [roomTypeId, setRoomTypeId] = useState("");
  const [ratePlanId, setRatePlanId] = useState("");
  const [checkIn, setCheckIn] = useState(today);
  const [checkOut, setCheckOut] = useState(() => addDays(today(), 1));
  const [adults, setAdults] = useState(2);
  const [children, setChildren] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [customer, setCustomer] = useState<CustomerDTO | null>(null);
  const [guestName, setGuestName] = useState("");
  const [customerSearch, setCustomerSearch] = useState("");
  const [codeInput, setCodeInput] = useState("");
  const [appliedCode, setAppliedCode] = useState<string | null>(null);
  const [reviewedFingerprint, setReviewedFingerprint] = useState<string | null>(null);
  const [holdKey, setHoldKey] = useState<{ fingerprint: string; key: string } | null>(null);
  const [booking, setBooking] = useState<BookingRecord | null>(null);

  const properties = useQuery({ queryKey: ["composer", "properties"], queryFn: bookingService.properties, enabled: canReadCatalog });
  const roomTypes = useQuery({ queryKey: ["composer", "room-types", propertyId], queryFn: () => bookingService.roomTypes(propertyId), enabled: canReadCatalog && Boolean(propertyId) });
  const ratePlans = useQuery({ queryKey: ["composer", "rate-plans", propertyId, roomTypeId], queryFn: () => bookingService.ratePlans(propertyId, roomTypeId), enabled: canReadCatalog && Boolean(propertyId && roomTypeId) });
  const searchTerm = customerSearch.trim();
  const customers = useQuery({ queryKey: ["composer", "customers", searchTerm], queryFn: () => bookingService.searchCustomers(searchTerm), enabled: canReadGuests && searchTerm.length >= 2 });

  const room = roomTypes.data?.find((item) => item.id === roomTypeId);
  const stayNights =
    checkIn && checkOut
      ? (Date.parse(`${checkOut}T00:00:00Z`) - Date.parse(`${checkIn}T00:00:00Z`)) /
        86_400_000
      : 0;
  const errors = useMemo(() => {
    const result: Record<string, string> = {};
    if (!propertyId) result.property = t("errors.property");
    if (!roomTypeId) result.roomType = t("errors.roomType");
    if (!ratePlanId) result.ratePlan = t("errors.ratePlan");
    if (!checkIn || !checkOut || checkOut <= checkIn) result.dates = t("errors.dates");
    if (stayNights > 60) result.stayLength = t("errors.stayLength");
    if (!Number.isInteger(adults) || adults < 1) result.adults = t("errors.adults");
    if (!Number.isInteger(children) || children < 0) result.children = t("errors.children");
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 50) result.quantity = t("errors.quantity");
    if (room && (adults > room.max_adults || children > room.max_children || adults + children > room.max_occupancy)) {
      result.occupancy = t("errors.occupancy", { adults: room.max_adults, children: room.max_children, total: room.max_occupancy });
    }
    if (!customer && !guestName.trim()) result.guest = t("errors.guest");
    return result;
  }, [propertyId, roomTypeId, ratePlanId, checkIn, checkOut, adults, children, quantity, room, customer, guestName, stayNights, t]);
  const quoteReady = !errors.property && !errors.roomType && !errors.ratePlan && !errors.dates && !errors.stayLength && !errors.adults && !errors.children && !errors.quantity;

  const quoteRequest: ManualQuoteRequest = {
    property_id: propertyId,
    room_type_id: roomTypeId,
    rate_plan_id: ratePlanId,
    check_in: checkIn,
    check_out: checkOut,
    adults,
    children,
    quantity,
    customer_id: customer?.id ?? null,
    promotion_code: appliedCode,
  };
  const quote = useQuery({ queryKey: ["composer", "quote", quoteRequest], queryFn: () => bookingService.quote(quoteRequest), enabled: canCreate && quoteReady && !booking, staleTime: 0, retry: false });

  // Any input change invalidates a pending review. A retry of the same request
  // reuses its idempotency key so a network failure can never double-book.
  const fingerprint = JSON.stringify({ ...quoteRequest, guestName });
  const reviewing = reviewedFingerprint === fingerprint;
  const setReviewing = (value: boolean) => setReviewedFingerprint(value ? fingerprint : null);

  const hold = useMutation({
    mutationFn: (key: string) => bookingService.hold({ ...quoteRequest, guest_name: customer ? null : guestName.trim(), idempotency_key: key }),
    onSuccess: (value) => { setBooking(value); setReviewedFingerprint(null); },
  });
  const submitHold = () => {
    const key = holdKey?.fingerprint === fingerprint ? holdKey.key : newKey();
    setHoldKey({ fingerprint, key });
    hold.mutate(key);
  };
  const advance = useMutation({ mutationFn: (id: string) => bookingService.advanceToPayment(id), onSuccess: setBooking });
  const cancel = useMutation({ mutationFn: (id: string) => bookingService.cancel(id), onSuccess: setBooking });

  const reset = () => {
    setBooking(null); setAppliedCode(null); setCodeInput(""); setCustomer(null); setGuestName("");
    setHoldKey(null); hold.reset(); advance.reset(); cancel.reset();
  };

  if (workspace.isLoading || access.isLoading) return <OperationalState icon={Loader2} busy title={t("loading")} />;
  if (workspace.isError || access.isError) return <OperationalState icon={AlertTriangle} tone="danger" title={t("loadError")} />;
  if (!canCreate) return <OperationalState icon={Lock} title={t("denied")} description={t("deniedDescription")} />;
  if (!canReadCatalog) return <OperationalState icon={Lock} title={t("catalogDenied")} description={t("catalogDeniedDescription")} />;

  const data = quote.data;
  const promotion = data?.promotion;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("eyebrow")} title={t("title")} description={t("description")} />
      {booking ? (
        <BookingResult booking={booking} canManage={canManage} canCancel={canCancel} advancing={advance.isPending} cancelling={cancel.isPending} error={advance.error ?? cancel.error} onAdvance={() => advance.mutate(booking.id)} onCancel={() => cancel.mutate(booking.id)} onReset={reset} t={t} quotedTotal={data?.total ?? null} />
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
          <div className="space-y-5">
            <Section step="1" title={t("steps.stay")}>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label={t("property")} error={errors.property} htmlFor="property">
                  <select id="property" className={selectClass} value={propertyId} onChange={(event) => { setPropertyId(event.target.value); setRoomTypeId(""); setRatePlanId(""); }}>
                    <option value="">{properties.isLoading ? t("loading") : t("select")}</option>
                    {properties.data?.filter((item) => item.active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </Field>
                <Field label={t("checkIn")} htmlFor="check-in"><Input id="check-in" type="date" value={checkIn} onChange={(event) => setCheckIn(event.target.value)} /></Field>
                <Field label={t("checkOut")} error={errors.dates ?? errors.stayLength} htmlFor="check-out"><Input id="check-out" type="date" min={checkIn} value={checkOut} onChange={(event) => setCheckOut(event.target.value)} /></Field>
              </div>
              {properties.isError ? <p className="text-sm text-destructive">{t("catalogError")}</p> : null}
            </Section>

            <Section step="2" title={t("steps.room")}>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("roomType")} error={errors.roomType} htmlFor="room-type">
                  <select id="room-type" className={selectClass} disabled={!propertyId} value={roomTypeId} onChange={(event) => { setRoomTypeId(event.target.value); setRatePlanId(""); }}>
                    <option value="">{roomTypes.isLoading ? t("loading") : t("select")}</option>
                    {roomTypes.data?.filter((item) => item.active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </Field>
                <Field label={t("ratePlan")} error={errors.ratePlan} htmlFor="rate-plan">
                  <select id="rate-plan" className={selectClass} disabled={!roomTypeId} value={ratePlanId} onChange={(event) => setRatePlanId(event.target.value)}>
                    <option value="">{ratePlans.isLoading ? t("loading") : t("select")}</option>
                    {ratePlans.data?.filter((item) => item.active).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.refundable ? t("refundable") : t("nonRefundable")}</option>)}
                  </select>
                </Field>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label={t("adults")} error={errors.adults} htmlFor="adults"><Input id="adults" type="number" min={1} value={adults} onChange={(event) => setAdults(Number(event.target.value))} /></Field>
                <Field label={t("children")} error={errors.children} htmlFor="children"><Input id="children" type="number" min={0} value={children} onChange={(event) => setChildren(Number(event.target.value))} /></Field>
                <Field label={t("quantity")} error={errors.quantity} htmlFor="quantity"><Input id="quantity" type="number" min={1} max={50} value={quantity} onChange={(event) => setQuantity(Number(event.target.value))} /></Field>
              </div>
              {errors.occupancy ? <p className="text-sm text-destructive" role="alert">{errors.occupancy}</p> : null}
            </Section>

            <Section step="3" title={t("steps.guest")}>
              {customer ? (
                <div className="flex items-center justify-between rounded-md border border-cyan-500/40 bg-cyan-500/5 p-3">
                  <div className="flex items-center gap-3"><UserRound className="size-5 text-cyan-600" /><div><p className="font-medium">{customer.display_name}</p><p className="text-xs text-muted-foreground">{customer.email ?? customer.phone ?? customer.id}</p></div></div>
                  <Button size="sm" variant="ghost" onClick={() => setCustomer(null)}>{t("change")}</Button>
                </div>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  {canReadGuests ? (
                    <Field label={t("searchCustomer")} htmlFor="customer-search">
                      <div className="relative"><Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" /><Input id="customer-search" className="pl-9" placeholder={t("searchPlaceholder")} value={customerSearch} onChange={(event) => setCustomerSearch(event.target.value)} /></div>
                      {customers.isFetching ? <p className="text-xs text-muted-foreground">{t("searching")}</p> : null}
                      {customers.isError ? <p className="text-xs text-destructive">{t("searchError")}</p> : null}
                      {customers.data ? (
                        <ul className="mt-2 max-h-48 divide-y overflow-auto rounded-md border">
                          {customers.data.items.length === 0 ? <li className="p-3 text-sm text-muted-foreground">{t("noCustomers")}</li> : customers.data.items.map((item) => (
                            <li key={item.id}><button type="button" className="w-full p-3 text-left text-sm hover:bg-muted" onClick={() => { setCustomer(item); setCustomerSearch(""); }}><span className="font-medium">{item.display_name}</span><span className="block text-xs text-muted-foreground">{item.email ?? item.phone ?? "—"}</span></button></li>
                          ))}
                        </ul>
                      ) : null}
                    </Field>
                  ) : <p className="text-sm text-muted-foreground">{t("guestReadMissing")}</p>}
                  <Field label={t("guestName")} error={errors.guest} htmlFor="guest-name"><Input id="guest-name" maxLength={255} value={guestName} onChange={(event) => setGuestName(event.target.value)} placeholder={t("guestNamePlaceholder")} /></Field>
                </div>
              )}
            </Section>

            <Section step="4" title={t("steps.promotion")}>
              <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(event) => { event.preventDefault(); const value = codeInput.trim(); setAppliedCode(value ? value : null); }}>
                <div className="relative flex-1"><Tag className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" /><Input aria-label={t("promotionCode")} className="pl-9 uppercase" maxLength={32} value={codeInput} onChange={(event) => setCodeInput(event.target.value)} placeholder={t("promotionPlaceholder")} /></div>
                <Button type="submit" variant="outline" disabled={!codeInput.trim()}>{t("apply")}</Button>
                {appliedCode ? <Button type="button" variant="ghost" onClick={() => { setAppliedCode(null); setCodeInput(""); }}>{t("remove")}</Button> : null}
              </form>
              {promotion ? (promotion.valid
                ? <p className="flex items-center gap-2 text-sm text-cyan-700 dark:text-cyan-300"><CheckCircle2 className="size-4" />{t("promotionValid", { name: promotion.promotion_name ?? promotion.code ?? "" })}</p>
                : <p className="text-sm text-destructive" role="alert">{t("promotionInvalid", { reason: promotion.reason_code ?? "" })}</p>) : null}
            </Section>
          </div>

          <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start">
            <div className="rounded-lg border border-cyan-500/30 bg-card">
              <div className="border-b px-4 py-3"><h2 className="font-semibold">{t("quoteTitle")}</h2><p className="text-xs text-muted-foreground">{t("quoteHint")}</p></div>
              <div className="space-y-3 p-4 text-sm">
                {!quoteReady ? <p className="text-muted-foreground">{t("quoteIncomplete")}</p>
                  : quote.isFetching && !data ? <p className="flex items-center gap-2 text-muted-foreground"><Loader2 className="size-4 animate-spin" />{t("quoting")}</p>
                  : quote.isError ? <div className="space-y-2"><p className="text-destructive" role="alert">{errorText(quote.error)}</p><Button size="sm" variant="outline" onClick={() => quote.refetch()}>{t("retry")}</Button></div>
                  : data && !data.available ? <p className="text-destructive" role="alert">{t(`reasons.${data.reason_code ?? "NOT_AVAILABLE"}`, { units: data.available_units })}</p>
                  : data ? (
                    <>
                      <p className="font-medium">{data.room_type_name} · {data.rate_plan_name}</p>
                      <ul className="space-y-1 text-muted-foreground">
                        {data.nightly_rates.map((rate) => <li key={rate.date} className="flex justify-between"><span>{rate.date}</span><span>{money(rate.amount, data.currency)}</span></li>)}
                      </ul>
                      <Row label={t("unitsNights", { units: data.quantity, nights: data.nights })} value="" />
                      <Row label={t("subtotal")} value={money(data.subtotal, data.currency)} />
                      <Row label={t("discount")} value={`− ${money(data.discount_amount, data.currency)}`} />
                      <Row label={t("total")} value={money(data.total, data.currency)} strong />
                      <p className="text-xs text-muted-foreground">{data.refundable ? t("refundable") : t("nonRefundable")}{data.cancellation_policy_summary ? ` · ${data.cancellation_policy_summary}` : ""}</p>
                      {quote.isFetching ? <p className="text-xs text-muted-foreground">{t("refreshing")}</p> : null}
                    </>
                  ) : null}
              </div>
            </div>
            {reviewing && data?.available ? (
              <div className="space-y-3 rounded-lg border border-pink-500/40 bg-pink-500/5 p-4 text-sm" role="dialog" aria-label={t("confirmTitle")}>
                <h3 className="font-semibold">{t("confirmTitle")}</h3>
                <p>{t("confirmBody", { minutes: data.hold_minutes })}</p>
                <p className="text-muted-foreground">{customer ? customer.display_name : guestName} · {checkIn} → {checkOut} · {money(data.total, data.currency)}</p>
                {hold.isError ? <p className="text-destructive" role="alert">{errorText(hold.error)}</p> : null}
                <div className="flex gap-2"><Button disabled={hold.isPending} onClick={submitHold}>{hold.isPending ? <Loader2 className="size-4 animate-spin" /> : <CalendarPlus className="size-4" />}{t("confirmHold")}</Button><Button variant="ghost" disabled={hold.isPending} onClick={() => setReviewing(false)}>{t("back")}</Button></div>
              </div>
            ) : (
              <Button className="w-full" disabled={!data?.available || Object.keys(errors).length > 0 || quote.isFetching || (promotion ? !promotion.valid : false)} onClick={() => setReviewing(true)}>{t("review")}</Button>
            )}
            {promotion && !promotion.valid ? <p className="text-xs text-muted-foreground">{t("removeInvalidCode")}</p> : null}
          </aside>
        </div>
      )}
    </div>
  );
}

const selectClass = "flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm disabled:opacity-50";

function Section({ step, title, children }: { step: string; title: string; children: React.ReactNode }) {
  return <section className="space-y-4 rounded-lg border bg-card p-4"><h2 className="flex items-center gap-2 font-semibold"><span className="grid size-6 place-items-center rounded-full bg-cyan-500 text-xs text-slate-950">{step}</span>{title}</h2>{children}</section>;
}

function Field({ label, error, htmlFor, children }: { label: string; error?: string; htmlFor: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label htmlFor={htmlFor}>{label}</Label>{children}{error ? <p className="text-xs text-destructive">{error}</p> : null}</div>;
}

function Row({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return <div className={`flex justify-between ${strong ? "border-t pt-2 text-base font-semibold" : ""}`}><span>{label}</span><span>{value}</span></div>;
}

type Translate = ReturnType<typeof useTranslations>;

function BookingResult({ booking, canManage, canCancel, advancing, cancelling, error, onAdvance, onCancel, onReset, t, quotedTotal }: { booking: BookingRecord; canManage: boolean; canCancel: boolean; advancing: boolean; cancelling: boolean; error: unknown; onAdvance: () => void; onCancel: () => void; onReset: () => void; t: Translate; quotedTotal: string | null }) {
  const active = booking.status === "HELD" || booking.status === "PENDING_PAYMENT";
  return (
    <section className="space-y-4 rounded-lg border border-cyan-500/40 bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><p className="text-xs uppercase tracking-wide text-muted-foreground">{t("result.title")}</p><h2 className="text-xl font-semibold">{booking.property_name_snapshot} · {booking.item.room_type_name_snapshot}</h2></div>
        <Badge variant="outline">{booking.status}</Badge>
      </div>
      <dl className="grid gap-3 text-sm sm:grid-cols-4">
        <div><dt className="text-muted-foreground">{t("result.stay")}</dt><dd>{booking.check_in} → {booking.check_out}</dd></div>
        <div><dt className="text-muted-foreground">{t("subtotal")}</dt><dd>{money(booking.subtotal, booking.currency)}</dd></div>
        <div><dt className="text-muted-foreground">{t("discount")}</dt><dd>{money(booking.discount_amount, booking.currency)}</dd></div>
        <div><dt className="text-muted-foreground">{t("total")}</dt><dd className="font-semibold">{money(booking.total_amount, booking.currency)}</dd></div>
      </dl>
      {quotedTotal && quotedTotal !== booking.total_amount ? <p className="text-sm text-pink-600" role="status">{t("result.repriced", { quoted: quotedTotal, held: booking.total_amount })}</p> : null}
      {booking.status === "HELD" && booking.hold_expires_at ? <p className="text-sm text-muted-foreground">{t("result.holdExpires", { time: new Date(booking.hold_expires_at).toLocaleString() })}</p> : null}
      <p className="text-sm text-muted-foreground">{t(`result.next.${booking.status}`)}</p>
      {error ? <p className="text-sm text-destructive" role="alert">{errorText(error)}</p> : null}
      <div className="flex flex-wrap gap-2">
        {booking.status === "HELD" && canManage ? <Button disabled={advancing} onClick={onAdvance}>{advancing ? <Loader2 className="size-4 animate-spin" /> : null}{t("result.advance")}</Button> : null}
        {booking.status === "PENDING_PAYMENT" ? <Button asChild><Link href="/dashboard/payments">{t("result.payments")}</Link></Button> : null}
        {active && canCancel ? <Button variant="outline" disabled={cancelling} onClick={onCancel}>{t("result.cancel")}</Button> : null}
        <Button variant="ghost" onClick={onReset}>{t("result.another")}</Button>
      </div>
      {booking.status === "HELD" && !canManage ? <p className="text-xs text-muted-foreground">{t("result.manageMissing")}</p> : null}
    </section>
  );
}
