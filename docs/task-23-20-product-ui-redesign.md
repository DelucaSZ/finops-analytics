# Etapa 23.20 — Redesign global, navegação e experiência multi-cloud

**Status:** concluída, validada e incorporada à `main` pelo PR #74; merge commit `029a1b579ac6c91f8adee14ac9748a91eb7c8ef4`.

## Objetivo e auditoria visual

A etapa consolida visualmente o DeepOps sem criar novos domínios e sem alterar contratos financeiros, lifecycle, pricing, coleta ou regras de oportunidade. A auditoria encontrou uma base predominantemente dark-only, sidebar desktop de largura fixa, branding residual AWS em autenticação/metadata, a mensagem decorativa `Ambiente protegido`, estilos de superfície hardcoded e densidade divergente entre áreas construídas incrementalmente.

O redesign evolui a biblioteca e os componentes existentes. `PageHeader`, botões, panels/cards, badges, tabelas, filtros, forms, modals/drawers e estados de feedback convergem para tokens semânticos compartilhados e para escalas mais consistentes de radius, spacing e tipografia.

> o DeepOps passa a se apresentar visualmente como uma plataforma FinOps multi-cloud, e não como uma ferramenta exclusivamente AWS.

> AWS e OCI continuam identificados sempre que o provider faz parte do contexto do dado, mas o branding global do produto permanece provider-neutral.

## Branding, navegação e sidebar

O shell global usa `DeepOps` e `FINOPS MULTI-CLOUD`. O login deixa de exibir `AWS FINOPS INTELLIGENCE`, o metadata deixa de descrever o produto como exclusivo de ambientes AWS e `Ambiente protegido` é removido sem badge decorativo substituto. Menções a AWS continuam preservadas quando representam contexto factual.

A navegação principal permanece compacta: Dashboard, Oportunidades, Fluxo, Billing, Coletas e Configurações. A sidebar desktop suporta expanded/collapsed com larguras centralizadas em tokens, transição curta, botão acessível, active state perceptível e tooltips quando collapsed. A preferência `deepops.sidebar.collapsed` persiste localmente e falha de storage usa expanded como fallback.

Em mobile a navegação usa drawer/overlay, não o collapsed desktop. O drawer fecha após navegação, pelo overlay e por Escape.

## Theme system

Foi introduzida preferência `system | light | dark`, persistida em `deepops.theme`, com `system` como default. `System` usa `prefers-color-scheme` e responde a mudanças do sistema. Preferência inválida volta para `system`.

O layout executa bootstrap mínimo antes da hidratação para aplicar tema e sidebar antes do primeiro paint, reduzindo flash relevante. A opção original `system` permanece persistida; a cor resolvida não substitui a preferência.

Configurações ganha **Aparência**, disponível a usuários autenticados, sem backend para preferência puramente local.

## Design tokens, typography e density

`frontend/app/ui-system.css` centraliza tokens de background/foreground, surfaces, borders, primary, muted, success/warning/danger/info, focus, charts, controls, overlay, radius e dimensões da sidebar. Light e Dark têm hierarquias completas de surface/border/text/control. Provider branding não dirige o tema global.

`PageHeader` passa a aceitar eyebrow/description opcionais. Page titles, section headings, KPIs, body/captions, buttons e badges usam escalas mais consistentes. Cards funcionais continuam existindo, mas sombras, paddings e grandes vazios foram reduzidos para aumentar densidade útil.

## Tables, filters, forms, charts e estados

Tabelas usam headers/borders semânticos, spacing mais compacto e scroll horizontal quando necessário. Billing, Pricing OCI e Usage & Costs tiveram filtros, forms, KPIs, charts, tables, warnings/errors e surfaces migrados para tokens light/dark. Inputs/selects preservam labels, focus visible e contraste. Dialog/drawer overlay usa token compartilhado. Loading, empty e error states existentes herdam a mesma semântica visual.

Charts usam palette semântica em vez de depender de cores de provider. Legends/tooltips e estrutura de dados existentes permanecem inalteradas.

## Páginas revisadas

