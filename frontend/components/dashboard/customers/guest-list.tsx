"use client";

import { AlertTriangle, Loader2, Search, Users } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { PaginationControls } from "@/components/shared/pagination-controls";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCRMCustomers } from "@/hooks/api/use-crm";
import { useMyWorkspace, useWorkspaceAccess } from "@/hooks/api/use-workspace";

export function GuestList() {
  const t = useTranslations("guestCrm");
  const common = useTranslations("common");
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [exceptions, setExceptions] = useState(false);
  const workspace = useMyWorkspace();
  const access = useWorkspaceAccess(workspace.data?.id);
  // Section filters need the section's capability; the API rejects them otherwise.
  const capabilities = access.data?.capabilities ?? [];
  const canReadPayments = capabilities.includes("payment.read");
  const canReadBookings = capabilities.includes("booking.read");
  const [repeat, setRepeat] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const query = useCRMCustomers({
    q: search || undefined,
    has_payment_exception: (canReadPayments && exceptions) || undefined,
    repeat_guest: (canReadBookings && repeat) || undefined,
    page,
    page_size: pageSize,
  });

  const applySearch = () => {
    setSearch(draft.trim());
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </header>
      <div className="flex flex-wrap gap-2">
        <div className="flex min-w-64 flex-1 gap-2">
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") applySearch();
            }}
            placeholder={t("search")}
          />
          <Button onClick={applySearch}>
            <Search className="size-4" />
            {t("searchAction")}
          </Button>
        </div>
        {canReadPayments ? (
          <Button
            variant={exceptions ? "default" : "outline"}
            onClick={() => {
              setExceptions((value) => !value);
              setPage(1);
            }}
          >
            {t("filters.exceptions")}
          </Button>
        ) : null}
        {canReadBookings ? (
          <Button
            variant={repeat ? "default" : "outline"}
            onClick={() => {
              setRepeat((value) => !value);
              setPage(1);
            }}
          >
            {t("filters.repeat")}
          </Button>
        ) : null}
      </div>
      {query.isLoading ? (
        <State icon={Loader2} text={t("loading")} spin />
      ) : query.isError ? (
        <State icon={AlertTriangle} text={t("error")} action={() => query.refetch()} />
      ) : !query.data?.items.length ? (
        <State icon={Users} text={t("empty")} />
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-card">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-muted/40">
              <tr>
                <th className="p-3">{t("guest")}</th>
                <th className="p-3">{t("tags")}</th>
                <th className="p-3">{t("bookings")}</th>
                <th className="p-3">{t("latestBooking")}</th>
                <th className="p-3">{t("lastContact")}</th>
                <th className="p-3">{t("attention")}</th>
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((item) => (
                <tr key={item.customer.id} className="border-b last:border-0">
                  <td className="p-3">
                    <Link
                      className="font-medium text-primary"
                      href={`/dashboard/customers/${item.customer.id}`}
                    >
                      {item.customer.display_name}
                    </Link>
                    <p className="text-xs text-muted-foreground">
                      {item.customer.email ?? item.customer.phone ?? "—"}
                    </p>
                  </td>
                  <td className="p-3">
                    <div className="flex flex-wrap gap-1">
                      {item.tags.map((tag) => (
                        <Badge key={tag.id} variant="muted">
                          {tag.name}
                        </Badge>
                      ))}
                      {item.repeat_guest ? <Badge>{t("repeatGuest")}</Badge> : null}
                    </div>
                  </td>
                  <td className="p-3">{item.booking_count ?? "—"}</td>
                  <td className="p-3">{item.latest_booking_status ?? "—"}</td>
                  <td className="p-3">
                    {item.last_conversation_at
                      ? new Date(item.last_conversation_at).toLocaleString()
                      : "—"}
                  </td>
                  <td className="p-3">
                    {item.has_payment_exception ? (
                      <Badge
                        variant="outline"
                        className="border-destructive/50 text-destructive"
                      >
                        {t("paymentException")}
                      </Badge>
                    ) : item.needs_attention ? (
                      <Badge variant="outline">{t("needsAttention")}</Badge>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <PaginationControls
            page={query.data.page}
            pageSize={query.data.page_size}
            total={query.data.total}
            totalPages={query.data.total_pages}
            previousLabel={common("previous")}
            nextLabel={common("next")}
            pageSizeLabel={common("pageSize")}
            summaryLabel={common("pageSummary", {
              page: query.data.page,
              totalPages: query.data.total_pages,
              total: query.data.total,
            })}
            onPageChange={setPage}
            onPageSizeChange={(size) => {
              setPageSize(size);
              setPage(1);
            }}
          />
        </div>
      )}
    </div>
  );
}

function State({
  icon: Icon,
  text,
  action,
  spin,
}: {
  icon: typeof Users;
  text: string;
  action?: () => unknown;
  spin?: boolean;
}) {
  const t = useTranslations("common");
  return (
    <div className="grid min-h-52 place-items-center rounded-lg border border-dashed p-8 text-center">
      <div>
        <Icon
          className={`mx-auto mb-3 size-8 text-muted-foreground ${spin ? "animate-spin" : ""}`}
        />
        <p className="text-sm text-muted-foreground">{text}</p>
        {action ? (
          <Button className="mt-3" variant="outline" onClick={action}>
            {t("tryAgain")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
