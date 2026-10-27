import Link from "next/link";
import type { ReactNode } from "react";

import { Logo } from "@/components/shared/logo";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { Card } from "@/components/ui/card";

interface AuthShellProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function AuthShell({ title, subtitle, children, footer }: AuthShellProps) {
  return (
    <div className="relative flex min-h-dvh items-center justify-center bg-surface px-4 py-20 sm:px-6">
      <div className="absolute left-4 top-5 sm:left-6">
        <Logo />
      </div>
      <div className="absolute right-4 top-4 sm:right-6">
        <ThemeToggle />
      </div>

      <Card className="w-full max-w-md p-6 shadow-soft sm:p-8">
        <div className="mb-7 flex flex-col gap-1.5 text-left">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="text-sm leading-6 text-muted-foreground">{subtitle}</p>
        </div>
        {children}
        {footer ? <div className="mt-6 text-center text-sm">{footer}</div> : null}
      </Card>
    </div>
  );
}

export function AuthLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="font-medium text-brand hover:underline">
      {children}
    </Link>
  );
}
