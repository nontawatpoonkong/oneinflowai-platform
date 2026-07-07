import type { Metadata } from "next";
import { BookOpen, Boxes, MessageSquare, Rocket, Users } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { SiteShell } from "@/components/layout/site-shell";
import { Card } from "@/components/ui/card";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("docs") };
}

const TOPICS = [
  { id: "gettingStarted", icon: Rocket },
  { id: "conversations", icon: MessageSquare },
  { id: "customers", icon: Users },
  { id: "workspaces", icon: Boxes },
  { id: "api", icon: BookOpen },
];

export default async function DocsPage() {
  const t = await getTranslations("docs");

  return (
    <SiteShell>
      <div className="container-wide grid gap-10 py-20 lg:grid-cols-[220px_1fr]">
        <aside className="hidden lg:block">
          <nav className="sticky top-24 flex flex-col gap-1 text-sm">
            {TOPICS.map((topic) => (
              <span
                key={topic.id}
                className="rounded-lg px-3 py-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {t(`topics.${topic.id}.title`)}
              </span>
            ))}
          </nav>
        </aside>

        <div className="flex flex-col gap-6">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
            <p className="mt-2 text-muted-foreground">{t("description")}</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {TOPICS.map((topic) => (
              <Card key={topic.id} className="flex items-start gap-4 p-5">
                <span className="grid size-10 place-items-center rounded-xl bg-brand/10 text-brand">
                  <topic.icon className="size-5" />
                </span>
                <div>
                  <h3 className="font-semibold">{t(`topics.${topic.id}.title`)}</h3>
                  <p className="text-sm text-muted-foreground">
                    {t(`topics.${topic.id}.description`)}
                  </p>
                </div>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </SiteShell>
  );
}
