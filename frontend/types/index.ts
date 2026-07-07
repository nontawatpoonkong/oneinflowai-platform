import type { LucideIcon } from "lucide-react";

/** Domain / UI types. Display text lives in the i18n dictionaries, keyed by id. */

export interface Feature {
  id: string;
  icon: LucideIcon;
}

export interface Step {
  id: string;
  icon: LucideIcon;
}

export interface FlowNode {
  id: string;
  icon: LucideIcon;
}

export interface PricingPlan {
  id: string;
  price: number;
  period: "forever" | "month" | "year";
  highlighted?: boolean;
}

export interface Industry {
  id: string;
  icon: LucideIcon;
}

export interface SidebarItem {
  id: string;
  icon: LucideIcon;
  active?: boolean;
}

export interface TrendPoint {
  label: string;
  value: number;
}

export interface LiveMetric {
  id: string;
  base: number;
  drift: number;
  decimals?: number;
  currency?: boolean;
  suffix?: string;
  unit?: "seconds";
  icon: LucideIcon;
  live?: boolean;
}

export interface ServerCard {
  id: string;
  label: string;
  base: number;
  unit: string;
  status: "healthy" | "warning" | "critical";
  icon: LucideIcon;
}

export interface CostMetric {
  id: string;
  value: number;
  suffix?: string;
  currency?: boolean;
  decimals?: number;
  unit?: "seconds";
  icon: LucideIcon;
}

export interface RoiInput {
  employees: number;
  salary: number;
  dailyConversations: number;
}
