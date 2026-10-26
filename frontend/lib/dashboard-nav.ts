import {
  Bell,
  BarChart3,
  Bot,
  BedDouble,
  CalendarDays,
  CalendarPlus,
  Boxes,
  ClipboardList,
  CreditCard,
  FileText,
  Hotel,
  Inbox,
  LayoutDashboard,
  type LucideIcon,
  Plug,
  Tags,
  Settings,
  ScrollText,
  Sparkles,
  Users,
} from "lucide-react";

export interface DashboardNavItem {
  key: string; // -> dashboard.nav.<key>
  href: string;
  icon: LucideIcon;
  group: "workspace" | "hotel" | "system";
  capability: string;
}

export const DASHBOARD_NAV: DashboardNavItem[] = [
  { key: "dashboard", href: "/dashboard", icon: LayoutDashboard, group: "workspace", capability: "dashboard.view" },
  { key: "inbox", href: "/dashboard/inbox", icon: Inbox, group: "workspace", capability: "conversation.read" },
  { key: "actions", href: "/dashboard/actions", icon: ClipboardList, group: "workspace", capability: "action.read" },
  { key: "customers", href: "/dashboard/customers", icon: Users, group: "workspace", capability: "guest.read" },
  { key: "payments", href: "/dashboard/payments", icon: CreditCard, group: "workspace", capability: "payment.read" },
  { key: "analytics", href: "/dashboard/analytics", icon: BarChart3, group: "workspace", capability: "analytics.read" },
  { key: "newBooking", href: "/dashboard/bookings/new", icon: CalendarPlus, group: "workspace", capability: "booking.create" },
  { key: "promotions", href: "/dashboard/promotions", icon: Tags, group: "workspace", capability: "promotion.read" },
  { key: "rooms", href: "/dashboard/hotel/rooms", icon: BedDouble, group: "hotel", capability: "room.read" },
  { key: "roomCatalog", href: "/dashboard/hotel/catalog", icon: Boxes, group: "hotel", capability: "room.read" },
  { key: "availability", href: "/dashboard/hotel/availability", icon: CalendarDays, group: "hotel", capability: "room.read" },
  { key: "stays", href: "/dashboard/hotel/stays", icon: ClipboardList, group: "hotel", capability: "stay.read" },
  { key: "housekeeping", href: "/dashboard/hotel/housekeeping", icon: Sparkles, group: "hotel", capability: "housekeeping.read" },
  { key: "pms", href: "/dashboard/hotel/pms", icon: Hotel, group: "hotel", capability: "pms.read" },
  { key: "automations", href: "/dashboard/automations", icon: Bot, group: "system", capability: "automation.read" },
  { key: "knowledge", href: "/dashboard/knowledge", icon: FileText, group: "system", capability: "knowledge.read" },
  { key: "channels", href: "/dashboard/integrations", icon: Plug, group: "system", capability: "workspace.settings.manage" },
  { key: "notifications", href: "/dashboard/notifications", icon: Bell, group: "system", capability: "dashboard.view" },
  { key: "team", href: "/dashboard/settings/team", icon: Users, group: "system", capability: "workspace.members.read" },
  { key: "workspace", href: "/dashboard/workspace", icon: Boxes, group: "system", capability: "workspace.settings.manage" },
  { key: "billing", href: "/dashboard/billing", icon: CreditCard, group: "system", capability: "workspace.billing.read" },
  { key: "audit", href: "/dashboard/settings/audit", icon: ScrollText, group: "system", capability: "audit.read" },
  { key: "settings", href: "/dashboard/settings", icon: Settings, group: "system", capability: "dashboard.view" },
];

export const DASHBOARD_NAV_GROUPS = ["workspace", "hotel", "system"] as const;

export function permittedNavigation(capabilities?: string[]) {
  if (!capabilities) return DASHBOARD_NAV.filter((item) => item.key === "dashboard");
  const allowed = new Set(capabilities);
  return DASHBOARD_NAV.filter((item) => allowed.has(item.capability));
}
