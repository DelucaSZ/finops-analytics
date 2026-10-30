"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { BrandLogo } from "@/components/brand/brand-logo";
import { useTheme } from "@/components/theme-provider";
import {
  Avatar,
  Divider,
  Drawer,
  DrawerContent,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  IconButton,
  Tooltip,
} from "@/components/ui";
import { brand } from "@/lib/brand";
import { iconDefaults, iconSizes } from "@/lib/iconography";
import {
  parseSidebarCollapsed,
  serializeSidebarCollapsed,
  SIDEBAR_STORAGE_KEY,
  type ThemePreference,
} from "@/lib/ui-preferences.mjs";
import { isNavigationItemActive, navigation, type NavigationItem } from "./navigation";
import styles from "./app-shell.module.css";

export interface ShellUser {
  name?: string | null;
  full_name?: string | null;
  email?: string | null;
  role?: string | null;
}

interface ApplicationShellProps {
  children: ReactNode;
  user?: ShellUser | null;
  leaving?: boolean;
  statusMessage?: string;
  onLogout(): void | Promise<void>;
}

const themeOptions: ReadonlyArray<{
  value: ThemePreference;
  label: string;
  icon: LucideIcon;
}> = [
  { value: "light", label: "Claro", icon: Sun },
  { value: "dark", label: "Escuro", icon: Moon },
  { value: "system", label: "Sistema", icon: Monitor },
];

function AvenBrand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className={styles.brandLink} href="/" aria-label={`${brand.name} — Dashboard`}>
      <span className={compact ? styles.brandWordmarkMobile : styles.brandWordmark} aria-hidden="true">
        <BrandLogo variant="wordmark" decorative />
      </span>
      {!compact && (
        <span className={styles.brandMark} aria-hidden="true">
          <BrandLogo variant="verticalNoTagline" decorative />
        </span>
      )}
      <span className={styles.srOnly}>{brand.name}</span>
    </Link>
  );
}

function NavigationLink({
  item,
  pathname,
  collapsed,
  onNavigate,
}: {
  item: NavigationItem;
  pathname: string;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  const active = isNavigationItemActive(pathname, item);
  const link = (
    <Link
      className={styles.navItem}
      href={item.href}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? item.label : undefined}
      onClick={onNavigate}
    >
      <Icon {...iconDefaults} size={iconSizes.lg} aria-hidden="true" />
      <span className={styles.navLabel}>{item.label}</span>
    </Link>
  );

  return collapsed ? <Tooltip className={styles.navTooltip} content={item.label}>{link}</Tooltip> : link;
}

