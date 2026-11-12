"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Calculator, Plus, Trash2 } from "lucide-react";
import { CurrencyDisplay, PageContainer, PageHeader } from "@/components/aven";
import { Alert, Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, Input, Select, Switch } from "@/components/ui";
import {
  compactIdentifier, decimalValue, estimateCalculator, fetchAwsOptions, fetchAwsRegions, fetchOciOptions,
  nonNegativePercent, positiveNumber,
  type AwsOption, type AwsOptionsResponse, type CalculatorEstimate, type CalculatorPeriod,
  type CalculatorRequest, type OciComputeOptions, type OciDbOptions, type PeriodMode,
  type PriceComponent, type Provider, type ResourceConfiguration, type Service, type VolumeInput,
} from "@/lib/calculator";
import styles from "./calculator.module.css";

type TextForm = Record<string, string>;
type Status = "initial" | "loading" | "ready" | "error";
const engineOptions = ["postgres", "mysql", "mariadb"];
const services: Record<Provider, Service[]> = { aws: ["ec2", "rds"], oci: ["compute", "db_system"] };

function initialFields(): TextForm {
  return {
    region: "", search: "", instance: "", os: "", engine: "postgres", deployment: "",
    volumeType: "gp3", capacity: "100", iops: "3000", throughput: "125",
    shape: "", ocpus: "1", memory: "8", bootSize: "100", bootVpu: "10",
    dbChoice: "", cpuCount: "4", dbStorage: "500",
    discount: "0", fx: "", tax: "13", quantity: "1", amount: "1",
    startAt: "", endAt: "",
  };
}
const initialVolume = (): VolumeInput => ({ size_gb: "100", vpus_per_gb: "10", count: 1 });

function AbortableError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}
function currency(value: string | null | undefined, unit: "USD" | "BRL") {
  return <CurrencyDisplay value={value} currency={unit} minimumFractionDigits={2} maximumFractionDigits={2} />;
}
function statusVariant(status: CalculatorEstimate["pricing_status"]) {
  return status === "priced" ? "success" : status === "partially_priced" ? "warning" : "danger";
}

