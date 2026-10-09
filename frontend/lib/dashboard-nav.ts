import {
  Bell,
  Bot,
  BedDouble,
  Boxes,
  ClipboardList,
  CreditCard,
  FileText,
  Inbox,
  LayoutDashboard,
  type LucideIcon,
  Plug,
  Settings,
  Sparkles,
  Users,
} from "lucide-react";

export interface DashboardNavItem {
  key: string; // -> dashboard.nav.<key>
  href: string;
  icon: LucideIcon;
}

export const DASHBOARD_NAV: DashboardNavItem[] = [
  { key: "dashboard", href: "/dashboard", icon: LayoutDashboard },
  { key: "inbox", href: "/dashboard/inbox", icon: Inbox },
  { key: "customers", href: "/dashboard/customers", icon: Users },
  { key: "rooms", href: "/dashboard/hotel/rooms", icon: BedDouble },
  { key: "stays", href: "/dashboard/hotel/stays", icon: ClipboardList },
  { key: "housekeeping", href: "/dashboard/hotel/housekeeping", icon: Sparkles },
  { key: "automations", href: "/dashboard/automations", icon: Bot },
  { key: "actions", href: "/dashboard/actions", icon: ClipboardList },
  { key: "knowledge", href: "/dashboard/knowledge", icon: FileText },
  { key: "payments", href: "/dashboard/payments", icon: CreditCard },
  { key: "channels", href: "/dashboard/integrations", icon: Plug },
  { key: "notifications", href: "/dashboard/notifications", icon: Bell },
  { key: "workspace", href: "/dashboard/workspace", icon: Boxes },
  { key: "billing", href: "/dashboard/billing", icon: CreditCard },
  { key: "settings", href: "/dashboard/settings", icon: Settings },
];
