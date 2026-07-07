"use client";

import { MessageSquarePlus, MessageSquare } from "lucide-react";
import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useConversations } from "@/hooks/api/use-conversations";
import { formatDateTime } from "@/utils/format";

export function LatestConversations() {
  const t = useTranslations("dashboard");
  const { data, isLoading, isError } = useConversations({
    page: 1,
    page_size: 5,
    sort_by: "created_at",
    order: "desc",
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("overview.latestConversations")}</CardTitle>
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
            icon={MessageSquarePlus}
            title={t("empty.conversationsTitle")}
            description={t("empty.conversationsDesc")}
          />
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {data.items.map((conversation) => (
              <li key={conversation.id} className="flex items-center gap-3 py-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-brand/10 text-brand">
                  <MessageSquare className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {conversation.subject ?? t("overview.untitledConversation")}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {conversation.channel} · {formatDateTime(conversation.created_at)}
                  </p>
                </div>
                <Badge variant="muted" className="shrink-0">
                  {t(`status.${conversation.status}`)}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
