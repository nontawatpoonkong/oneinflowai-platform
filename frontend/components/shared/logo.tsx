import { Sparkles } from "lucide-react";
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
      <span className="grid size-8 place-items-center rounded-xl bg-brand-gradient text-brand-foreground shadow-glow transition-transform group-hover:scale-105">
        <Sparkles className="size-4" />
      </span>
      <span className="text-lg font-semibold tracking-tight">
        One<span className="text-gradient">Flow</span>AI
      </span>
    </Link>
  );
}
