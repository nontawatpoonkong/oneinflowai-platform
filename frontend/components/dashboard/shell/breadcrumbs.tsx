"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { Fragment } from "react";

const KNOWN_KEYS = new Set([
  "dashboard",
  "inbox",
  "customers",
  "hotel",
  "rooms",
  "stays",
  "housekeeping",
  "knowledge",
  "analytics",
  "integrations",
  "workspace",
  "settings",
]);

export function Breadcrumbs() {
  const pathname = usePathname();
  const tNav = useTranslations("dashboard.nav");
  const segments = pathname.split("/").filter(Boolean);

  const label = (segment: string) =>
    KNOWN_KEYS.has(segment)
      ? tNav(segment)
      : segment.charAt(0).toUpperCase() + segment.slice(1);

  return (
    <nav aria-label="Breadcrumb" className="hidden items-center gap-1.5 text-sm sm:flex">
      {segments.map((segment, index) => {
        const href = "/" + segments.slice(0, index + 1).join("/");
        const isLast = index === segments.length - 1;
        return (
          <Fragment key={href}>
            {index > 0 ? (
              <ChevronRight className="size-3.5 text-muted-foreground" />
            ) : null}
            {isLast ? (
              <span className="font-medium">{label(segment)}</span>
            ) : (
              <Link
                href={href}
                className="text-muted-foreground transition-colors hover:text-foreground"
              >
                {label(segment)}
              </Link>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}
