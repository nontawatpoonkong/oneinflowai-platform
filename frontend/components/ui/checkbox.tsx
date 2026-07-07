"use client";

import { Check } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

interface CheckboxProps {
  id?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label?: string;
  className?: string;
}

/** Accessible checkbox built on a native input for reliable keyboard support. */
export function Checkbox({
  id,
  checked,
  onCheckedChange,
  label,
  className,
}: CheckboxProps) {
  return (
    <label
      htmlFor={id}
      className={cn("inline-flex cursor-pointer items-center gap-2", className)}
    >
      <span className="relative inline-flex">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onCheckedChange(e.target.checked)}
          className="peer size-4 appearance-none rounded border border-input bg-background transition-colors checked:border-brand checked:bg-brand focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        />
        <Check className="pointer-events-none absolute inset-0 m-auto size-3 scale-0 text-brand-foreground transition-transform peer-checked:scale-100" />
      </span>
      {label ? <span className="text-sm text-muted-foreground">{label}</span> : null}
    </label>
  );
}
