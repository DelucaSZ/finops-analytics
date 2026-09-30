import type { CloudAccount } from "./types";

export type AccountFormState = {
  provider: "" | "aws" | "oci" | string;
  name: string;
  native_account_id: string;
  enabled: boolean;
  aws: {
    role_arn: string;
    external_id: string;
    regions: string;
    is_management_account: boolean;
    schedule_enabled: boolean;
    scan_interval_hours: number;
  };
  oci: {
    user_ocid: string;
    fingerprint: string;
    region: string;
    scope_regions: string;
    compartment_ocids: string;
    include_root_compartment: boolean;
    include_subcompartments: boolean;
    private_key_pem: string;
    private_key_password: string;
  };
};

export const SUPPORTED_ACCOUNT_PROVIDERS: string[];
export function csvList(value: string): string[];
export function createEmptyAccountForm(provider?: string, externalId?: string): AccountFormState;
export function accountToForm(account: CloudAccount): AccountFormState;
export function buildCreateAccountPayload(form: AccountFormState): Record<string, unknown>;
export function buildUpdateAccountPayload(
  account: CloudAccount,
  form: AccountFormState,
  options?: { replaceCredentials?: boolean },
): Record<string, unknown>;
export function validateAccountForm(
  form: AccountFormState,
  options?: { mode?: "create" | "edit"; replaceCredentials?: boolean },
): Record<string, string>;
export function filterCloudAccounts(
  accounts: CloudAccount[],
  provider: string,
  search: string,
): CloudAccount[];
