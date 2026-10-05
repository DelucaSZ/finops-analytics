import type { CloudAccount, ProviderCapabilities } from "./types";

// Type-only compatibility for manual collection helpers consumed by the settings UI.
export function isManualCollectionEligible(
  account: CloudAccount | null | undefined,
  capability: ProviderCapabilities | null | undefined,
): boolean;

export function eligibleManualCollectionAccounts(
  accounts: CloudAccount[],
  capabilities: ProviderCapabilities[],
): CloudAccount[];

export function eligibleManualCollectionProviders(
  accounts: CloudAccount[],
  capabilities: ProviderCapabilities[],
): ProviderCapabilities[];

export function accountsForManualCollectionProvider(
  accounts: CloudAccount[],
  capabilities: ProviderCapabilities[],
  provider: string,
): CloudAccount[];
