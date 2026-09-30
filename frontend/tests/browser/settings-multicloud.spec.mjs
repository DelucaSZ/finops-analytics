import { expect, test } from "@playwright/test";

const now = "2026-09-30T12:00:00Z";

const awsAccount = {
  id: 1,
  provider: "aws",
  native_account_id: "123456789012",
  name: "AWS Prod",
  enabled: true,
  connection_status: "connected",
  last_connection_test_at: now,
  last_error: null,
  created_at: now,
  updated_at: now,
  oci_configuration: null,
  aws_configuration: {
    id: 11,
    role_arn: "arn:aws:iam::123456789012:role/DeepOps",
    external_id: "stage21-browser-external-id",
    regions: ["sa-east-1"],
    is_management_account: false,
    schedule_enabled: true,
    scan_interval_hours: 24,
    next_scan_at: null,
    created_at: now,
    updated_at: now,
  },
};

const ociAccount = {
  id: 2,
  provider: "oci",
  native_account_id: "ocid1.tenancy.oc1..stage21browserfixture",
  name: "OCI Prod",
  enabled: true,
  connection_status: "connected",
  last_connection_test_at: now,
  last_error: null,
  created_at: now,
  updated_at: now,
  aws_configuration: null,
  oci_configuration: {
    id: 22,
    user_ocid: "ocid1.user.oc1..stage21browserfixture",
    fingerprint: "aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99",
    region: "sa-saopaulo-1",
    scope_regions: ["sa-saopaulo-1"],
    compartment_ocids: ["ocid1.compartment.oc1..stage21browserfixture"],
    include_root_compartment: false,
    include_subcompartments: false,
    credentials_configured: true,
    credential_key_version: "v1",
    credential_revision: 1,
    configuration_revision: 1,
    created_at: now,
    updated_at: now,
  },
};

const capabilities = [
  {
    provider: "aws",
    label: "AWS",
    registration: true,
    editing: true,
    connection_test: true,
    manual_collection: true,
    scheduling: true,
    finops_policies: true,
  },
  {
    provider: "oci",
    label: "OCI",
    registration: true,
    editing: true,
    connection_test: true,
    manual_collection: false,
    scheduling: false,
    finops_policies: false,
  },
];

async function mockApi(page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1/, "");
    let payload;
    let status = 200;

    if (path === "/auth/me") {
      payload = { id: "stage21-admin", email: "admin@example.test", role: "admin" };
    } else if (path === "/cloud-accounts/capabilities") {
      payload = capabilities;
    } else if (path === "/cloud-accounts") {
      payload = [awsAccount, ociAccount];
    } else if (path === "/cloud-accounts/2") {
      payload = ociAccount;
    } else if (path === "/policies/global") {
      payload = [];
    } else {
      status = 404;
      payload = { detail: "Browser fixture endpoint not implemented" };
    }

    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("legacy accounts redirect preserves query and OCI edit never restores secrets", async ({ page }) => {
  await page.goto("/accounts?cloud=oci");

  await expect(page).toHaveURL(/\/settings\/accounts\?cloud=oci$/);
  await expect(page.getByRole("heading", { name: "Contas", level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: "Contas" })).toHaveAttribute(
    "aria-current",
    "page",
  );

  await page.getByLabel("Filtrar por cloud").selectOption("oci");
  await expect(page.getByText("OCI Prod", { exact: true })).toBeVisible();
  await expect(page.getByText("AWS Prod", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Analisar" })).toHaveCount(0);

  await page.getByRole("button", { name: "Editar" }).click();
  await expect(page.getByRole("heading", { name: "Editar OCI Prod" })).toBeVisible();
  await expect(page.getByPlaceholder("ocid1.tenancy.oc1..")).toHaveAttribute("readonly", "");

  await page.getByRole("button", { name: "Substituir credencial" }).click();
  const pem = page.getByPlaceholder("-----BEGIN PRIVATE KEY-----");
  await pem.fill("TEST-ONLY-SECRET-MUST-BE-CLEARED");
  await page.getByLabel("Senha da nova chave").fill("test-only-passphrase");

  await page.getByRole("button", { name: "Cancelar substituição" }).click();
  await expect(pem).toHaveCount(0);

  await page.getByRole("button", { name: "Substituir credencial" }).click();
  await expect(page.getByPlaceholder("-----BEGIN PRIVATE KEY-----")).toHaveValue("");
  await expect(page.getByLabel("Senha da nova chave")).toHaveValue("");
});

test("legacy policies redirect preserves query and OCI policies remain unavailable", async ({ page }) => {
  await page.goto("/policies?source=legacy");

  await expect(page).toHaveURL(/\/settings\/policies\?source=legacy$/);
  await expect(page.getByRole("heading", { name: "Políticas", level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: "Políticas" })).toHaveAttribute(
    "aria-current",
    "page",
  );

  await page.getByRole("button", { name: "OCI", exact: true }).click();
  await expect(
    page.getByText("Políticas de análise OCI ainda não disponíveis", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Nenhuma regra AWS é aplicada/)).toBeVisible();
});
