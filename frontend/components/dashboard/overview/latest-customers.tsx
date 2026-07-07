"use client";

import { UserPlus, Users } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCustomers } from "@/hooks/api/use-customers";
import { formatDate, initialsFrom } from "@/utils/format";

export function LatestCustomers() {
  const t = useTranslations("dashboard");
  const { data, isLoading, isError } = useCustomers({
    page: 1,
    page_size: 5,
    sort_by: "created_at",
    order: "desc",
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("overview.latestCustomers")}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : isError || !data || data.items.length === 0 ? (
          <EmptyState
            icon={Users}
            title={t("empty.customersTitle")}
            description={t("empty.customersDesc")}
            action={
              <Button asChild size="sm" variant="outline">
                <Link href="/dashboard/customers">
                  <UserPlus className="size-4" /> {t("overview.addCustomer")}
                </Link>
              </Button>
            }
          />
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {data.items.map((customer) => (
              <li key={customer.id} className="flex items-center gap-3 py-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-brand/10 text-xs font-semibold text-brand">
                  {initialsFrom(customer.display_name, customer.display_name)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {customer.display_name}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {customer.email ?? customer.phone ?? t("overview.noContact")}
                  </p>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {formatDate(customer.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