function SidebarNavigation({
  pathname,
  collapsed,
  onNavigate,
}: {
  pathname: string;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  return (
    <nav className={styles.navigation} aria-label="Navegação principal">
      {navigation.map((item) => (
        <NavigationLink
          key={item.href}
          item={item}
          pathname={pathname}
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
      ))}
    </nav>
  );
}

function Sidebar({
  pathname,
  collapsed,
  onToggleCollapsed,
}: {
  pathname: string;
  collapsed: boolean;
  onToggleCollapsed(): void;
}) {
  return (
    <div className={styles.sidebarBody}>
      <div className={styles.brandRow}>
        <AvenBrand />
      </div>

      <SidebarNavigation pathname={pathname} collapsed={collapsed} />

      <div className={styles.sidebarFooter}>
        <Divider />
        <div className={styles.sidebarUtility}>
          <IconButton
            aria-label={collapsed ? "Expandir navegação" : "Recolher navegação"}
            tooltip={collapsed ? "Expandir navegação" : "Recolher navegação"}
            onClick={onToggleCollapsed}
            aria-expanded={!collapsed}
            aria-controls="aven-desktop-sidebar"
          >
            {collapsed ? (
              <ChevronRight {...iconDefaults} aria-hidden="true" />
            ) : (
              <ChevronLeft {...iconDefaults} aria-hidden="true" />
            )}
          </IconButton>
          <span className={styles.collapseLabel}>Recolher navegação</span>
        </div>
      </div>
    </div>
  );
}

function ThemeControl() {
  const { theme, setTheme } = useTheme();
  const current = themeOptions.find((option) => option.value === theme) ?? themeOptions[2];
  const CurrentIcon = current.icon;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className={styles.topbarControl} aria-label={`Tema: ${current.label}`}>
        <CurrentIcon {...iconDefaults} aria-hidden="true" />
        <span className={styles.topbarControlLabel}>{current.label}</span>
        <ChevronDown {...iconDefaults} size={iconSizes.sm} aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent className={styles.themeMenu} aria-label="Selecionar tema">
        {themeOptions.map((option) => {
          const Icon = option.icon;
          return (
            <DropdownMenuItem
              key={option.value}
              icon={<Icon {...iconDefaults} aria-hidden="true" />}
              onClick={() => setTheme(option.value)}
              aria-label={theme === option.value ? `${option.label}, selecionado` : option.label}
            >
              <span className={styles.themeMenuLabel}>{option.label}</span>
              {theme === option.value && <Check {...iconDefaults} size={iconSizes.sm} aria-hidden="true" />}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function getInitials(value: string) {
  const words = value.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  return words.slice(0, 2).map((word) => word[0]?.toUpperCase()).join("");
}

function UserControl({
  user,
  leaving,
  onLogout,
}: Pick<ApplicationShellProps, "user" | "leaving" | "onLogout">) {
  const displayName = user?.name || user?.full_name || user?.email || null;
  const secondary = user?.email && user.email !== displayName ? user.email : user?.role;
  const identityLabel = displayName || "Conta autenticada";
  const initials = displayName ? getInitials(displayName) : "?";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className={styles.userTrigger} aria-label="Menu do usuário">
        <Avatar fallback={initials} alt={identityLabel} size="sm" />
        {(displayName || secondary) && (
          <span className={styles.userTriggerCopy}>
            {displayName && <strong>{displayName}</strong>}
            {secondary && <small>{secondary}</small>}
          </span>
        )}
        <ChevronDown {...iconDefaults} size={iconSizes.sm} aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent className={styles.userMenu} aria-label="Ações do usuário">
        <div className={styles.userSummary}>
          <strong>{identityLabel}</strong>
          {secondary && <span>{secondary}</span>}
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          danger
          disabled={leaving}
          icon={<LogOut {...iconDefaults} aria-hidden="true" />}
          onClick={() => void onLogout()}
        >
          {leaving ? "Saindo…" : "Sair"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Topbar({
  user,
  leaving,
  onLogout,
  onOpenMobileNavigation,
}: Pick<ApplicationShellProps, "user" | "leaving" | "onLogout"> & {
  onOpenMobileNavigation(): void;
}) {
  return (
    <header className={styles.topbar}>
      <div className={styles.topbarLeading}>
        <IconButton
          className={styles.mobileMenuTrigger}
          aria-label="Abrir navegação"
          tooltip="Abrir navegação"
          onClick={onOpenMobileNavigation}
        >
          <Menu {...iconDefaults} size={iconSizes.xl} aria-hidden="true" />
        </IconButton>
        <div className={styles.mobileBrand}>
          <AvenBrand compact />
        </div>
      </div>

      <div className={styles.topbarUtilities}>
        <ThemeControl />
        <UserControl user={user} leaving={leaving} onLogout={onLogout} />
      </div>
    </header>
  );
}

export function ApplicationShell({
  children,
  user,
  leaving = false,
  statusMessage,
  onLogout,
}: ApplicationShellProps) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    } catch {
      saved = null;
    }
    const next = parseSidebarCollapsed(saved);
    setCollapsed(next);
    document.documentElement.dataset.sidebar = next ? "collapsed" : "expanded";
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  function toggleSidebar() {
    const next = !collapsed;
    setCollapsed(next);
    document.documentElement.dataset.sidebar = next ? "collapsed" : "expanded";
    try {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, serializeSidebarCollapsed(next));
    } catch {
      // Navigation remains functional when local persistence is unavailable.
    }
  }

  return (
    <div className={styles.shell}>
      <a className={styles.skipLink} href="#main-content">Pular para o conteúdo</a>

      <aside id="aven-desktop-sidebar" className={styles.desktopSidebar} aria-label="Navegação principal">
        <Sidebar pathname={pathname} collapsed={collapsed} onToggleCollapsed={toggleSidebar} />
      </aside>

      <div className={styles.workspace}>
        <Topbar
          user={user}
          leaving={leaving}
          onLogout={onLogout}
          onOpenMobileNavigation={() => setMobileOpen(true)}
        />

        <main id="main-content" tabIndex={-1} className={styles.mainContent}>
          <div className={styles.contentFrame}>
            {statusMessage && <p className={styles.shellError} role="alert">{statusMessage}</p>}
            {children}
          </div>
        </main>
      </div>

      <Drawer open={mobileOpen} onOpenChange={setMobileOpen}>
        <DrawerContent side="left" className={styles.mobileDrawer} aria-label="Navegação móvel">
          <div className={styles.mobileSidebar}>
            <div className={styles.mobileBrandRow}>
              <AvenBrand compact />
            </div>
            <SidebarNavigation
              pathname={pathname}
              collapsed={false}
              onNavigate={() => setMobileOpen(false)}
            />
          </div>
        </DrawerContent>
      </Drawer>
    </div>
  );
}
