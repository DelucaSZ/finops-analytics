"use client";

import {
  Bell,
  Check,
  Cloud,
  Database,
  MoreHorizontal,
  Search,
  Settings,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { iconDefaults, iconSizes } from "@/lib/iconography";
import { useTheme } from "@/components/theme-provider";
import {
  AccountSelector,
  ChartCard,
  CurrencyDisplay,
  DataState,
  DateRangePicker,
  EnvironmentSelector,
  FilterBar,
  MetricCard,
  PageHeader,
  PercentageDisplay,
  ProviderBadge,
  ProviderSelector,
  RecommendationCard,
  ResourceIdentifier,
  Section,
  StatusIndicator,
  TrendIndicator,
  type DateRangeValue,
} from "@/components/aven";
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Checkbox,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Divider,
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  EmptyState,
  IconButton,
  Input,
  Pagination,
  Radio,
  RadioGroup,
  Select,
  Skeleton,
  Spinner,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  Tooltip,
  useToast,
} from "@/components/ui";
import styles from "./page.module.css";

const accountOptions = [
  { value: "111111111111", label: "Production account with a deliberately long name for truncation coverage", accountId: "111111111111", provider: "AWS", environment: "Production" },
  { value: "222222222222", label: "Shared services", accountId: "222222222222", provider: "AWS", environment: "Shared" },
  { value: "oci-prod", label: "OCI production tenancy", accountId: "ocid1.tenancy.oc1..example", provider: "OCI", environment: "Production" },
];

const environmentOptions = [
  { value: "production", label: "Production" },
  { value: "staging", label: "Staging" },
  { value: "shared", label: "Shared services" },
];

const providerOptions = [
  { value: "aws", label: "AWS" },
  { value: "oci", label: "OCI" },
  { value: "future-cloud", label: "Future Cloud" },
];

