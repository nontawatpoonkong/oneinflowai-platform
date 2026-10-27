import { Workflow } from "lucide-react";
import Link from "next/link";

import { SITE } from "@/lib/constants";
import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cn("group inline-flex items-center gap-2", className)}
      aria-label={`${SITE.name} home`}
    >
      <span className="grid size-8 place-items-center rounded-lg bg-foreground text-background transition-colors group-hover:bg-brand group-hover:text-brand-foreground">
        <Workflow className="size-4" strokeWidth={2.2} />
      </span>
      <span className="text-base font-semibold tracking-[-0.02em]">
        OneInFlow<span className="text-brand">AI</span>
      </span>
    </Link>
  );
}
