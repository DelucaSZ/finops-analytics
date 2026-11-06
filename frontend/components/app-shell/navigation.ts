import type messages from "@/i18n/messages/pt-BR.json";
import {
  Activity,
  Boxes,
  Database,
  LayoutDashboard,
  ReceiptText,
  ScanSearch,
  Settings2,
  WalletCards,
  type LucideIcon,
} from "lucide-react";

export interface NavigationItem {
  href: string;
  labelKey: keyof typeof messages.shell.navigation;
  icon: LucideIcon;
  exact?: boolean;
  activePrefixes?: readonly string[];
}

export const navigation = [
  { href: "/", labelKey: "dashboard", icon: LayoutDashboard, exact: true },
  {
    href: "/opportunities",
    labelKey: "opportunities",
    icon: ScanSearch,
    exact: true,
    activePrefixes: ["/opportunities/collection/"],
  },
  { href: "/inventory", labelKey: "inventory", icon: Boxes },
  { href: "/flow", labelKey: "flow", icon: WalletCards },
  { href: "/billing", labelKey: "billing", icon: ReceiptText },
  { href: "/rds/reservations", labelKey: "reservations", icon: Database },
  { href: "/collections", labelKey: "collections", icon: Activity },
  { href: "/settings", labelKey: "settings", icon: Settings2 },
] satisfies readonly NavigationItem[];

export function isNavigationItemActive(pathname: string, item: NavigationItem) {
  if (pathname === item.href) return true;
  if (item.activePrefixes?.some((prefix) => pathname.startsWith(prefix))) return true;
  if (item.exact) return false;
  return pathname.startsWith(`${item.href}/`);
}
