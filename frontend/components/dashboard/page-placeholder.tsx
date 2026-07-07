import type { LucideIcon } from "lucide-react";

import { EmptyState } from "@/components/shared/empty-state";

interface PagePlaceholderProps {
  title: string;
  comingSoonTitle: string;
  description: string;
  icon: LucideIcon;
}

/** Shared placeholder for dashboard sections shipping in future sprints. */
export function PagePlaceholder({
  title,
  comingSoonTitle,
  description,
  icon,
}: PagePlaceholderProps) {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <EmptyState
        icon={icon}
        title={comingSoonTitle}
        description={description}
        className="py-20"
      />
    </div>
  );
}
