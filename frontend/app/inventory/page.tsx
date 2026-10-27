"use client";

import { Suspense, useMemo, type ReactNode } from "react";
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

const PRESENCE_OPTIONS = [
  { value: "active", label: "Active resources" },
  { value: "missing", label: "Missing resources" },
  { value: "all", label: "All presence states" },
];

function humanize(value?: string | null) {
  if (!value) return "—";
  return value
    .replaceAll("-", "_")
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function inventoryError(error: unknown, fallback: string) {
  if (!(error instanceof ApiError)) return fallback;
  if (error.status === 403) return "You do not have permission to view this inventory scope.";
  if (error.status === 422) return "One or more inventory filters are invalid.";
  if (error.status === 429) return "Inventory requests are temporarily rate limited. Try again shortly.";
  if (error.status >= 500) return "Inventory data is temporarily unavailable.";
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

function selectOptions(values?: string[]) {
  return (values ?? []).map((value) => ({ value, label: humanize(value) }));
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
            <Alert variant="danger" title="Unable to load Inventory" description={error} />
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
              emptyTitle="No resources match this scope"
              emptyDescription="Adjust the provider, account, region, resource type, status or search filters."
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
  const active = sort === field;
  const Icon = active ? (direction === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
  return (
    <Button
      variant="ghost"
      size="sm"
      trailingIcon={<Icon {...iconDefaults} />}
      aria-label={`Sort by ${label}${active ? `, currently ${direction}` : ""}`}
      onClick={() => onSort(field)}
    >
      {label}
    </Button>
  );
}

function ResourceRow({ resource }: { resource: InventoryResource }) {
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
        <span className={styles.secondary}>{resource.service || resource.native_resource_type || "Service unavailable"}</span>
      </TableCell>
      <TableCell>
        {resource.account_name || resource.native_account_id}
        <span className={styles.secondary}>{resource.native_account_id}</span>
      </TableCell>
      <TableCell>
        {resource.region || "Global / unavailable"}
        <span className={styles.secondary}>{resource.availability_zone || "No availability zone"}</span>
      </TableCell>
      <TableCell>
        <div className={styles.statusStack}>
          <StatusIndicator status={lifecycleTone(resource.lifecycle_status)} label={humanize(resource.lifecycle_status)} />
          {resource.native_status && resource.native_status.toLowerCase() !== resource.lifecycle_status.toLowerCase() ? (
            <span className={styles.secondary}>{resource.native_status}</span>
          ) : null}
        </div>
      </TableCell>
      <TableCell><StatusIndicator status={presenceTone(resource.presence_status)} label={humanize(resource.presence_status)} /></TableCell>
      <TableCell>
        {formatDateTime(resource.last_seen_at)}
        <span className={styles.secondary}>First seen {formatDateTime(resource.first_seen_at)}</span>
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
  return (
    <FilterBar
      aria-label="Inventory filters"
      clearAction={<Button variant="ghost" size="sm" onClick={onClear}>Clear filters</Button>}
    >
      <Input
        label="Search"
        value={state.search}
        placeholder="Name, ID, account, type or region"
        leadingIcon={<Search {...iconDefaults} />}
        onChange={(event) => onChange({ search: event.target.value, page: 1 })}
      />
      <ProviderSelector
        label="Provider"
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
        placeholder="All providers"
        clearLabel="All providers"
        searchable={false}
      />
      <AccountSelector
        label="Account"
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
        placeholder="All authorized accounts"
        clearLabel="All authorized accounts"
      />
      <Select
        label="Region"
        value={state.region}
        onChange={(event) => onChange({ region: event.target.value, page: 1 })}
        options={selectOptions(contextualOptions?.regions)}
      >
        <option value="">All regions</option>
      </Select>
      <Select
        label="Resource type"
        value={state.resourceType}
        onChange={(event) => onChange({ resourceType: event.target.value, page: 1 })}
        options={selectOptions(contextualOptions?.resource_types)}
      >
        <option value="">All resource types</option>
      </Select>
      <Select
        label="Service"
        value={state.service}
        onChange={(event) => onChange({ service: event.target.value, page: 1 })}
        options={selectOptions(contextualOptions?.services)}
      >
        <option value="">All services</option>
      </Select>
      <Select
        label="Lifecycle"
        value={state.lifecycleStatus}
        onChange={(event) => onChange({ lifecycleStatus: event.target.value, page: 1 })}
        options={selectOptions(contextualOptions?.lifecycle_statuses)}
      >
        <option value="">All lifecycle states</option>
      </Select>
      <Select
        label="Presence"
        value={state.presenceStatus}
        onChange={(event) => onChange({ presenceStatus: event.target.value, page: 1 })}
        options={PRESENCE_OPTIONS}
      />
    </FilterBar>
  );
}

function InventoryContent() {
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

  const queryFailure = resources.error ? inventoryError(resources.error, "Could not load Inventory resources.") : undefined;
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
      label: "Resources in view",
      value: resources.data?.total ?? "—",
      supportingText: state.presenceStatus === "active" ? "Currently observed resources" : "Matches the current Inventory filters",
      icon: <Boxes {...iconDefaults} />,
    },
    {
      label: "Cloud accounts",
      value: contextualOptions.data?.accounts.length ?? "—",
      supportingText: "Authorized accounts in the selected provider scope",
      icon: <Cloud {...iconDefaults} />,
    },
    {
      label: "Regions",
      value: contextualOptions.data?.regions.length ?? "—",
      supportingText: "Regions represented by persisted Inventory data",
      icon: <MapPin {...iconDefaults} />,
    },
    {
      label: "Resource types",
      value: contextualOptions.data?.resource_types.length ?? "—",
      supportingText: "Normalized resource types available in this scope",
      icon: <Layers3 {...iconDefaults} />,
    },
  ];

  const items = resources.data?.items ?? [];
  const hasTableState = resources.isLoading || Boolean(queryFailure) || items.length === 0;

  return (
    <div className={styles.page}>
      <PageHeader
        title="Inventory"
        description="Explore persisted AWS and OCI resources across authorized accounts, regions and resource types."
        actions={(
          <Button
            variant="outline"
            leadingIcon={<RefreshCw {...iconDefaults} />}
            loading={resources.isFetching || baseOptions.isFetching || contextualOptions.isFetching}
            onClick={refresh}
          >
            Refresh
          </Button>
        )}
      />

      {optionsFailure ? (
        <Alert
          variant="warning"
          title="Some filter options are unavailable"
          description={inventoryError(optionsFailure, "Could not load Inventory filter options.")}
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

      <Section title="Inventory overview" description="A concise view of the persisted resource scope currently selected.">
        <div className={styles.metricsGrid} aria-label="Inventory summary">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} {...metric} loading={resources.isLoading || contextualOptions.isLoading} />
          ))}
        </div>
      </Section>

      <Section
        title="Resource explorer"
        description="Search, sort and inspect normalized cloud resources without querying provider APIs from the browser."
        actions={resources.isFetching && !resources.isLoading ? <StatusIndicator status="pending" label="Updating" /> : undefined}
      >
        <div className={styles.tableMeta}>
          <span>{resources.data ? `${resources.data.total} resources` : "Resource count unavailable"}</span>
          <span>Default scope shows active resources only.</span>
        </div>
        <Table>
          <TableHeader>
            <TableRow staticRow>
              <TableHead><SortHeader field="name" label="Resource" sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="provider" label="Provider" sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="resource_type" label="Type / service" sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="account" label="Account" sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="region" label="Location" sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="lifecycle_status" label="Lifecycle" sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="presence_status" label="Presence" sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
              <TableHead><SortHeader field="last_seen_at" label="Last observed" sort={state.sort as InventorySortField} direction={state.direction as InventorySortDirection} onSort={onSort} /></TableHead>
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
              label="Rows per page"
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
        title="Inventory semantics"
        description="Inventory represents persisted cloud resources independently from Findings and Opportunities. Missing resources remain queryable for audit and troubleshooting, while the default view shows active resources."
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
