"use client";

import { Suspense, useMemo, type ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import {formatLocaleDateTime} from "@/i18n/formatters.mjs";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Boxes,
  Cloud,
  Layers3,
  MapPin,
  RefreshCw,
  Search,
} from "lucide-react";
import {
  AccountSelector,
  DataState,
  FilterBar,
  MetricCard,
  PageHeader,
  ProviderBadge,
  ProviderSelector,
  ResourceIdentifier,
  Section,
  StatusIndicator,
} from "@/components/aven";
import {
  Alert,
  Button,
  Input,
  Pagination,
  Select,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { iconDefaults } from "@/lib/iconography";
import {
  buildInventoryApiQuery,
  buildInventoryOptionsQuery,
  parseInventorySearchParams,
  patchInventoryUrl,
} from "@/lib/inventory-query.mjs";
import type {
  InventoryOptions,
  InventoryPage,
  InventoryResource,
  InventorySortDirection,
  InventorySortField,
} from "@/lib/inventory";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";
import styles from "./inventory.module.css";

function useLifecycleLabels() {
  const t = useTranslations("inventory");
  return {
    running: t("lifecycle.running"), active: t("lifecycle.active"), available: t("lifecycle.available"),
    attached: t("lifecycle.attached"), ready: t("lifecycle.ready"), pending: t("lifecycle.pending"),
    creating: t("lifecycle.creating"), starting: t("lifecycle.starting"), stopping: t("lifecycle.stopping"),
    provisioning: t("lifecycle.provisioning"), updating: t("lifecycle.updating"), failed: t("lifecycle.failed"),
    error: t("lifecycle.error"), faulty: t("lifecycle.faulty"), stopped: t("lifecycle.stopped"),
    inactive: t("lifecycle.inactive"), detached: t("lifecycle.detached"), terminated: t("lifecycle.terminated"),
    deleted: t("lifecycle.deleted"),
  } as Record<string, string>;
}

function lifecycleLabel(value: string, labels: Record<string,string>) {
  return labels[value.toLowerCase()] ?? humanize(value);
}


function humanize(value?: string | null) {
  if (!value) return "—";
  return value
    .replaceAll("-", "_")
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function formatDateTime(value?: string | null, locale = "pt-BR") {
  return formatLocaleDateTime(value, locale, {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", dateStyle: undefined, timeStyle: undefined,
  });
}

function inventoryError(error: unknown, fallback: string, messages: { forbidden: string; invalid: string; limited: string; unavailable: string }) {
  if (!(error instanceof ApiError)) return fallback;
  if (error.status === 403) return messages.forbidden;
  if (error.status === 422) return messages.invalid;
  if (error.status === 429) return messages.limited;
  if (error.status >= 500) return messages.unavailable;
  return error.message || fallback;
}

function lifecycleTone(status: string) {
  const normalized = status.toLowerCase();
  if (["running", "active", "available", "attached", "ready"].includes(normalized)) return "success" as const;
  if (["pending", "creating", "starting", "stopping", "provisioning", "updating"].includes(normalized)) return "pending" as const;
  if (["failed", "error", "faulty"].includes(normalized)) return "danger" as const;
  if (["stopped", "inactive", "detached", "terminated", "deleted"].includes(normalized)) return "warning" as const;
  return "neutral" as const;
}

function presenceTone(status: string) {
  if (status.toLowerCase() === "active") return "success" as const;
  if (status.toLowerCase() === "missing") return "danger" as const;
  return "neutral" as const;
}

function rawOptions(values: string[] | undefined, allLabel: string) {
  return [
    { value: "", label: allLabel },
    ...(values ?? []).map((value) => ({ value, label: value })),
  ];
}

function humanizedOptions(values: string[] | undefined, allLabel: string, labelFor: (value: string) => string = humanize) {
  return [
    { value: "", label: allLabel },
    ...(values ?? []).map((value) => ({ value, label: labelFor(value) })),
  ];
}

function accountOptions(options?: InventoryOptions, provider?: string) {
  return (options?.accounts ?? [])
    .filter((account) => !provider || account.provider === provider)
    .map((account) => ({
      value: String(account.id),
      label: account.name || account.native_account_id,
      accountId: account.native_account_id,
      provider: account.provider.toUpperCase(),
      searchTerms: [account.native_account_id, account.provider],
    }));
}

function providerOptions(options?: InventoryOptions) {
  return (options?.providers ?? []).map((provider) => ({
    value: provider,
    label: provider.toUpperCase(),
  }));
}

function InventoryTableState({ loading, error, empty }: { loading: boolean; error?: string; empty: boolean }) {
  const t = useTranslations("inventory");
  if (loading) {
    return (
      <TableBody>
        {Array.from({ length: 6 }, (_, index) => (
          <TableRow key={index} staticRow>
            <TableCell colSpan={8}><Skeleton /></TableCell>
          </TableRow>
        ))}
      </TableBody>
    );
  }

  if (error) {
    return (
      <TableBody>
        <TableRow staticRow>
          <TableCell colSpan={8}>
            <Alert variant="danger" title={t("states.loadError")} description={error} />
          </TableCell>
        </TableRow>
      </TableBody>
    );
  }

  if (empty) {
    return (
      <TableBody>
        <TableRow staticRow>
          <TableCell colSpan={8}>
            <DataState
              empty
              emptyTitle={t("states.emptyTitle")}
              emptyDescription={t("states.emptyDescription")}
            >
              <span />
            </DataState>
          </TableCell>
        </TableRow>
      </TableBody>
    );
  }

  return null;
}

function SortHeader({
  field,
  label,
  sort,
  direction,
  onSort,
}: {
  field: InventorySortField;
  label: string;
  sort: InventorySortField;
  direction: InventorySortDirection;
  onSort: (field: InventorySortField) => void;
}) {
  const t = useTranslations("inventory");
  const active = sort === field;
  const Icon = active ? (direction === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
  return (
    <Button
      variant="ghost"
      size="sm"
      trailingIcon={<Icon {...iconDefaults} />}
      aria-label={active ? t("table.sortCurrent", { label, direction: t(`table.${direction}`) }) : t("table.sortBy", { label })}
      onClick={() => onSort(field)}
    >
      {label}
    </Button>
  );
}

function ResourceRow({ resource }: { resource: InventoryResource }) {
  const t = useTranslations("inventory");
  const locale = useLocale();
  const lifecycle = useLifecycleLabels();
  const displayName = resource.name || resource.resource_id;
  return (
    <TableRow>
      <TableCell>
        <ResourceIdentifier
          primary={displayName}
          technicalId={resource.name ? resource.resource_id : undefined}
          copyValue={resource.resource_id}
        />
      </TableCell>
      <TableCell><ProviderBadge provider={resource.provider} /></TableCell>
      <TableCell>
        {humanize(resource.resource_type)}
        <span className={styles.secondary}>{resource.service || resource.native_resource_type || t("table.serviceUnavailable")}</span>
      </TableCell>
      <TableCell>
        {resource.account_name || resource.native_account_id}
        {resource.account_name ? <span className={styles.secondary}>{resource.native_account_id}</span> : null}
      </TableCell>
      <TableCell>
        {resource.region || t("table.regionUnavailable")}
        <span className={styles.secondary}>{resource.availability_zone || t("table.noZone")}</span>
      </TableCell>
      <TableCell>
        <div className={styles.statusStack}>
          <StatusIndicator status={lifecycleTone(resource.lifecycle_status)} label={lifecycleLabel(resource.lifecycle_status, lifecycle)} />
          {resource.native_status && resource.native_status.toLowerCase() !== resource.lifecycle_status.toLowerCase() ? (
            <span className={styles.secondary}>{resource.native_status}</span>
          ) : null}
        </div>
      </TableCell>
      <TableCell><StatusIndicator status={presenceTone(resource.presence_status)} label={resource.presence_status === "active" ? t("presence.active") : resource.presence_status === "missing" ? t("presence.missing") : humanize(resource.presence_status)} /></TableCell>
      <TableCell>
        {formatDateTime(resource.last_seen_at, locale)}
        <span className={styles.secondary}>{t("table.firstSeen")} {formatDateTime(resource.first_seen_at, locale)}</span>
      </TableCell>
    </TableRow>
  );
}

function InventoryFilters({
  state,
  baseOptions,
  contextualOptions,
  loading,
  onChange,
  onClear,
}: {
  state: ReturnType<typeof parseInventorySearchParams>;
  baseOptions?: InventoryOptions;
  contextualOptions?: InventoryOptions;
  loading: boolean;
  onChange: (changes: Partial<ReturnType<typeof parseInventorySearchParams>>) => void;
  onClear: () => void;
}) {
  const t = useTranslations("inventory");
  const lifecycle = useLifecycleLabels();
  return (
    <FilterBar
      aria-label={t("filters.aria")}
      clearAction={<Button variant="ghost" size="sm" onClick={onClear}>{t("filters.clear")}</Button>}
    >
      <Input
        label={t("filters.search")}
        value={state.search}
        placeholder={t("filters.searchPlaceholder")}
        leadingIcon={<Search {...iconDefaults} />}
        onChange={(event) => onChange({ search: event.target.value, page: 1 })}
      />
      <ProviderSelector
        label={t("filters.provider")}
        value={state.provider}
        onChange={(provider) => onChange({
          provider,
          account: "",
          region: "",
          resourceType: "",
          lifecycleStatus: "",
          service: "",
          page: 1,
        })}
        options={providerOptions(baseOptions)}
        loading={loading}
        placeholder={t("filters.allProviders")}
        clearLabel={t("filters.allProviders")}
        searchable={false}
      />
      <AccountSelector
        label={t("filters.account")}
        value={state.account}
        onChange={(account) => onChange({
          account,
          region: "",
          resourceType: "",
          lifecycleStatus: "",
          service: "",
          page: 1,
        })}
        options={accountOptions(baseOptions, state.provider)}
        loading={loading}
        placeholder={t("filters.allAccounts")}
        clearLabel={t("filters.allAccounts")}
      />
      <Select
        label={t("filters.region")}
        value={state.region}
        onChange={(event) => onChange({ region: event.target.value, page: 1 })}
        options={rawOptions(contextualOptions?.regions, t("filters.allRegions"))}
      />
      <Select
        label={t("filters.resourceType")}
        value={state.resourceType}
        onChange={(event) => onChange({ resourceType: event.target.value, page: 1 })}
        options={humanizedOptions(contextualOptions?.resource_types, t("filters.allTypes"))}
      />
      <Select
        label={t("filters.service")}
        value={state.service}
        onChange={(event) => onChange({ service: event.target.value, page: 1 })}
        options={rawOptions(contextualOptions?.services, t("filters.allServices"))}
      />
      <Select
        label={t("filters.lifecycle")}
        value={state.lifecycleStatus}
        onChange={(event) => onChange({ lifecycleStatus: event.target.value, page: 1 })}
        options={humanizedOptions(contextualOptions?.lifecycle_statuses, t("filters.allLifecycle"), (value) => lifecycleLabel(value, lifecycle))}
      />
      <Select
        label={t("filters.presence")}
        value={state.presenceStatus}
        onChange={(event) => onChange({ presenceStatus: event.target.value, page: 1 })}
        options={[{value:"active",label:t("presence.activeResources")},{value:"missing",label:t("presence.missingResources")},{value:"all",label:t("presence.all")}]}
      />
    </FilterBar>
  );
}

function InventoryContent() {
  const t = useTranslations("inventory");
  const errors = { forbidden: t("errors.forbidden"), invalid: t("errors.invalid"), limited: t("errors.limited"), unavailable: t("errors.unavailable") };
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const state = useMemo(() => parseInventorySearchParams(searchParams), [searchParams]);
  const update = (changes: Partial<typeof state>) => router.replace(`${pathname}${patchInventoryUrl(state, changes)}`, { scroll: false });
  const clear = () => router.replace(pathname, { scroll: false });

  const resourceQuery = buildInventoryApiQuery(state);
  const contextualOptionsQuery = buildInventoryOptionsQuery(state);

  const resources = useApiQuery<InventoryPage>({
    key: queryKeys.inventory.list(resourceQuery),
    path: `/inventory/resources?${resourceQuery}`,
    keepPreviousData: true,
    placeholderIdentity: JSON.stringify({ ...state, page: 0 }),
    ...cachePolicy.operational,
  });
  const baseOptions = useApiQuery<InventoryOptions>({
    key: queryKeys.inventory.options("", ""),
    path: "/inventory/options",
    ...cachePolicy.metadata,
  });
  const contextualOptions = useApiQuery<InventoryOptions>({
    key: queryKeys.inventory.options(state.provider, state.account),
    path: `/inventory/options${contextualOptionsQuery ? `?${contextualOptionsQuery}` : ""}`,
    ...cachePolicy.metadata,
  });

  const queryFailure = resources.error ? inventoryError(resources.error, t("errors.resources"), errors) : undefined;
  const optionsFailure = baseOptions.error || contextualOptions.error;
  const refresh = () => {
    void resources.refetch();
    void baseOptions.refetch();
    void contextualOptions.refetch();
  };

  const onSort = (field: InventorySortField) => {
    if (state.sort === field) {
      update({ direction: state.direction === "asc" ? "desc" : "asc", page: 1 });
      return;
    }
    update({ sort: field, direction: field === "last_seen_at" ? "desc" : "asc", page: 1 });
  };

  const metrics: Array<{ label: string; value: ReactNode; supportingText: ReactNode; icon: ReactNode }> = [
    {
      label: t("metrics.resources"),
      value: resources.data?.total ?? "—",
      supportingText: state.presenceStatus === "active" ? t("metrics.currentlyObserved") : t("metrics.matchesFilters"),
      icon: <Boxes {...iconDefaults} />,
    },
    {
      label: t("metrics.accounts"),
      value: contextualOptions.data?.accounts.length ?? "—",
      supportingText: t("metrics.accountsDescription"),
      icon: <Cloud {...iconDefaults} />,
    },
    {
      label: t("metrics.regions"),
      value: contextualOptions.data?.regions.length ?? "—",
      supportingText: t("metrics.regionsDescription"),
      icon: <MapPin {...iconDefaults} />,
    },
    {
      label: t("metrics.types"),
      value: contextualOptions.data?.resource_types.length ?? "—",
      supportingText: t("metrics.typesDescription"),
      icon: <Layers3 {...iconDefaults} />,
    },
  ];

  const items = resources.data?.items ?? [];
  const hasTableState = resources.isLoading || Boolean(queryFailure) || items.length === 0;

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={(
          <Button
            variant="outline"
            leadingIcon={<RefreshCw {...iconDefaults} />}
            loading={resources.isFetching || baseOptions.isFetching || contextualOptions.isFetching}
            onClick={refresh}
          >
            {t("actions.refresh")}
          </Button>
        )}
      />

      {optionsFailure ? (
        <Alert
          variant="warning"
          title={t("states.optionsWarning")}
          description={inventoryError(optionsFailure, t("errors.options"), errors)}
        />
      ) : null}

      <InventoryFilters
        state={state}
        baseOptions={baseOptions.data}
        contextualOptions={contextualOptions.data}
        loading={baseOptions.isLoading}
        onChange={update}
        onClear={clear}
      />

      <Section title={t("overview.title")} description={t("overview.description")}>
        <div className={styles.metricsGrid} aria-label={t("overview.aria")}>
          {metrics.map((metric) => (
            <MetricCard key={metric.label} {...metric} loading={resources.isLoading || contextualOptions.isLoading} />
          ))}
        </div>
      </Section>

      <Section
        title={t("table.title")}
        description={t("table.description")}
        actions={resources.isFetching && !resources.isLoading ? <StatusIndicator status="pending" label={t("states.updating")} /> : undefined}
      >
        <div className={styles.tableMeta}>
          <span>{resources.data ? t("table.resourceCount", { count: resources.data.total }) : t("table.countUnavailable")}</span>
          <span>{t("table.defaultScope")}</span>
        </div>
        <Table>
          <TableHeader>
            <TableRow staticRow>
              <TableHead><SortHeader field="name" label={t("table.resource")} sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="provider" label={t("filters.provider")} sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="resource_type" label={t("table.typeService")} sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="account" label={t("filters.account")} sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="region" label={t("table.location")} sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="lifecycle_status" label={t("filters.lifecycle")} sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="presence_status" label={t("filters.presence")} sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="last_seen_at" label={t("table.lastObserved")} sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
            </TableRow>
          </TableHeader>
          {hasTableState ? (
            <InventoryTableState loading={resources.isLoading} error={queryFailure} empty={!resources.isLoading && !queryFailure && items.length === 0} />
          ) : (
            <TableBody>{items.map((resource) => <ResourceRow key={resource.id} resource={resource} />)}</TableBody>
          )}
        </Table>

        {resources.data ? (
          <div className={styles.paginationRow}>
            <Select
              label={t("table.rowsPerPage")}
              value={String(state.pageSize)}
              onChange={(event) => update({ pageSize: Number(event.target.value), page: 1 })}
              options={[
                { value: "20", label: "20" },
                { value: "50", label: "50" },
                { value: "100", label: "100" },
              ]}
            />
            {resources.data.total_pages > 1 ? (
              <Pagination page={resources.data.page} pageCount={resources.data.total_pages} onPageChange={(page) => update({ page })} />
            ) : null}
          </div>
        ) : null}
      </Section>

      <Alert
        variant="info"
        title={t("semantics.title")}
        description={t("semantics.description")}
      />
    </div>
  );
}

export default function InventoryPage() {
  return (
    <Suspense fallback={<div className={styles.page}><Skeleton /><Skeleton /><Skeleton /></div>}>
      <InventoryContent />
    </Suspense>
  );
}
