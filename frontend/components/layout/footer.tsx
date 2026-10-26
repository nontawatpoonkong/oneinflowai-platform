"use client";

import { Github, Mail, Twitter } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Logo } from "@/components/shared/logo";
import { FOOTER_SECTIONS, SITE } from "@/lib/constants";

const SOCIALS = [
  { label: "GitHub", href: SITE.github, icon: Github },
  { label: "Twitter", href: "#", icon: Twitter },
  { label: "Contact", href: "#", icon: Mail },
];

export function Footer() {
  const t = useTranslations();

  return (
    <footer className="border-t border-border bg-background">
      <div className="container-wide grid gap-12 py-14 md:grid-cols-[1.4fr_repeat(3,1fr)]">
        <div className="flex flex-col gap-4">
          <Logo />
          <p className="max-w-xs text-sm text-muted-foreground">
            {t("footer.tagline")}
          </p>
          <div className="flex items-center gap-2">
            {SOCIALS.map(({ label, href, icon: Icon }) => (
              <a
                key={label}
                href={href}
                aria-label={label}
                className="grid size-9 place-items-center rounded-md border border-border text-muted-foreground transition-colors hover:border-brand hover:text-brand"
              >
                <Icon className="size-4" />
              </a>
            ))}
          </div>
        </div>

        {FOOTER_SECTIONS.map((section) => (
          <div key={section.key} className="flex flex-col gap-3">
            <h3 className="text-sm font-semibold">
              {t(`footer.sections.${section.key}`)}
            </h3>
            <ul className="flex flex-col gap-2">
              {section.links.map((link) => (
                <li key={`${section.key}-${link.key}`}>
                  <Link
                    href={link.href}
                    className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {t(`footer.links.${link.key}`)}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="border-t border-border">
        <div className="container-wide flex flex-col items-center justify-between gap-2 py-6 text-sm text-muted-foreground sm:flex-row">
          <p>
            &copy; {new Date().getFullYear()} {SITE.name}. {t("footer.rights")}
          </p>
          <p>{t("footer.built")}</p>
        </div>
      </div>
    </footer>
  );
}
