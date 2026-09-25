"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Building2,
  ChevronLeft,
  ChevronRight,
  Cloud,
  Filter,
  ListFilter,
  RefreshCw,
  Search,
  Tags,
  WalletCards,
  X,
} from "lucide-react";
import { OpportunityDecisionDialog } from "@/components/opportunity-decision-dialog";
import type { OpportunityDecisionAction } from "@/components/opportunity-decision-dialog";
import { OpportunityDetail } from "@/components/opportunity-detail";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { api, formatDate, usd } from "@/lib/api";
import {
  buildLifecycleRequest,
  buildOpportunityApiQuery,
  buildOpportunityStatsQuery,
  parseOpportunitySearchParams,
  patchOpportunityUrl,
} from "@/lib/opportunity-query.mjs";
import type { OpportunityQueryState } from "@/lib/opportunity-query.mjs";
import type {
  AwsAccount,
  CollectionRun,
  Finding,
  OpportunityPage,
  OpportunityStats,
  Policy,
} from "@/lib/types";

const statusTabs = [
  { value: "open", label: "Abertas" },
  { value: "treated", label: "Tratadas" },
  { value: "rejected", label: "Rejeitadas" },
] as const;

const rejectionFallback = "Não foi possível atualizar a oportunidade. Nenhuma alteração foi aplicada.";

const sortOptions = [
  ["last_seen_at", "Última detecção"],
  ["first_seen_at", "Primeira detecção"],
  ["severity", "Severidade"],
  ["estimated_savings", "Impacto financeiro"],
  ["created_at", "Criação"],
] as const;

function pageWindow(page: number, totalPages: number) {
  if (totalPages <= 1) return totalPages ? [1] : [];
  const start = Math.max(1, Math.min(page - 2, totalPages - 4));
  const end = Math.min(totalPages, start + 4);
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

function savingsLabel(finding: Finding) {
  return finding.rule_key === "cost_growth_anomaly"
    ? "Não estimada"
    : `${usd(finding.estimated_monthly_savings)}/mês`;
}

function SkeletonRows() {
  return (
    <tbody aria-hidden="true">
      {Array.from({ length: 6 }, (_, index) => (
        <tr key={index} className="opportunity-skeleton-row">
          <td><span className="skeleton-box skeleton-check" /></td>
          <td><span className="skeleton-box skeleton-title" /><span className="skeleton-box skeleton-line" /></td>
          <td><span className="skeleton-box skeleton-line" /><span className="skeleton-box skeleton-line short" /></td>
          <td><span className="skeleton-box skeleton-pill" /></td>
          <td><span className="skeleton-box skeleton-line short" /></td>
          <td><span className="skeleton-box skeleton-line" /></td>
          <td><span className="skeleton-box skeleton-pill" /></td>
        </tr>
      ))}
    </tbody>
  );
}

export default function OpportunitiesPage() {
  return (
    <Suspense fallback={<div className="opportunities-boot" role="status">Carregando oportunidades…</div>}>
      <OpportunitiesContent />
    </Suspense>
  );
}

function OpportunitiesContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();
  const state = useMemo<OpportunityQueryState>(
    () => parseOpportunitySearchParams(searchKey),
    [searchKey],
  );
  const listQuery = useMemo(() => buildOpportunityApiQuery(state), [
    state.accountId, state.collectionRunId, state.order, state.page, state.pageSize,
    state.provider, state.region, state.resourceId, state.rule, state.search,
    state.severity, state.sort, state.status,
  ]);
  const statsQuery = useMemo(() => buildOpportunityStatsQuery(state), [
    state.accountId, state.collectionRunId, state.provider, state.region,
    state.resourceId, state.rule, state.search, state.severity,
  ]);

  const [findings, setFindings] = useState<Finding[]>([]);
  const [accounts, setAccounts] = useState<AwsAccount[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [collectionRuns, setCollectionRuns] = useState<CollectionRun[]>([]);
  const [stats, setStats] = useState<OpportunityStats>({ open: 0, treated: 0, rejected: 0 });
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [filtersLoading, setFiltersLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [filterError, setFilterError] = useState("");
  const [message, setMessage] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [searchInput, setSearchInput] = useState(state.search);
  const [regionInput, setRegionInput] = useState(state.region);
  const [accountInput, setAccountInput] = useState(state.accountId);
  const [decision, setDecision] = useState<{
    action: OpportunityDecisionAction;
    ids: string[];
    bulk: boolean;
  } | null>(null);
  const [decisionSaving, setDecisionSaving] = useState(false);
  const [decisionError, setDecisionError] = useState("");
  const selectAllRef = useRef<HTMLInputElement>(null);

  const updateUrl = useCallback((patch: Record<string, string | number | null | undefined>, options?: { resetPage?: boolean; push?: boolean }) => {
    const params = patchOpportunityUrl(searchKey, patch, { resetPage: options?.resetPage });
    const href = `${pathname}${params.size ? `?${params.toString()}` : ""}`;
    if (options?.push) router.push(href, { scroll: false });
    else router.replace(href, { scroll: false });
  }, [pathname, router, searchKey]);

  useEffect(() => setSearchInput(state.search), [state.search]);
  useEffect(() => setRegionInput(state.region), [state.region]);
  useEffect(() => setAccountInput(state.accountId), [state.accountId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const value = searchInput.trim();
      if (value !== state.search) updateUrl({ search: value });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [searchInput, state.search, updateUrl]);

  useEffect(() => {
    const controller = new AbortController();
    setFiltersLoading(true);
    setFilterError("");
    Promise.all([
      api<AwsAccount[]>("/accounts", { signal: controller.signal }),
      api<Policy[]>("/policies/global", { signal: controller.signal }),
    ])
      .then(([accountData, policyData]) => {
        setAccounts(accountData);
        setPolicies(policyData);
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setFilterError(err instanceof Error ? err.message : "Não foi possível carregar as opções de filtro.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setFiltersLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    api<CollectionRun[]>("/collections?limit=100&offset=0", { signal: controller.signal })
      .then(set