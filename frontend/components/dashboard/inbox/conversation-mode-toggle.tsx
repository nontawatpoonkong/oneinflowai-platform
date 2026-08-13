"use client";

import { Bot, Headphones, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ConversationAiModeDTO } from "@/types/api";

const modes = [
  { value: "AUTO", icon: Sparkles },
  { value: "COPILOT", icon: Bot },
  { value: "HUMAN", icon: Headphones },
] as const;

interface ConversationModeToggleProps {
  activeMode: ConversationAiModeDTO;
  disabled: boolean;
  label: string;
  labels: Record<ConversationAiModeDTO, string>;
  onSelect: (mode: ConversationAiModeDTO) => void;
}

export function ConversationModeToggle({
  activeMode,
  disabled,
  label,
  labels,
  onSelect,
}: ConversationModeToggleProps) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      aria-busy={disabled}
      className="flex max-w-full rounded-xl border bg-muted/50 p-1"
    >
      {modes.map(({ value, icon: Icon }) => {
        const active = value === activeMode;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => !active && onSelect(value)}
            className={cn(
              "inline-flex min-w-0 items-center justify-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed",
              active
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:bg-background/60 hover:text-foreground",
              disabled && !active && "opacity-50",
            )}
          >
            <Icon className="size-3.5 shrink-0" aria-hidden="true" />
            <span className="truncate">{labels[value]}</span>
          </button>
        );
      })}
    </div>
  );
}