- **Dashboard:** branding provider-neutral, surfaces/KPIs mais densos, escopo multi-cloud e totais por currency preservados.
- **Opportunities / History / Detail:** tabs, filtros, tabela e drawer usam o sistema compartilhado; status humano e presence técnica continuam distintos e agora também recebem tratamento visual distinto.
- **Fluxo:** provider, currency, periodicity, run-rate e one-time permanecem sem simplificação de domínio.
- **Billing:** filtros principais, profile context, KPIs, charts e breakdowns foram compactados e tematizados; `Estimated` continua factual.
- **Settings:** navegação única e compacta, nova área Aparência, mantendo Pricing OCI, Billing Profiles e Usage & Costs separados.
- **Pricing OCI:** tabela administrativa, form/modal, paginação e histórico tematizados; BRL permanece BRL.
- **Billing Profiles:** permanece área administrativa própria sob Settings e herda tokens/componentes compartilhados.
- **Usage & Costs:** preserva a distinção entre DeepOps cost estimate e AWS Billing e seus estados de incomplete/erro.
- **Login/auth:** branding global provider-neutral e temas compartilhados sem reimplementar autenticação.

## Acessibilidade, responsividade e performance

Focus visible existe em Light/Dark. Botões de sidebar/menu têm `aria-label`, `aria-expanded` e `aria-controls`. Itens collapsed continuam identificáveis por tooltip e label acessível. `prefers-reduced-motion` reduz transitions. A navegação mobile é independente do estado collapsed desktop e grids/filtros reduzem colunas em viewports menores.

A implementação reutiliza React/Next.js, CSS e `lucide-react`. Nenhuma biblioteca nova de animação, charts, ícones ou componentes foi adicionada; não há novo fluxo de dados de domínio para tema/sidebar.

## Regressões e invariantes

> nenhuma regra de conversão cambial foi introduzida pelo redesign; BRL e USD continuam sendo tratados separadamente.

> o redesign preserva a separação conceitual entre Opportunities, Fluxo, Billing e Usage & Costs.

Human status e technical presence continuam conceitos distintos. Billing e Fluxo permanecem domínios distintos. Nenhum analyzer, provider, forecast, Billing OCI, repricing, ledger rule ou novo domínio foi introduzido.

## Testes e validação

Foram adicionados testes para normalização/resolução de tema, default System, persistência de sidebar, bootstrap pré-hidratação, ausência do branding global obsoleto, collapse/tooltips, mobile drawer, tokens semânticos, reduced motion, diferenciação visual de human status/presence e navegação Settings/Aparência.

Validação do head funcional `1534c4c005ae861a24e0beb226dfa9e44a98a01b` no PR #74:

- backend: `ruff check .` aprovado;
- backend: `ruff format --check .` aprovado;
- backend: `pytest -q` com **850 testes aprovados**;
- frontend: `npm test` com **113 testes aprovados**;
- frontend: `npm run build` aprovado, incluindo lint/type validation e geração das páginas;
- security job aprovado;
- Stage 21 Compose smoke aprovado;
- Auto deploy tests aprovado;
- First Load JS compartilhado no build final: **103 kB**;
- nenhuma dependência visual nova adicionada.

O smoke visual manual não foi executado antes do merge. Após o fechamento da implementação, a decisão operacional é realizar essa validação diretamente no ambiente implantado durante o próximo rollout/pull de produção. Isso não deve ser descrito como teste já executado; qualquer regressão encontrada deve ser tratada como hotfix/follow-up da 23.20.

## Publicação

- PR: `#74 — feat: Task 23.20 — redesign global e experiência multi-cloud`;
- head funcional: `1534c4c005ae861a24e0beb226dfa9e44a98a01b`;
- merge commit na `main`: `029a1b579ac6c91f8adee14ac9748a91eb7c8ef4`.

O fechamento pós-merge e o checklist operacional do smoke estão registrados também em `docs/task-23-20-closeout.md`.

## Limites deliberados

A 23.20 não implementa GCP/Azure, FX, Billing OCI, forecast, analyzers, regras financeiras novas, repricing ou novos domínios. Também não altera lifecycle/presence para facilitar apresentação.
