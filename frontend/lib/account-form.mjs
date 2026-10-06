export const SUPPORTED_ACCOUNT_PROVIDERS = ["aws", "oci"];

function uniqueList(items) {
  return [...new Set(items.map((item) => item.trim()).filter(Boolean))];
}

export function csvList(value) {
  return uniqueList(String(value || "").split(","));
}

export function createEmptyAccountForm(provider = "", externalId = "") {
  return {
    provider,
    name: "",
    native_account_id: "",
    enabled: true,
    schedule_enabled: false,
    scan_interval_hours: 24,
    aws: {
      role_arn: "",
      external_id: externalId,
      regions: "sa-east-1",
      is_management_account: false,
    },
    oci: {
      user_ocid: "",
      fingerprint: "",
      region: "",
      scope_regions: "",
      compartment_ocids: "",
      include_root_compartment: false,
      include_subcompartments: false,
      private_key_pem: "",
      private_key_password: "",
    },
  };
}

export function accountToForm(account) {
  const form = createEmptyAccountForm(account.provider);
  form.name = account.name;
  form.native_account_id = account.native_account_id;
  form.enabled = account.enabled;
  form.schedule_enabled = Boolean(account.schedule_enabled);
  form.scan_interval_hours = Number(account.scan_interval_hours);

  if (account.aws_configuration) {
    form.aws = {
      role_arn: account.aws_configuration.role_arn,
      external_id: account.aws_configuration.external_id,
      regions: account.aws_configuration.regions.join(", "),
      is_management_account: account.aws_configuration.is_management_account,
    };
  }

  if (account.oci_configuration) {
    form.oci = {
      user_ocid: account.oci_configuration.user_ocid,
      fingerprint: account.oci_configuration.fingerprint,
      region: account.oci_configuration.region,
      scope_regions: account.oci_configuration.scope_regions.join(", "),
      compartment_ocids: account.oci_configuration.compartment_ocids.join(", "),
      include_root_compartment: account.oci_configuration.include_root_compartment,
      include_subcompartments: account.oci_configuration.include_subcompartments,
      private_key_pem: "",
      private_key_password: "",
    };
  }

  return form;
}

export function buildCreateAccountPayload(form) {
  if (!SUPPORTED_ACCOUNT_PROVIDERS.includes(form.provider)) {
    throw new Error("Selecione AWS ou OCI.");
  }

  const common = {
    provider: form.provider,
    native_account_id: form.native_account_id.trim(),
    name: form.name.trim(),
    enabled: Boolean(form.enabled),
    schedule_enabled: Boolean(form.schedule_enabled),
    scan_interval_hours: Number(form.scan_interval_hours),
  };

  if (form.provider === "aws") {
    return {
      ...common,
      configuration: {
        role_arn: form.aws.role_arn.trim(),
        external_id: form.aws.external_id.trim(),
        regions: csvList(form.aws.regions),
        is_management_account: Boolean(form.aws.is_management_account),
      },
    };
  }

  const configuration = {
    user_ocid: form.oci.user_ocid.trim(),
    fingerprint: form.oci.fingerprint.trim(),
    region: form.oci.region.trim(),
    scope_regions: csvList(form.oci.scope_regions),
    compartment_ocids: csvList(form.oci.compartment_ocids),
    include_root_compartment: Boolean(form.oci.include_root_compartment),
    include_subcompartments: Boolean(form.oci.include_subcompartments),
    private_key_pem: form.oci.private_key_pem,
  };
  if (form.oci.private_key_password) {
    configuration.private_key_password = form.oci.private_key_password;
  }
  return { ...common, configuration };
}

