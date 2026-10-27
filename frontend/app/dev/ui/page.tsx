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

export default function AvenUiPreviewPage() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const { toast } = useToast();
  const [checked, setChecked] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [page, setPage] = useState(2);

  return (
    <main className={styles.preview}>
      <header className={styles.header}>
        <h1 className={styles.title}>Aven UI Primitives</h1>
        <p className={styles.lead}>Technical preview for Task 24.5. All visual primitives consume Aven semantic/foundation tokens.</p>
        <div className={styles.row}>
          {(["light", "dark", "system"] as const).map((value) => (
            <Button key={value} variant={theme === value ? "primary" : "outline"} size="sm" onClick={() => setTheme(value)}>
              {value[0].toUpperCase() + value.slice(1)}
            </Button>
          ))}
          <span className={styles.themeState}>Preference: {theme} · resolved: {resolvedTheme}</span>
        </div>
      </header>

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
