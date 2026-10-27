"use client";

import { motion, useScroll } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { MobileNav } from "@/components/layout/mobile-nav";
import { Logo } from "@/components/shared/logo";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { Button } from "@/components/ui/button";
import { useActiveSection } from "@/hooks/use-active-section";
import { useScrolled } from "@/hooks/use-scroll-progress";
import { LANDING_SECTIONS, NAV_LINKS } from "@/lib/constants";
import { cn } from "@/lib/utils";

export function Navbar() {
  const t = useTranslations();
  const pathname = usePathname();
  const scrolled = useScrolled(12);
  const isLanding = pathname === "/";
  const activeSection = useActiveSection(
    isLanding ? LANDING_SECTIONS.map((s) => s.id) : [],
  );
  const { scrollYProgress } = useScroll();

  const underline =
    "absolute inset-x-3 -bottom-0.5 h-0.5 origin-left rounded-full bg-brand transition-transform duration-300";

  return (
    <header
      className={cn(
        "sticky top-0 z-40 w-full transition-all duration-300",
        scrolled
          ? "border-b border-border/60 bg-background/70 backdrop-blur-xl"
          : "border-b border-transparent bg-transparent",
      )}
    >
      <div
        className={cn(
          "container-wide flex items-center justify-between gap-4 transition-all duration-300",
          scrolled ? "h-14" : "h-16",
        )}
      >
        <Logo className={cn("transition-transform", scrolled && "scale-95")} />

        <nav className="hidden items-center gap-1 lg:flex">
          {isLanding
            ? LANDING_SECTIONS.map((section) => (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  className="group relative px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
                >
                  {t(`nav.sections.${section.key}`)}
                  <span
                    className={cn(
                      underline,
                      activeSection === section.id
                        ? "scale-x-100"
                        : "scale-x-0 group-hover:scale-x-100",
                    )}
                  />
                </a>
              ))
            : NAV_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="group relative px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
                >
                  {t(`nav.links.${link.key}`)}
                  <span
                    className={cn(
                      underline,
                      pathname === link.href
                        ? "scale-x-100"
                        : "scale-x-0 group-hover:scale-x-100",
                    )}
                  />
                </Link>
              ))}
        </nav>

        <div className="flex items-center gap-2">
          <div className="hidden sm:block">
            <ThemeToggle />
          </div>
          <Button asChild variant="ghost" size="sm" className="hidden lg:inline-flex">
            <Link href="/login">{t("common.login")}</Link>
          </Button>
          <Button asChild size="sm" className="hidden lg:inline-flex">
            <Link href="/register">{t("common.getStarted")}</Link>
          </Button>
          <MobileNav />
        </div>
      </div>

      <motion.div
        aria-hidden
        style={{ scaleX: scrollYProgress }}
        className="h-0.5 origin-left bg-brand"
      />
    </header>
  );
}
