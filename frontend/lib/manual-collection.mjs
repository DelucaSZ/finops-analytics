export function isManualCollectionEligible(account, capability) {
  return Boolean(
    account
      && capability?.manual_collection
      && account.enabled
      && account.connection_status === "connected",
  );
}

export function eligibleManualCollectionAccounts(accounts, capabilities) {
  const capabilityByProvider = new Map(
    capabilities.map((capability) => [capability.provider, capability]),
  );
  return accounts
    .filter((account) =>
      isManualCollectionEligible(
        account,
        capabilityByProvider.get(account.provider),
      ),
    )
    .sort((left, right) => {
      const providerOrder = String(left.provider).localeCompare(String(right.provider));
      if (providerOrder !== 0) return providerOrder;
      const nameOrder = String(left.name).localeCompare(String(right.name), "pt-BR", {
        sensitivity: "base",
      });
      return nameOrder !== 0 ? nameOrder : Number(left.id) - Number(right.id);
    });
}

export function eligibleManualCollectionProviders(accounts, capabilities) {
  const eligibleAccounts = eligibleManualCollectionAccounts(accounts, capabilities);
  const eligibleProviderSet = new Set(eligibleAccounts.map((account) => account.provider));
  return capabilities
    .filter(
      (capability) =>
        capability.manual_collection && eligibleProviderSet.has(capability.provider),
    )
    .sort((left, right) =>
      String(left.label || left.provider).localeCompare(
        String(right.label || right.provider),
        "pt-BR",
        { sensitivity: "base" },
      ),
    );
}

export function accountsForManualCollectionProvider(accounts, capabilities, provider) {
  return eligibleManualCollectionAccounts(accounts, capabilities).filter(
    (account) => account.provider === provider,
  );
}
