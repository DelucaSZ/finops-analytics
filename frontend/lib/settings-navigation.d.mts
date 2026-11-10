export type SettingsTab = { href: string; labelKey: "appearance" | "accounts" | "policies" | "security" | "sessions" | "users" | "audit" | "https" | "pricing" | "billingProfiles" | "usageCosts" | "retention" };
export type LegacySettingsRedirect = {
  source: string;
  destination: string;
  permanent: boolean;
};

export const legacySettingsRedirects: LegacySettingsRedirect[];
export function settingsTabsForRole(role: string): SettingsTab[];
export function isSettingsTabActive(pathname: string, href: string): boolean;
export function isAdminOnlySettingsPath(pathname: string): boolean;
export function canManageCloudAccounts(role: string): boolean;
export function canRunCloudAnalysis(role: string): boolean;
export function canManagePolicies(role: string): boolean;