export default function AvenUiPreviewPage() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const { toast } = useToast();
  const [checked, setChecked] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [page, setPage] = useState(2);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [environment, setEnvironment] = useState("production");
  const [provider, setProvider] = useState("aws");
  const [dates, setDates] = useState<DateRangeValue>({ startDate: "2026-10-01", endDate: "2026-10-26" });

  return (
    <main className={styles.preview}>
      <header className={styles.header}>
        <h1 className={styles.title}>Aven UI System</h1>
        <p className={styles.lead}>Technical preview for Aven primitives and Task 24.6 Product Components. Visual structure consumes semantic/foundation tokens.</p>
        <div className={styles.row}>
          {(["light", "dark", "system"] as const).map((value) => (
            <Button key={value} variant={theme === value ? "primary" : "outline"} size="sm" onClick={() => setTheme(value)}>
              {value[0].toUpperCase() + value.slice(1)}
            </Button>
          ))}
          <span className={styles.themeState}>Preference: {theme} · resolved: {resolvedTheme}</span>
        </div>
      </header>

      <Section title="Product Components" description="Domain-aware reusable composition for FinOps pages without page-specific business rules.">
        <PageHeader
          title="Billing"
          description="Usage and cloud costs across the selected scope. This long supporting description validates wrapping without overlap."
          breadcrumbs={<span>FinOps / Billing</span>}
          metadata={<StatusIndicator status="info" label="Preview data" />}
          actions={<><Button variant="outline">Export</Button><Button>Refresh</Button></>}
        />

        <div className={styles.grid}>
          <MetricCard label="Total cost" value={<CurrencyDisplay value={124810} currency="USD" />} trend={{ value: 6.3, direction: "up", sentiment: "negative" }} supportingText="Compared with previous period" />
          <MetricCard label="Potential savings" value={<CurrencyDisplay value={21400} currency="USD" />} trend={{ value: 8.2, direction: "up", sentiment: "positive" }} />
          <MetricCard label="Coverage" value={<PercentageDisplay value={74.6} />} trend={{ value: 0, direction: "flat", sentiment: "neutral" }} />
          <MetricCard label="No backend value" value={null} emptyValue="N/A" supportingText="Null remains distinct from zero." />
          <MetricCard label="Loading metric" value={null} loading />
        </div>

        <FilterBar clearAction={<Button variant="ghost" size="sm" onClick={() => { setAccounts([]); setDates({ startDate: null, endDate: null }); }}>Clear filters</Button>}>
          <AccountSelector label="Accounts" options={accountOptions} multiple value={accounts} onChange={setAccounts} selectAll />
          <EnvironmentSelector label="Environment" options={environmentOptions} value={environment} onChange={setEnvironment} />
          <ProviderSelector label="Provider" options={providerOptions} value={provider} onChange={setProvider} />
          <DateRangePicker
            value={dates}
            onChange={setDates}
            presets={[
              { value: "october", label: "Current month", range: { startDate: "2026-10-01", endDate: "2026-10-26" } },
              { value: "custom", label: "Custom" },
            ]}
          />
        </FilterBar>

        <Section title="Operational presentation" description="Status, provider, resources, money, percentages, and trends compose independently." appearance="card">
          <div className={styles.row}>
            <StatusIndicator status="success" label="Active" />
            <StatusIndicator status="warning" label="Expiring" />
            <StatusIndicator status="danger" label="Expired" />
            <StatusIndicator status="pending" label="Pending" />
            <ProviderBadge provider="aws" />
            <ProviderBadge provider="oci" />
            <ProviderBadge provider="future-cloud" />
            <TrendIndicator value={4.8} direction="down" sentiment="positive" label="Cost trend" />
            <TrendIndicator value={4.8} direction="down" sentiment="negative" label="Savings trend" />
          </div>
          <ResourceIdentifier primary="orders-production-db-with-a-long-resource-name" technicalId="arn:aws:rds:us-east-1:111111111111:db:orders-production-primary-database-with-long-id" />
          <div className={styles.row}>
            <CurrencyDisplay value={0} currency="USD" />
            <CurrencyDisplay value={-1240.55} currency="USD" />
            <CurrencyDisplay value={18342.49} currency="BRL" locale="pt-BR" />
            <CurrencyDisplay value={1480000} currency="USD" compact />
            <PercentageDisplay value={42} />
            <PercentageDisplay value={0.42} valueMode="fraction" />
          </div>
        </Section>

        <div className={styles.grid}>
          <ChartCard title="Cost evolution" description="ChartCard provides the container; visualization remains independent." legend={<><Badge>Actual</Badge><Badge variant="info">Forecast</Badge></>}>
            <div className={styles.previewChart} role="img" aria-label="Placeholder for a future responsive cost chart">Future chart slot</div>
          </ChartCard>
          <ChartCard title="Loading chart" loading><div /></ChartCard>
          <ChartCard title="Empty chart" empty emptyDescription="No cost data for the selected scope."><div /></ChartCard>
          <ChartCard title="Error chart" error="The chart request failed."><div /></ChartCard>
        </div>

        <RecommendationCard
          title="Purchase RDS reservation"
          description="Opportunity detected from active database shape and reservation coverage."
          provider="aws"
          status="warning"
          statusLabel="Review"
          potentialSavings={<CurrencyDisplay value={4320} currency="USD" />}
          impact="High"
          confidence={<PercentageDisplay value={91} />}
          resource={<ResourceIdentifier primary="orders-production-db" technicalId="db-ABCDEFGHIJKLMNOP" />}
          metadata="Region: us-east-1 · Term: 1 year"
          actions={<><Button variant="outline">Dismiss</Button><Button>Review opportunity</Button></>}
        />

        <div className={styles.grid}>
          <DataState loading><span>Loaded content</span></DataState>
          <DataState empty emptyTitle="No recommendations" emptyDescription="The selected scope has no current opportunities."><span>Loaded content</span></DataState>
          <DataState error="Unable to load recommendations."><span>Loaded content</span></DataState>
          <AccountSelector label="Disabled selector" options={accountOptions} value="" onChange={() => {}} disabled />
          <AccountSelector label="Loading selector" options={[]} value="" onChange={() => {}} loading />
        </div>
      </Section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Buttons & actions</h2>
        <div className={styles.row}>
          <Button variant="primary" leadingIcon={<Sparkles {...iconDefaults} />}>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger" leadingIcon={<Trash2 {...iconDefaults} />}>Danger</Button>
          <Button loading>Loading</Button>
          <Button disabled>Disabled</Button>
          <IconButton aria-label="Notificações" tooltip="Notificações"><Bell {...iconDefaults} /></IconButton>
          <Tooltip content="Keyboard and pointer accessible tooltip"><Button variant="outline">Tooltip</Button></Tooltip>
        </div>
        <div className={styles.row}>
          <Button size="sm">Small</Button><Button size="md">Medium</Button><Button size="lg">Large</Button>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Forms</h2>
        <div className={styles.formGrid}>
          <Input label="Nome" placeholder="Digite..." helperText="Helper text" leadingIcon={<Search {...iconDefaults} />} />
          <Input label="Erro" defaultValue="Valor inválido" error="Revise este campo." />
          <Input label="Disabled" value="Indisponível" disabled readOnly />
          <Select label="Ambiente" placeholder="Selecione" defaultValue="" options={[{ value: "prod", label: "Produção" }, { value: "stage", label: "Staging" }]} />
          <Textarea label="Descrição" placeholder="Conteúdo longo em Português or English..." helperText="Resizable vertically." />
        </div>
        <div className={styles.row}>
          <Checkbox checked={checked} onChange={(event) => setChecked(event.target.checked)} label="Selecionado" description="Checkbox com descrição" />
          <Checkbox indeterminate label="Indeterminado" />
          <Checkbox disabled label="Disabled" />
          <RadioGroup legend="Radio group">
            <Radio name="preview-radio" value="one" defaultChecked label="Opção um" />
            <Radio name="preview-radio" value="two" label="Opção dois" />
          </RadioGroup>
          <Switch checked={enabled} onCheckedChange={setEnabled} label="Ativo" description="Boolean switch" aria-label="Ativar recurso" />
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Status & feedback</h2>
        <div className={styles.row}>
          <Badge>Neutral</Badge><Badge variant="info">Info</Badge><Badge variant="success" icon={<Check {...iconDefaults} />}>Success</Badge><Badge variant="warning">Warning</Badge><Badge variant="danger">Danger</Badge>
        </div>
        <div className={styles.grid}>
          <Alert variant="info" title="Informação" description="Status is communicated with icon, text and semantic color." />
          <Alert variant="success" title="Concluído" description="The operation completed successfully." />
          <Alert variant="warning" title="Atenção" description="Review before continuing." />
          <Alert variant="danger" title="Falha" description="An actionable error state." />
        </div>
        <Button variant="outline" onClick={() => toast({ variant: "success", title: "Salvo", description: "Toast theme-aware com pausa no hover." })}>Show toast</Button>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Navigation & overlays</h2>
        <div className={styles.row}>
          <DropdownMenu>
            <DropdownMenuTrigger><MoreHorizontal {...iconDefaults} /> Menu</DropdownMenuTrigger>
            <DropdownMenuContent aria-label="Ações de exemplo">
              <DropdownMenuItem icon={<Settings {...iconDefaults} />}>Configurar</DropdownMenuItem>
              <DropdownMenuItem icon={<Cloud {...iconDefaults} />}>Abrir recurso</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem danger icon={<Trash2 {...iconDefaults} />}>Excluir</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Dialog>
            <DialogTrigger variant="outline">Open dialog</DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Dialog title</DialogTitle><DialogDescription>Native modal semantics, focus trapping and Escape behavior.</DialogDescription></DialogHeader>
              <p>Content can scroll inside the viewport-safe surface.</p>
              <DialogFooter><DialogClose>Cancel</DialogClose><Button>Confirm</Button></DialogFooter>
            </DialogContent>
          </Dialog>
          <Drawer>
            <DrawerTrigger variant="outline">Open drawer</DrawerTrigger>
            <DrawerContent side="right">
              <DrawerHeader><DrawerTitle>Drawer title</DrawerTitle><DrawerDescription>Right and left sides share the same primitive contract.</DrawerDescription></DrawerHeader>
              <p>Drawer content.</p>
              <DrawerFooter><DrawerClose>Close</DrawerClose></DrawerFooter>
            </DrawerContent>
          </Drawer>
        </div>
        <Tabs defaultValue="overview">
          <TabsList aria-label="Preview tabs"><TabsTrigger value="overview">Overview</TabsTrigger><TabsTrigger value="details">Details</TabsTrigger><TabsTrigger value="disabled" disabled>Disabled</TabsTrigger></TabsList>
          <TabsContent value="overview">Overview panel with keyboard navigation.</TabsContent>
          <TabsContent value="details">Details panel.</TabsContent>
        </Tabs>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Surfaces & data</h2>
        <div className={styles.grid}>
          <Card><CardHeader><CardTitle>Card title</CardTitle><CardDescription>Use cards only when a distinct surface is meaningful.</CardDescription></CardHeader><CardContent>Card content</CardContent><CardFooter><Button size="sm">Action</Button></CardFooter></Card>
          <Card><CardContent><EmptyState icon={<Database size={iconSizes["2xl"]} />} title="Nenhum item" description="Generic empty state without domain coupling." primaryAction={<Button size="sm">Primary action</Button>} /></CardContent></Card>
        </div>
        <Table className={styles.previewTable}>
          <TableHeader><TableRow staticRow><TableHead>Resource</TableHead><TableHead>Status</TableHead><TableHead numeric>Value</TableHead></TableRow></TableHeader>
          <TableBody>
            <TableRow selected><TableCell>resource-with-a-long-identifier</TableCell><TableCell><Badge variant="success">Active</Badge></TableCell><TableCell numeric>1,234.56</TableCell></TableRow>
            <TableRow><TableCell>resource-02</TableCell><TableCell><Badge variant="warning">Pending</Badge></TableCell><TableCell numeric>87.20%</TableCell></TableRow>
          </TableBody>
        </Table>
        <Pagination page={page} pageCount={8} onPageChange={setPage} />
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Loading, identity & separators</h2>
        <div className={styles.row}>
          <Spinner size="sm" label="Carregando" /><Spinner size="md" /><Spinner size="lg" />
          <Avatar fallback="AV" size="sm" /><Avatar fallback="AV" /><Avatar fallback="AV" size="lg" />
        </div>
        <Divider />
        <div className={styles.skeletonStack}><Skeleton /><Skeleton /><Skeleton variant="rectangular" /><Skeleton variant="circle" /></div>
      </section>
    </main>
  );
}
