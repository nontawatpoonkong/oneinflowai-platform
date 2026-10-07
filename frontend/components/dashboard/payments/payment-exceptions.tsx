"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  useAcknowledgeBookingPayment,
  useBookingPaymentExceptions,
  useReconcileBookingPayment,
} from "@/hooks/api/use-payments";
import { useMyWorkspace, useWorkspaceMembers } from "@/hooks/api/use-workspace";
import { useAuth } from "@/hooks/use-auth";

export function PaymentExceptionsPanel({ onSelectPayment }: { onSelectPayment: (id: string) => void }) {
  const t = useTranslations("hotelPaymentExceptions");
  const { user } = useAuth();
  const workspace = useMyWorkspace();
  const members = useWorkspaceMembers(workspace.data?.id);
  const role = members.data?.find((member) => member.user_id === user?.id)?.role;
  const canManage = role === "owner" || role === "admin";
  const exceptions = useBookingPaymentExceptions();
  const reconcile = useReconcileBookingPayment();
  const acknowledge = useAcknowledgeBookingPayment();
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const retry = async (id: string) => {
    try {
      const result = await reconcile.mutateAsync(id);
      toast.success(result.application_status === "APPLIED" ? t("applied") : t("stillNeedsReview"));
    } catch {
      toast.error(t("retryError"));
    }
  };

  const saveNote = async (id: string) => {
    try {
      await acknowledge.mutateAsync({ id, note: note.trim() });
      setReviewing(null);
      setNote("");
      toast.success(t("acknowledged"));
    } catch {
      toast.error(t("acknowledgeError"));
    }
  };

  return (
    <section className="rounded-2xl border bg-card p-5" aria-labelledby="payment-exceptions-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="payment-exceptions-title" className="font-semibold">{t("title")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("description")}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => exceptions.refetch()} disabled={exceptions.isFetching}>
          {exceptions.isFetching ? <Loader2 className="size-4 animate-spin" /> : null}{t("refresh")}
        </Button>
      </div>
      {exceptions.isLoading ? <p className="mt-4 text-sm text-muted-foreground">{t("loading")}</p> : null}
      {exceptions.isError ? <p className="mt-4 text-sm text-destructive">{t("loadError")}</p> : null}
      {exceptions.data?.length === 0 ? <p className="mt-4 text-sm text-muted-foreground">{t("empty")}</p> : null}
      <div className="mt-4 space-y-3">
        {exceptions.data?.map((item) => (
          <article key={item.payment_id} className="rounded-xl border p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 space-y-1 text-sm">
                <div className="flex items-center gap-2"><AlertTriangle className="size-4 text-warning" /><Badge variant="muted">{item.reason ? t(`reasons.${item.reason}`) : t("unclassified")}</Badge></div>
                <p>{t("payment")}: <span className="font-mono">{item.payment_id.slice(0, 8)}</span> · {t("booking")}: <span className="font-mono">{item.booking_id.slice(0, 8)}</span></p>
                <p>{t("amount")}: {new Intl.NumberFormat(undefined, { style: "currency", currency: item.payment_currency }).format(Number(item.payment_verified_amount ?? item.payment_expected_amount))}</p>
                <p className="text-xs text-muted-foreground">{item.payment_verified_at ? new Date(item.payment_verified_at).toLocaleString() : "—"} · {t("bookingStatus")}: {item.booking_status}</p>
                {item.review_note ? <p className="text-xs text-muted-foreground">{t("reviewNote")}: {item.review_note}</p> : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => onSelectPayment(item.payment_id)}>{t("viewPayment")}</Button>
                {canManage ? <Button size="sm" variant="outline" disabled={reconcile.isPending} onClick={() => retry(item.payment_id)}>{t("retry")}</Button> : null}
                {canManage ? <Button size="sm" variant="outline" onClick={() => { setReviewing(item.payment_id); setNote(item.review_note ?? ""); }}>{t("acknowledge")}</Button> : null}
              </div>
            </div>
            {canManage && reviewing === item.payment_id ? (
              <div className="mt-4 space-y-2">
                <label htmlFor={`review-${item.payment_id}`} className="text-xs text-muted-foreground">{t("reviewNote")}</label>
                <textarea id={`review-${item.payment_id}`} className="min-h-20 w-full rounded-md border bg-background p-2 text-sm" maxLength={1000} value={note} onChange={(event) => setNote(event.target.value)} />
                <p className="text-xs text-muted-foreground">{t("noFinancialAction")}</p>
                <Button size="sm" disabled={!note.trim() || acknowledge.isPending} onClick={() => saveNote(item.payment_id)}>{t("saveNote")}</Button>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