export default function CalculatorPage() {
  const t = useTranslations("calculator");
  const locale = useLocale();
  const tx = (key: string) => t(key as Parameters<typeof t>[0]);
  const [provider, setProvider] = useState<Provider>("aws");
  const [service, setService] = useState<Service>("ec2");
  const [form, setForm] = useState<TextForm>(initialFields);
  const [periodMode, setPeriodMode] = useState<PeriodMode>("monthly");
  const [convert, setConvert] = useState(false);
  const [volumes, setVolumes] = useState<VolumeInput[]>([]);
  const [awsRegions, setAwsRegions] = useState<string[]>([]);
  const [awsOptions, setAwsOptions] = useState<AwsOptionsResponse | null>(null);
  const [ociCompute, setOciCompute] = useState<OciComputeOptions | null>(null);
  const [ociDb, setOciDb] = useState<OciDbOptions | null>(null);
  const [metadataStatus, setMetadataStatus] = useState<Status>("initial");
  const [metadataError, setMetadataError] = useState("");
  const [estimate, setEstimate] = useState<CalculatorEstimate | null>(null);
  const [estimateError, setEstimateError] = useState("");
  const [calculating, setCalculating] = useState(false);
  const [edited, setEdited] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  const requestNumber = useRef(0);

  const update = (field: string, value: string) => {
    invalidate();
    setForm((previous) => ({ ...previous, [field]: value }));
  };
  function invalidate() {
    requestNumber.current += 1;
    requestRef.current?.abort();
    requestRef.current = null;
    setCalculating(false);
    setEstimate(null);
    setEstimateError("");
    setEdited(true);
  }
  function reset(nextProvider: Provider, nextService: Service) {
    invalidate();
    setProvider(nextProvider);
    setService(nextService);
    setForm(initialFields());
    setVolumes([]);
    setConvert(false);
    setPeriodMode("monthly");
    setAwsOptions(null);
    setOciCompute(null);
    setOciDb(null);
    setMetadataStatus("initial");
    setMetadataError("");
  }
  function changeRegion(next: string) {
    invalidate();
    setForm((previous) => ({
      ...previous, region: next, instance: "", os: "", deployment: "", shape: "", dbChoice: "",
    }));
    setAwsOptions(null);
    setOciCompute(null);
    setOciDb(null);
  }

  // AWS regions must come from Pricing API; the browser never embeds a fictitious region catalog.
  useEffect(() => {
    if (provider !== "aws") return;
    const controller = new AbortController();
    setMetadataStatus("loading");
    setMetadataError("");
    fetchAwsRegions(controller.signal).then((data) => {
      if (controller.signal.aborted) return;
      setAwsRegions(data.items);
      setMetadataStatus("ready");
    }).catch((error) => {
      if (controller.signal.aborted || AbortableError(error)) return;
      setAwsRegions([]);
      setMetadataStatus("error");
      setMetadataError("regions");
    });
    return () => controller.abort();
  }, [provider]);

  const region = form.region.trim();
  const search = form.search.trim();
  useEffect(() => {
    if (provider !== "aws" || !region || search.length < 2 || (service !== "ec2" && service !== "rds")) {
      setAwsOptions(null);
      return;
    }
    const controller = new AbortController();
    setAwsOptions(null);
    setMetadataStatus("loading");
    setMetadataError("");
    const timer = window.setTimeout(() => {
      fetchAwsOptions(service, region, search, form.engine, controller.signal).then((data) => {
        if (controller.signal.aborted) return;
        setAwsOptions(data);
        setMetadataStatus("ready");
      }).catch((error) => {
        if (controller.signal.aborted || AbortableError(error)) return;
        setAwsOptions(null);
        setMetadataStatus("error");
        setMetadataError("options");
      });
    }, 350);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [provider, service, region, search, form.engine]);

  useEffect(() => {
    if (provider !== "oci" || !region || (service !== "compute" && service !== "db_system")) return;
    const controller = new AbortController();
    setMetadataStatus("loading");
    setMetadataError("");
    const timer = window.setTimeout(() => {
      const result = service === "compute"
        ? fetchOciOptions("compute", region, controller.signal)
        : fetchOciOptions("db_system", region, controller.signal);
      result.then((data) => {
        if (controller.signal.aborted) return;
        if (data.service === "compute") setOciCompute(data);
        else setOciDb(data);
        setMetadataStatus("ready");
      }).catch((error) => {
        if (controller.signal.aborted || AbortableError(error)) return;
        setMetadataStatus("error");
        setMetadataError("options");
      });
    }, 350);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [provider, service, region]);

  // Only advertise the combinations returned by the authenticated metadata endpoints.
  const ec2Combinations = useMemo(() => (awsOptions?.items ?? []).filter((item) => Boolean(item.instance_type && item.operating_system)), [awsOptions]);
  const rdsCombinations = useMemo(() => (awsOptions?.items ?? []).filter((item) => Boolean(item.instance_class && item.deployment)), [awsOptions]);
  const instanceOptions = Array.from(new Set(ec2Combinations.map((item) => item.instance_type!)));
  const ec2OsOptions = ec2Combinations.filter((item) => item.instance_type === form.instance).map((item) => item.operating_system!);
  const rdsClassOptions = Array.from(new Set(rdsCombinations.map((item) => item.instance_class!)));
  const deploymentOptions = rdsCombinations.filter((item) => item.instance_class === form.instance).map((item) => item.deployment!);
  const shapeOptions = ociCompute?.items ?? [];
  const selectedShape = shapeOptions.find((item) => item.shape === form.shape);
  const dbOptions = ociDb?.items ?? [];
  const dbOption = dbOptions[Number(form.dbChoice)] && form.dbChoice !== "" ? dbOptions[Number(form.dbChoice)] : null;

  function changeVolume(index: number, key: keyof VolumeInput, value: string) {
    invalidate();
    setVolumes((old) => old.map((volume, i) => i === index
      ? { ...volume, [key]: key === "count" ? Number(value) : value }
      : volume));
  }

  function buildRequest(): CalculatorRequest | null {
    const quantity = Number(form.quantity);
    if (!region || !Number.isInteger(quantity) || quantity < 1 || quantity > 100000) return null;
    let period: CalculatorPeriod = { mode: periodMode };
    if (["hours", "days", "weeks"].includes(periodMode)) {
      if (!positiveNumber(form.amount)) return null;
      const hours = Number(decimalValue(form.amount)) * (periodMode === "weeks" ? 168 : periodMode === "days" ? 24 : 1);
      if (hours > 5 * 366 * 24) return null;
      period = { mode: periodMode, amount: decimalValue(form.amount) };
    }
    if (periodMode === "custom") {
      if (!form.startAt || !form.endAt) return null;
      const start = new Date(form.startAt);
      const end = new Date(form.endAt);
      if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime())) return null;
      if (end.getTime() <= start.getTime() || end.getTime() - start.getTime() > 5 * 366 * 86400000) return null;
      period = { mode: "custom", start_at: start.toISOString(), end_at: end.toISOString() };
    }
    let config: ResourceConfiguration;
    if (provider === "aws" && service === "ec2") {
      if (!awsRegions.includes(region) || !ec2Combinations.some((o) => o.instance_type === form.instance && o.operating_system === form.os)) return null;
      if (!positiveNumber(form.capacity) || !["gp2", "gp3"].includes(form.volumeType)) return null;
      config = {
        service: "ec2", instance_type: form.instance, operating_system: form.os,
        purchase_option: "on_demand", tenancy: "shared",
        root_volume_gb: decimalValue(form.capacity), ebs_volume_type: form.volumeType as "gp2" | "gp3", ebs_volume_count: 1,
      };
      if (form.volumeType === "gp3") {
        const iops = Number(form.iops), throughput = Number(form.throughput);
        if (!Number.isInteger(iops) || iops < 3000 || iops > 80000 || !Number.isInteger(throughput) || throughput < 125 || throughput > 2000) return null;
        config.ebs_iops = iops;
        config.ebs_throughput_mbps = throughput;
      }
    } else if (provider === "aws" && service === "rds") {
      if (!awsRegions.includes(region) || !rdsCombinations.some((o) => o.instance_class === form.instance && o.deployment === form.deployment)) return null;
      if (!engineOptions.includes(form.engine) || !positiveNumber(form.capacity) || !["gp2", "gp3"].includes(form.volumeType)) return null;
      config = {
        service: "rds", instance_class: form.instance, engine: form.engine, deployment: form.deployment,
        storage_type: form.volumeType as "gp2" | "gp3", allocated_storage_gb: decimalValue(form.capacity),
      };
    } else if (provider === "oci" && service === "compute") {
      if (!selectedShape || !ociCompute?.operating_systems.includes(form.os)) return null;
      const cpu = Number(form.ocpus), memory = Number(form.memory);
      if (!Number.isInteger(cpu) || cpu < 1 || cpu > selectedShape.max_ocpus
        || !Number.isInteger(memory) || memory < cpu
        || memory > Math.min(selectedShape.max_memory_gb, cpu * selectedShape.max_memory_per_ocpu_gb)) return null;
      if (!positiveNumber(form.bootSize) || !ociCompute.vpu_tiers.includes(Number(form.bootVpu))) return null;
      if (volumes.some((v) => !positiveNumber(v.size_gb) || !ociCompute.vpu_tiers.includes(Number(v.vpus_per_gb))
        || !Number.isInteger(v.count) || v.count < 1 || v.count > 100)) return null;
      config = {
        service: "compute", shape: form.shape, ocpus: form.ocpus, memory_gb: form.memory,
        operating_system: form.os as "linux" | "windows",
        boot_volume: { size_gb: decimalValue(form.bootSize), vpus_per_gb: form.bootVpu, count: 1 },
        block_volumes: volumes.map((v) => ({ size_gb: decimalValue(v.size_gb), vpus_per_gb: v.vpus_per_gb, count: v.count })),
      };
    } else if (provider === "oci" && service === "db_system") {
      if (!dbOption || dbOption.shape !== ociDb?.new_provisioning_shape || dbOption.cpu_unit !== "ECPU") return null;
      const cpu = Number(form.cpuCount);
      if (!Number.isInteger(cpu) || cpu < 4 || cpu > 256 || cpu % 4 !== 0 || !positiveNumber(form.dbStorage)) return null;
      config = {
        service: "db_system", deployment_model: dbOption.deployment_model,
        shape: dbOption.shape, edition: dbOption.edition, license_model: dbOption.license_model,
        cpu_unit: "ECPU", cpu_count: form.cpuCount, storage_gb: decimalValue(form.dbStorage),
      };
    } else return null;

    const request: CalculatorRequest = { provider, region, quantity, period, resource_configuration: config };
    if (provider === "aws") {
      if (!nonNegativePercent(form.discount, 100) || !nonNegativePercent(form.tax, 1000)) return null;
      if (convert && (!positiveNumber(form.fx, 1000000) || decimalValue(form.fx).split(".")[1]?.length > 8)) return null;
      request.aws_financial = {
        discount_percent: decimalValue(form.discount), conversion_enabled: convert, tax_percent: decimalValue(form.tax),
        ...(convert ? { usd_brl_rate: decimalValue(form.fx) } : {}),
      };
    }
    return request;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    invalidate();
    const payload = buildRequest();
    if (!payload) {
      setEstimateError("validation");
      return;
    }
    const controller = new AbortController();
    requestRef.current = controller;
    const sequence = ++requestNumber.current;
    setCalculating(true);
    setEdited(false);
    try {
      const result = await estimateCalculator(payload, controller.signal);
      if (controller.signal.aborted || sequence !== requestNumber.current) return;
      setEstimate(result);
      setEstimateError("");
    } catch (error) {
      if (controller.signal.aborted || sequence !== requestNumber.current || AbortableError(error)) return;
      setEstimate(null);
      setEstimateError(error instanceof Error && "status" in error && error.status === 422 ? "validation" : "request");
    } finally {
      if (sequence === requestNumber.current) {
        setCalculating(false);
        requestRef.current = null;
      }
    }
  }

  function choice(label: string, value: string, options: Array<{ value: string; label: string }>, change: (v: string) => void, disabled = false, help?: string): ReactNode {
    return <Select label={label} value={value} placeholder={t("choose")} options={options}
      disabled={disabled} onChange={(e) => change(e.target.value)} helperText={help} />;
  }
  function numberField(label: string, key: string, minimum = "0", maximum?: string, step = "any"): ReactNode {
    return <Input label={label} type="number" inputMode="decimal" min={minimum} max={maximum} step={step}
      value={form[key] ?? ""} onChange={(event) => update(key, event.target.value)} />;
  }

  const showWaiting = !estimate && !calculating && !estimateError;
  const displayStatus = estimate ? tx("status." + estimate.pricing_status) : null;

  return (
    <PageContainer width="full" className={styles.page}>
      <PageHeader title={t("title")} description={t("description")} />
      <div className={styles.columns}>
        <form onSubmit={submit} className={styles.form}>
          <Card>
            <CardHeader><CardTitle>{t("configuration")}</CardTitle></CardHeader>
            <CardContent className={styles.formBody}>
              <div className={styles.fieldGrid}>
                {choice(t("provider"), provider, [
                  { value: "aws", label: t("aws") }, { value: "oci", label: t("oci") },
                ], (v) => reset(v as Provider, v === "aws" ? "ec2" : "compute"))}
                {choice(t("service"), service, services[provider].map((v) => ({ value: v, label: tx("services." + v) })),
                  (v) => reset(provider, v as Service))}
              </div>
              {provider === "aws"
                ? choice(t("region"), form.region, awsRegions.map((value) => ({ value, label: value })),
                    changeRegion, metadataStatus === "loading" && awsRegions.length === 0, t("awsRegionsHint"))
                : <Input label={t("region")} value={form.region} onChange={(event) => changeRegion(event.target.value)}
                    placeholder={t("ociRegionPlaceholder")} helperText={t("ociRegionHint")} maxLength={80} />}
              {metadataStatus === "error" && <Alert variant="warning" title={t("metadataError")} description={tx("errors." + metadataError)} />}
              {provider === "aws" && !awsRegions.length && metadataStatus === "loading" && <p className={styles.hint}>{t("loadingOptions")}</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>{t("technical")}</CardTitle></CardHeader>
            <CardContent className={styles.formBody}>
              {provider === "aws" && (
                <>
                  {service === "rds" && choice(t("engine"), form.engine, engineOptions.map((v) => ({ value: v, label: tx("engines." + v) })),
                    (v) => { invalidate(); setForm((old) => ({ ...old, engine: v, instance: "", deployment: "" })); setAwsOptions(null); })}
                  <Input label={t("searchClass")} value={form.search} onChange={(e) => {
                    invalidate(); setForm((old) => ({ ...old, search: e.target.value, instance: "", os: "", deployment: "" })); setAwsOptions(null);
                  }} placeholder={t("searchPlaceholder")} helperText={t("searchHint")} />
                  {search.length >= 2 && metadataStatus === "loading" && <p className={styles.hint}>{t("loadingOptions")}</p>}
                  {search.length >= 2 && metadataStatus === "ready" && !awsOptions?.items.length && <Alert variant="info" description={t("noOptions")} />}
                  {awsOptions && awsOptions.total > awsOptions.items.length && <p className={styles.hint}>{t("limitedResults")}</p>}
                  {choice(service === "ec2" ? t("instanceType") : t("instanceClass"), form.instance,
                    (service === "ec2" ? instanceOptions : rdsClassOptions).map((v) => ({ value: v, label: v })),
                    (v) => { invalidate(); setForm((old) => ({ ...old, instance: v, os: "", deployment: "" })); },
                    !awsOptions?.items.length)}
                  {service === "ec2" ? choice(t("operatingSystem"), form.os,
                    ec2OsOptions.map((v) => ({ value: v, label: tx("systems." + v) })), (v) => update("os", v), !form.instance)
                  : choice(t("deployment"), form.deployment,
                    deploymentOptions.map((v) => ({ value: v, label: tx("deployments." + v) })),
                    (v) => update("deployment", v), !form.instance)}
                  <div className={styles.rule} />
                  <h3 className={styles.sectionTitle}>{t("storage")}</h3>
                  <div className={styles.fieldGrid}>
                    {choice(t("volumeType"), form.volumeType, ["gp2", "gp3"].map((v) => ({ value: v, label: v })),
                      (v) => update("volumeType", v))}
                    {numberField(t("capacity"), "capacity", "0.01")}
                  </div>
                  {service === "ec2" && form.volumeType === "gp3" && <div className={styles.fieldGrid}>
                    {numberField(t("iops"), "iops", "3000", "80000", "1")}
                    {numberField(t("throughput"), "throughput", "125", "2000", "1")}
                  </div>}
                  {service === "rds" && <p className={styles.hint}>{t("rdsStorageHint")}</p>}
                </>
              )}
              {provider === "oci" && service === "compute" && (
                <>
                  {choice(t("shape"), form.shape, shapeOptions.map((item) => ({ value: item.shape, label: item.shape })),
                    (v) => update("shape", v), !ociCompute)}
                  {selectedShape && <p className={styles.hint}>{t("shapeLimits", { cpu: selectedShape.max_ocpus, ram: selectedShape.max_memory_gb })}</p>}
                  <div className={styles.fieldGrid}>
                    {numberField(t("ocpus"), "ocpus", "1", String(selectedShape?.max_ocpus ?? 94), "1")}
                    {numberField(t("memory"), "memory", "1", String(selectedShape?.max_memory_gb ?? 1024), "1")}
                  </div>
                  {choice(t("operatingSystem"), form.os,
                    (ociCompute?.operating_systems ?? []).map((v) => ({ value: v, label: tx("systems." + v) })),
                    (v) => update("os", v), !ociCompute)}
                  <div className={styles.rule} />
                  <h3 className={styles.sectionTitle}>{t("bootVolume")}</h3>
                  <div className={styles.fieldGrid}>
                    {numberField(t("capacity"), "bootSize", "0.01")}
                    {choice(t("vpu"), form.bootVpu, (ociCompute?.vpu_tiers ?? []).map((v) => ({ value: String(v), label: String(v) })),
                      (v) => update("bootVpu", v), !ociCompute)}
                  </div>
                  <div className={styles.headingRow}>
                    <h3 className={styles.sectionTitle}>{t("blockVolumes")}</h3>
                    <Button size="sm" variant="secondary" type="button" leadingIcon={<Plus size={16} />}
                      disabled={volumes.length >= 20} onClick={() => { invalidate(); setVolumes((old) => [...old, initialVolume()]); }}>
                      {t("addVolume")}
                    </Button>
                  </div>
                  {volumes.map((volume, index) => (
                    <div className={styles.volume} key={index}>
                      <div className={styles.headingRow}><strong>{t("volumeNumber", { number: index + 1 })}</strong>
                        <Button size="sm" variant="ghost" type="button" leadingIcon={<Trash2 size={16} />}
                          onClick={() => { invalidate(); setVolumes((old) => old.filter((_, i) => i !== index)); }}>{t("remove")}</Button>
                      </div>
                      <div className={styles.fieldGrid}>
                        <Input label={t("capacity")} type="number" min="0.01" step="any" value={volume.size_gb}
                          onChange={(e) => changeVolume(index, "size_gb", e.target.value)} />
                        {choice(t("vpu"), volume.vpus_per_gb,
                          (ociCompute?.vpu_tiers ?? []).map((v) => ({ value: String(v), label: String(v) })),
                          (v) => changeVolume(index, "vpus_per_gb", v), !ociCompute)}
                        <Input label={t("volumeCount")} type="number" min="1" max="100" step="1" value={volume.count}
                          onChange={(e) => changeVolume(index, "count", e.target.value)} />
                      </div>
                    </div>
                  ))}
                  <Alert variant="info" description={t("ociRegionDisclaimer")} />
                </>
              )}
              {provider === "oci" && service === "db_system" && (
                <>
                  {ociDb?.setup_required && <Alert variant="warning" title={t("dbSetupTitle")} description={t("dbSetupDescription")} />}
                  {choice(t("dbConfiguration"), form.dbChoice,
                    dbOptions.map((item, i) => ({
                      value: String(i),
                      label: [item.shape, tx("editions." + item.edition), tx("licenses." + item.license_model)].join(" · ")
                        + (item.complete_price_available ? "" : " · " + t("incomplete")),
                    })), (v) => update("dbChoice", v), !dbOptions.length)}
                  {dbOption && <div className={styles.definition}>
                    <span>{t("shape")}</span><strong>{dbOption.shape}</strong>
                    <span>{t("deployment")}</span><strong>{t("dbDeployment")}</strong>
                    <span>{t("edition")}</span><strong>{tx("editions." + dbOption.edition)}</strong>
                    <span>{t("license")}</span><strong>{tx("licenses." + dbOption.license_model)}</strong>
                  </div>}
                  <div className={styles.fieldGrid}>
                    {numberField(t("ecpus"), "cpuCount", "4", "256", "4")}
                    {numberField(t("dbStorage"), "dbStorage", "0.01")}
                  </div>
                  <p className={styles.hint}>{t("dbSkuDisclaimer")}</p>
                </>
              )}
              {!region && <p className={styles.hint}>{t("chooseRegionFirst")}</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>{t("usage")}</CardTitle></CardHeader>
            <CardContent className={styles.formBody}>
              {numberField(t("quantity"), "quantity", "1", "100000", "1")}
              {choice(t("period"), periodMode, (["monthly", "hours", "days", "weeks", "custom"] as PeriodMode[]).map((v) =>
                ({ value: v, label: tx("periods." + v) })), (v) => { invalidate(); setPeriodMode(v as PeriodMode); })}
              {["hours", "days", "weeks"].includes(periodMode) && numberField(t("duration"), "amount", "0.000001")}
              {periodMode === "custom" && <div className={styles.fieldGrid}>
                <Input label={t("start")} type="datetime-local" value={form.startAt} onChange={(e) => update("startAt", e.target.value)} />
                <Input label={t("end")} type="datetime-local" min={form.startAt} value={form.endAt}
                  onChange={(e) => update("endAt", e.target.value)} />
              </div>}
            </CardContent>
          </Card>

          {provider === "aws" && <Card>
            <CardHeader><CardTitle>{t("financial")}</CardTitle></CardHeader>
            <CardContent className={styles.formBody}>
              {numberField(t("discount"), "discount", "0", "100")}
              <Switch label={t("convert")} checked={convert} onCheckedChange={(v) => { invalidate(); setConvert(v); }} />
              {convert && <div className={styles.fieldGrid}>
                {numberField(t("fx"), "fx", "0.00000001", "1000000")}
                {numberField(t("tax"), "tax", "0", "1000")}
              </div>}
              <p className={styles.hint}>{t("discountDisclaimer")}</p>
            </CardContent>
          </Card>}
          <div className={styles.actions}>
            {estimateError === "validation" && <Alert variant="danger" description={t("errors.validation")} />}
            <Button type="submit" loading={calculating} leadingIcon={<Calculator size={18} />}>
              {t("calculate")}
            </Button>
          </div>
        </form>

        <div className={styles.results} aria-live="polite">
          <Card>
            <CardHeader><div className={styles.headingRow}>
              <CardTitle>{t("summary")}</CardTitle>
              {estimate && <Badge variant={statusVariant(estimate.pricing_status)}>{displayStatus}</Badge>}
            </div></CardHeader>
            <CardContent className={styles.resultBody}>
              {calculating && <p className={styles.hint}>{t("calculating")}</p>}
              {showWaiting && <EmptyState icon={<Calculator size={24} />} title={t("initialTitle")}
                description={edited ? t("recalculateHint") : t("initialDescription")} />}
              {estimateError === "request" && <Alert variant="danger" title={t("errors.title")} description={t("errors.request")} />}
              {estimate && <>
                {estimate.pricing_status === "priced" ? (
                  <div className={styles.metricGroup}>
                    <div className={styles.metric}>
                      <span>{t("monthly")}</span>
                      <strong>{currency(estimate.monthly_final_cost, estimate.final_currency)}</strong>
                    </div>
                    <div className={styles.metric}>
                      <span>{t("periodCost")}</span>
                      <strong>{currency(estimate.period_final_cost, estimate.final_currency)}</strong>
                    </div>
                    {estimate.period_duration_hours != null && <p className={styles.hint}>{t("hoursLabel", { hours: new Intl.NumberFormat(locale, { maximumFractionDigits: 3 }).format(Number(estimate.period_duration_hours)) })}</p>}
                  </div>
                ) : <Alert variant="warning" title={t("incomplete")} description={t("notFinal")} />}
                {estimate.pricing_status !== "priced" && <div className={styles.knownGrid}>
                  <div className={styles.definition}><span>{t("knownMonthly")}</span>
                    <strong>{currency(estimate.monthly_known_subtotal, estimate.pricing_currency)}</strong></div>
                  <div className={styles.definition}><span>{t("knownPeriod")}</span>
                    <strong>{currency(estimate.period_known_subtotal, estimate.pricing_currency)}</strong></div>
                </div>}
                <div className={styles.rule} />
                <div className={styles.definition}>
                  <span>{t("currency")}</span><strong>{estimate.final_currency}</strong>
                  <span>{t("statusLabel")}</span><strong>{displayStatus}</strong>
                  {estimate.pricing_reference_date && <>
                    <span>{t("reference")}</span><strong>{new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(estimate.pricing_reference_date))}</strong>
                  </>}
                  {estimate.pricing_status === "priced" && estimate.provider === "aws" && <>
                    <span>{t("originalMonthly")}</span><strong>{currency(estimate.monthly_original_cost, "USD")}</strong>
                    <span>{t("originalPeriod")}</span><strong>{currency(estimate.period_original_cost, "USD")}</strong>
                    <span>{t("discountMonthly")}</span><strong>{currency(estimate.monthly_discount_amount, "USD")}</strong>
                    <span>{t("discountPeriod")}</span><strong>{currency(estimate.period_discount_amount, "USD")}</strong>
                    <span>{t("netMonthly")}</span><strong>{currency(estimate.monthly_net_cost, "USD")}</strong>
                    <span>{t("netPeriod")}</span><strong>{currency(estimate.period_net_cost, "USD")}</strong>
                    {estimate.conversion_enabled && <>
                      <span>{t("fx")}</span><strong>{estimate.usd_brl_rate ?? "—"}</strong>
                      <span>{t("taxMonthly")}</span><strong>{currency(estimate.monthly_tax_amount, "BRL")}</strong>
                      <span>{t("taxPeriod")}</span><strong>{currency(estimate.period_tax_amount, "BRL")}</strong>
                    </>}
                  </>}
                </div>
                {estimate.missing_pricing_components.length > 0 && <Alert variant="warning" title={t("missingPrices")} description={
                  <span className={styles.codeWrap}>{estimate.missing_pricing_components.map((v) => compactIdentifier(v, 80)).join(", ")}</span>
                } />}
                {estimate.warnings.length > 0 && <div className={styles.warnings}>
                  {estimate.warnings.map((warning, i) => <p key={warning + i} className={styles.hint}>
                    {(t.has as (key: string) => boolean)("warnings." + warning) ? tx("warnings." + warning) : t("genericWarning")}
                  </p>)}
                </div>}
              </>}
            </CardContent>
          </Card>
        </div>
      </div>

      {estimate && <Card>
        <CardHeader><CardTitle>{t("breakdown")}</CardTitle></CardHeader>
        <CardContent>
          {!estimate.pricing_components.length ? <EmptyState title={t("noComponents")} description={t("notFinal")} /> : (
            <div className={styles.tableScroll} role="region" aria-label={t("breakdown")} tabIndex={0}>
              <table className={styles.table}>
                <thead><tr><th>{t("component")}</th><th>{t("sku")}</th><th>{t("unit")}</th>
                  <th>{t("unitPrice")}</th><th>{t("monthlyUnits")}</th><th>{t("periodUnits")}</th>
                  <th>{t("monthly")}</th><th>{t("periodCost")}</th><th>{t("statusLabel")}</th></tr></thead>
                <tbody>{estimate.pricing_components.map((component: PriceComponent, index) => (
                  <tr key={component.sku + index}>
                    <td>{component.description ?? component.service}</td>
                    <td><span className={styles.identifier} title={component.sku}>{compactIdentifier(component.sku)}</span></td>
                    <td>{component.unit}</td>
                    <td>{currency(component.unit_price, component.currency)}</td>
                    <td>{component.monthly_units ?? "—"}</td>
                    <td>{component.period_units ?? "—"}</td>
                    <td>{currency(component.monthly_original_cost, component.currency)}</td>
                    <td>{currency(component.period_original_cost, component.currency)}</td>
                    <td><Badge variant={component.pricing_status === "priced" ? "success" : "warning"}>
                      {component.pricing_status ? tx("status." + component.pricing_status) : t("unavailable")}
                    </Badge></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <p className={styles.hint}>{t("sourceHint")}</p>
          {estimate.pricing_components.some((item) => item.source) && <details className={styles.provenance}>
            <summary>{t("provenance")}</summary>
            {estimate.pricing_components.map((item, index) => <p key={index} className={styles.codeWrap}>
              {item.sku}: {item.source ?? "—"} · {item.effective_from ?? "—"} · {item.effective_until ?? "—"}
            </p>)}
          </details>}
        </CardContent>
      </Card>}
    </PageContainer>
  );
}
