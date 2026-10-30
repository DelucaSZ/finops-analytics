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
  label: string;
  icon: LucideIcon;
  exact?: boolean;
  activePrefixes?: readonly string[];
}

export const navigation = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, exact: true },
  {
    href: "/opportunities",
    label: "Oportunidades",
    icon: ScanSearch,
    exact: true,
    activePrefixes: ["/opportunities/collection/"],
  },
  { href: "/inventory", label: "Inventory", icon: Boxes },
  { href: "/flow", label: "Fluxo", icon: WalletCards },
  { href: "/billing", label: "Billing", icon: ReceiptText },
  { href: "/rds/reservations", label: "Reservas RDS", icon: Database },
  { href: "/collections", label: "Coletas", icon: Activity },
  { href: "/settings", label: "Configurações", icon: Settings2 },
] satisfies readonly NavigationItem[];

export function isNavigationItemActive(pathname: string, item: NavigationItem) {
  if (pathname === item.href) return true;
  if (item.activePrefixes?.some((prefix) => pathname.startsWith(prefix))) return true;
  if (item.exact) return false;
  return pathname.startsWith(`${item.href}/`);
}
