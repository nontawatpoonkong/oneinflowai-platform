import type { ReactNode } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ChartCardProps {
  title: string;
  caption?: string;
  children: ReactNode;
}

export function ChartCard({ title, caption, children }: ChartCardProps) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>{title}</CardTitle>
        {caption ? (
          <span className="text-xs text-muted-foreground">{caption}</span>
        ) : null}
      </CardHeader>
      <CardContent>
        <div className="h-32">{children}</div>
      </CardContent>
    </Card>
  );
}