function sameList(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function buildUpdateAccountPayload(account, form, options = {}) {
  const payload = {};
  if (form.name.trim() !== account.name) payload.name = form.name.trim();
  if (Boolean(form.enabled) !== account.enabled) payload.enabled = Boolean(form.enabled);
  if (Boolean(form.schedule_enabled) !== account.schedule_enabled) {
    payload.schedule_enabled = Boolean(form.schedule_enabled);
  }
  if (Number(form.scan_interval_hours) !== account.scan_interval_hours) {
    payload.scan_interval_hours = Number(form.scan_interval_hours);
  }

  if (account.provider === "aws" && account.aws_configuration) {
    const current = account.aws_configuration;
    const configuration = {};
    const regions = csvList(form.aws.regions);
    if (form.aws.role_arn.trim() !== current.role_arn) configuration.role_arn = form.aws.role_arn.trim();
    if (form.aws.external_id.trim() !== current.external_id) configuration.external_id = form.aws.external_id.trim();
    if (!sameList(regions, current.regions)) configuration.regions = regions;
    if (Boolean(form.aws.is_management_account) !== current.is_management_account) {
      configuration.is_management_account = Boolean(form.aws.is_management_account);
    }
    if (Object.keys(configuration).length) payload.configuration = configuration;
  }

  if (account.provider === "oci" && account.oci_configuration) {
    const current = account.oci_configuration;
    const configuration = {};
    const scopeRegions = csvList(form.oci.scope_regions);
    const compartments = csvList(form.oci.compartment_ocids);
    if (form.oci.user_ocid.trim() !== current.user_ocid) configuration.user_ocid = form.oci.user_ocid.trim();
    if (form.oci.region.trim() !== current.region) configuration.region = form.oci.region.trim();
    if (!sameList(scopeRegions, current.scope_regions)) configuration.scope_regions = scopeRegions;
    if (!sameList(compartments, current.compartment_ocids)) configuration.compartment_ocids = compartments;
    if (Boolean(form.oci.include_root_compartment) !== current.include_root_compartment) {
      configuration.include_root_compartment = Boolean(form.oci.include_root_compartment);
    }
    if (Boolean(form.oci.include_subcompartments) !== current.include_subcompartments) {
      configuration.include_subcompartments = Boolean(form.oci.include_subcompartments);
    }
    if (options.replaceCredentials) {
      configuration.private_key_pem = form.oci.private_key_pem;
      configuration.fingerprint = form.oci.fingerprint.trim();
      if (form.oci.private_key_password) {
        configuration.private_key_password = form.oci.private_key_password;
      }
    }
    if (Object.keys(configuration).length) payload.configuration = configuration;
  }

  return payload;
}

export function validateAccountForm(form, options = {}) {
  const errors = {};
  const creating = options.mode !== "edit";
  const replacing = Boolean(options.replaceCredentials);

  if (!String(form.name || "").trim() || String(form.name || "").trim().length < 2) {
    errors.name = "Informe um nome com pelo menos 2 caracteres.";
  }
  if (!SUPPORTED_ACCOUNT_PROVIDERS.includes(form.provider)) {
    errors.provider = "Selecione AWS ou OCI.";
    return errors;
  }
  if (![12, 24, 168].includes(Number(form.scan_interval_hours))) {
    errors.scan_interval_hours = "Selecione um intervalo de análise válido.";
  }

  if (form.provider === "aws") {
    if (!/^\d{12}$/.test(String(form.native_account_id || "").trim())) {
      errors.native_account_id = "AWS Account ID deve conter exatamente 12 dígitos.";
    }
    const roleArn = String(form.aws.role_arn || "").trim();
    if (!/^arn:aws[a-zA-Z-]*:iam::\d{12}:role\/.+/.test(roleArn)) {
      errors.role_arn = "Informe um Role ARN IAM válido.";
    } else if (
      /^\d{12}$/.test(String(form.native_account_id || "").trim())
      && roleArn.split(":")[4] !== String(form.native_account_id).trim()
    ) {
      errors.role_arn = "O Account ID do Role ARN deve ser o mesmo da conta.";
    }
    if (String(form.aws.external_id || "").trim().length < 16) {
      errors.external_id = "External ID deve possuir pelo menos 16 caracteres.";
    }
    if (!csvList(form.aws.regions).length) {
      errors.regions = "Informe pelo menos uma região AWS.";
    }
  }

  if (form.provider === "oci") {
    if (!String(form.native_account_id || "").trim().startsWith("ocid1.tenancy.")) {
      errors.native_account_id = "Informe um Tenancy OCID.";
    }
    if (!String(form.oci.user_ocid || "").trim().startsWith("ocid1.user.")) {
      errors.user_ocid = "Informe um User OCID.";
    }
    if (!String(form.oci.region || "").trim()) {
      errors.region = "Informe a região de conexão OCI.";
    }
    const compartments = csvList(form.oci.compartment_ocids);
    if (form.oci.include_subcompartments && !form.oci.include_root_compartment && !compartments.length) {
      errors.compartment_ocids = "Para incluir subcompartments, inclua a raiz ou ao menos um compartment-base.";
    }
    if (creating || replacing) {
      if (!String(form.oci.fingerprint || "").trim()) {
        errors.fingerprint = "Informe o fingerprint da API Signing Key.";
      }
      const pem = String(form.oci.private_key_pem || "");
      if (pem.length < 64 || pem.length > 65536) {
        errors.private_key_pem = "Informe uma chave privada PEM entre 64 bytes e 64 KiB.";
      }
    }
  }

  return errors;
}

export function filterCloudAccounts(accounts, provider, search) {
  const needle = String(search || "").trim().toLocaleLowerCase("pt-BR");
  return accounts.filter((account) => {
    if (provider && provider !== "all" && account.provider !== provider) return false;
    if (!needle) return true;
    return (
      account.name.toLocaleLowerCase("pt-BR").includes(needle)
      || account.native_account_id.toLocaleLowerCase("pt-BR").includes(needle)
    );
  });
}
