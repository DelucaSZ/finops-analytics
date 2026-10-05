import test from "node:test";
import assert from "node:assert/strict";
import {
  accountsForManualCollectionProvider,
  eligibleManualCollectionAccounts,
  eligibleManualCollectionProviders,
  isManualCollectionEligible,
} from "../lib/manual-collection.mjs";

const capabilities = [
  { provider: "aws", label: "AWS", manual_collection: true },
  { provider: "oci", label: "OCI", manual_collection: true },
  { provider: "azure", label: "Azure", manual_collection: false },
  { provider: "gcp", label: "GCP", manual_collection: false },
];

const accounts = [
  { id: 10, provider: "oci", name: "OCI Produção", enabled: true, connection_status: "connected" },
  { id: 11, provider: "oci", name: "OCI Desabilitada", enabled: false, connection_status: "connected" },
  { id: 20, provider: "aws", name: "AWS Produção", enabled: true, connection_status: "connected" },
  { id: 21, provider: "aws", name: "AWS Não testada", enabled: true, connection_status: "untested" },
  { id: 30, provider: "azure", name: "Azure", enabled: true, connection_status: "connected" },
];

test("manual collection eligibility preserves the Accounts screen preconditions", () => {
  assert.equal(isManualCollectionEligible(accounts[0], capabilities[1]), true);
  assert.equal(isManualCollectionEligible(accounts[1], capabilities[1]), false);
  assert.equal(isManualCollectionEligible(accounts[3], capabilities[0]), false);
  assert.equal(isManualCollectionEligible(accounts[4], capabilities[2]), false);
});

test("eligible providers are capability-driven and require at least one eligible account", () => {
  assert.deepEqual(
    eligibleManualCollectionProviders(accounts, capabilities).map((item) => item.provider),
    ["aws", "oci"],
  );
});

test("accounts are filtered by provider and use CloudAccount ids", () => {
  assert.deepEqual(
    accountsForManualCollectionProvider(accounts, capabilities, "oci").map((item) => item.id),
    [10],
  );
  assert.deepEqual(
    accountsForManualCollectionProvider(accounts, capabilities, "aws").map((item) => item.id),
    [20],
  );
});

test("ineligible accounts never enter the operational collection list", () => {
  assert.deepEqual(
    eligibleManualCollectionAccounts(accounts, capabilities).map((item) => item.id).sort((a, b) => a - b),
    [10, 20],
  );
});

test("future providers become eligible without AWS or OCI hardcoding", () => {
  const futureCapabilities = [
    ...capabilities,
    { provider: "futurecloud", label: "Future Cloud", manual_collection: true },
  ];
  const futureAccounts = [
    ...accounts,
    { id: 40, provider: "futurecloud", name: "Future Prod", enabled: true, connection_status: "connected" },
  ];
  assert.deepEqual(
    eligibleManualCollectionProviders(futureAccounts, futureCapabilities).map((item) => item.provider),
    ["aws", "futurecloud", "oci"],
  );
});
