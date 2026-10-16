# Etapa 23.19 — Dashboard de Usage & Costs do DeepOps

## Objetivo

Esta etapa disponibiliza em Configurações uma visão administrativa do uso técnico de CloudWatch produzido pelo próprio DeepOps e do custo operacional estimado pela Task 23.18.

> O dashboard apresenta uma estimativa do custo CloudWatch gerado pelo próprio DeepOps, e não o custo total de CloudWatch da conta AWS nem a fatura final da AWS.

> Por padrão, o valor apresentado é a estimativa bruta calculada pela Task 23.18 e não desconta free tier compartilhado quando o DeepOps não possui visibilidade completa sobre o consumo da conta.

> O frontend não reproduz fórmulas de pricing; todos os valores monetários são calculados pelo CloudWatch Cost Engine.

> Billing via Cost Explorer e Usage & Costs do DeepOps são domínios independentes.

> Nenhuma conversão cambial é realizada.

## Dependências confirmadas

A implementação parte diretamente dos contratos existentes na `main`:

- Task 23.17: `CloudWatchUsageEvent` como fonte factual de usage, com `occurred_at`, conta, região, operação, collector, analyzer, CollectionRun, request count, métricas/queries e success/failure;
- Task 23.18: `CloudWatchCostEngine` e seus endpoints de summary, timeseries e breakdown, com `gross_estimated_cost`, currency, completeness, unpriced usage, free-tier assumption, provenance e pricing verification date.

Nenhuma fórmula monetária foi movida para o browser. O Cost Engine continua sendo a única fonte de valores de custo.

## Localização e autorização

A área foi adicionada em:

```text
Configurações
└── Uso e custos
    └── CloudWatch do DeepOps
```

A rota é `/settings/usage-costs`. Ela integra a navegação administrativa existente de Configurações e não cria item principal na sidebar. O mesmo mecanismo de `settingsTabsForRole()`/`isAdminOnlySettingsPath()` mantém a área visível somente para administradores.

Os endpoints de telemetry e cost continuam protegidos por `require_admin`; esconder controles no frontend não substitui autorização server-side.

## Read models e APIs

O dashboard reutiliza:

```text
GET /api/v1/deepops-costs/cloudwatch/summary
GET /api/v1/deepops-costs/cloudwatch/timeseries
GET /api/v1/deepops-costs/cloudwatch/breakdown
GET /api/v1/usage/cloudwatch/summary
GET /api/v1/cloud-accounts
GET /api/v1/collections
```

A única extensão de read model necessária nesta task foi permitir `group_by=collection_run` no summary técnico de usage. Isso evita N+1 de raw telemetry para montar a tabela de execuções recentes e mantém requests/metric queries visíveis mesmo quando uma run possui custo não precificado.

O filtro de analyzer aceita internamente o sentinel `__shared__`, traduzido no backend para `analyzer IS NULL`. Assim, “Compartilhado / não atribuído” pode ser filtrado sem transformar `NULL` em um identificador persistido ou redistribuir custo.

Não foi criado endpoint composto nem mega-endpoint. A página consulta datasets agregados independentes em paralelo; não existe `GET all usage events` para gráficos ou tabelas.

## Filtros e período

O default é **Este mês**. Também existem Hoje, Últimos 7 dias, Mês anterior, Últimos 3 meses e Personalizado.

O frontend envia `date_from` e `date_to` como intervalo com limite superior exclusivo. O backend aplica o período a `CloudWatchUsageEvent.occurred_at`, nunca à data de cálculo do Cost Engine.

Filtros globais:

- Conta AWS;
- região;
- operação;
- collector;
- analyzer, incluindo Compartilhado / não atribuído quando existe attribution nula;
- período.

Os mesmos filtros canônicos são enviados para summary, timeseries e breakdowns. A lista de valores válidos de operação/região/collector/analyzer vem do summary de telemetry do período; não há catálogo hardcoded de operações instrumentadas.

Accounts são apresentadas com nome amigável e AWS Account ID quando disponíveis.

## Summary e KPIs

A visão inicial usa no máximo quatro KPIs:

- **Custo estimado do DeepOps**: usa exatamente `gross_estimated_cost` retornado pelo Cost Engine;
- **Requests CloudWatch**: soma técnica sobre grupos disjuntos do read model de usage;
- **Metric queries**: apresentada separadamente de requests;
- **Falhas**: eventos CloudWatch com `success=false`.

Não existe KPI genérico que some request count e metric-query count. Grandezas técnicas incompatíveis permanecem separadas.

Quando mais de uma currency estiver presente, valores monetários são renderizados por currency. Não existe total cross-currency.

## Gross estimated cost e free tier

O dashboard identifica o custo como **estimativa bruta**. `free_tier_applied` é exibido diretamente conforme a resposta da Task 23.18.

Quando `free_tier_applied=false`, a interface explica que o DeepOps observa seu próprio uso e pode não conhecer o consumo CloudWatch de outras workloads da conta, portanto não tenta inferir o saldo compartilhado de free tier.

Nenhum desconto, credit, EDP, private pricing ou free tier é reaplicado no browser.

## Pricing source, verified date e provenance

A área “Sobre esta estimativa” mostra:

- fonte de pricing;
- `pricing_verified_at`;
- free-tier assumption;
- completeness;
- unpriced usage;
- quantidade de vigências de pricing aplicadas;
- política de currency/FX.

No breakdown por operação, um detalhe técnico read-only mostra componentes fornecidos pelo backend: pricing rule id, usage quantity, unit price, unit quantity, pricing unit, effective date e source.

A interface não executa `usage × price`; os componentes existem somente para explicabilidade/provenance.

Se mais de uma pricing version aparecer no período, a UI informa a quantidade de versões efetivamente aplicada. Ela não apresenta “preço atual” como se tivesse sido usado em todo o histórico.

## Completeness e unpriced usage

`is_complete=false` produz warning visível antes dos KPIs e do gráfico. O valor parcial não é apresentado como total definitivo sem sinalização.

`unpriced_usage` é exibido com operação, região, eventos, requests e reason. Usage continua visível por meio da telemetria mesmo quando nenhum custo pode ser estimado.

Quando existe usage, mas o Cost Engine não encontra regra aplicável, a interface mostra explicitamente:

> Uso coletado, mas o custo não pôde ser estimado para o recorte porque não há regra de pricing aplicável.

## Timeseries

A série principal é **Custo estimado ao longo do tempo** e consome diretamente `/timeseries` da 23.18.

- períodos de até 62 dias usam buckets diários;
- períodos mais longos usam buckets mensais.

Cada currency é desenhada em um gráfico separado. O frontend usa apenas o valor agregado fornecido pelo backend para geometria do SVG; não recalcula custo.

Se o resultado do período estiver incompleto, a série monetária recebe warning geral de que é parcial, em vez de fingir precisão total.

O projeto não possuía biblioteca de charts. Foi reutilizado o padrão existente de SVG simples e acessível, sem introduzir dependência visual nova.

## Uso técnico

Além dos KPIs, uma seção específica apresenta:

- eventos;
- requests;
- metric queries;
- métricas solicitadas.

Essas grandezas são derivadas do read model agregado da 23.17. Não são convertidas em “unidades faturáveis” genéricas.

## Breakdown por conta

A seção de conta combina:

- group monetário por AWS Account ID da 23.18;
- summary técnico por account da 23.17;
- metadata de `CloudAccount` para nome amigável.

A tabela mostra requests, metric queries, falhas, custo estimado e participação percentual **somente dentro da mesma currency**.

## Breakdown por operação

A seção de operação apresenta custo e uso factual lado a lado e permite inspecionar o pricing provenance retornado pelo Cost Engine.

Percentuais são calculados apenas como aspecto visual dentro do conjunto de itens da mesma currency. Nenhum percentual é produzido entre currencies diferentes.

## Breakdown por collector

Collector utiliza somente attribution factual persistida pela 23.17. Identificadores conhecidos recebem labels amigáveis na UI; novos identificadores têm fallback legível sem alterar o valor enviado ao backend.

## Breakdown por analyzer e shared usage

Analyzer também usa somente attribution factual. O Cost Engine já representa `analyzer=NULL` como `Shared / Unattributed` no breakdown monetário sem duplicar requests.

A UI traduz o label para “Compartilhado / não atribuído”. Não existe rateio proporcional ou arbitrário de chamadas compartilhadas.

O filtro `__shared__` é somente um contrato HTTP interno para selecionar `IS NULL`; ele não é salvo no banco e não cria uma categoria financeira nova.

## CollectionRun

A tabela “Execuções recentes” combina três read models agregados:

- cost breakdown `group_by=collection_run`;
- usage summary `group_by=collection_run`;
- metadata paginada de `/collections` para início, conta e status.

A tabela mostra CollectionRun, data, conta, status, requests, metric queries e custo estimado por currency, com deep link para o detalhe de coleta existente.

Runs `FAILED` não são escondidas e não são tratadas como custo zero. Se houver requests e custo, os valores permanecem visíveis.

Usage sem `collection_run_id` continua válido e é apresentado como quantidade não atribuída a uma execução específica; nenhuma run artificial é criada.

## Currency e precisão

A currency sempre vem do Cost Engine. O dashboard não hardcode USD na formatação e não converte USD/BRL.

A formatação monetária é adaptativa:

- valores usuais usam 2 casas;
- abaixo de 0,01 são usadas 4 casas;
- abaixo de 0,0001 são usadas 6 casas;
- abaixo de 0,000001 são usadas 8 casas;
- se um valor ainda não-zero ficar abaixo da menor precisão visual, a UI usa marcador `<` em vez de exibir zero.

O valor financeiro original continua sendo a string Decimal retornada pelo backend. Conversão para `number` é usada apenas para formatação/geometria visual e cálculo de participação dentro da mesma currency, nunca para recomputar o custo.

## Loading, error e empty states

Telemetria e Cost Engine possuem erros independentes:

- falha de telemetry não é apresentada como pricing error;
- falha do Cost Engine não esconde telemetry válida;
- `is_complete=false` é warning, não erro de transporte;
- período sem telemetry é empty state, não erro;
- implantação recente explica que dados surgem após novas coletas, sem criar backfill fictício.

As requests do dashboard usam `AbortController` e sequence id. Mudanças rápidas de filtro abortam requests anteriores e uma resposta stale não substitui a seleção atual.

Loading é separado entre cost, usage e CollectionRun metadata; Configurações inteira não é bloqueada.

## Performance

Todos os gráficos/breakdowns consomem agregações SQL/read models existentes. Raw `CloudWatchUsageEvent` não é carregado em massa para o frontend.

A extensão `group_by=collection_run` elimina a necessidade de uma consulta por run. Account metadata é carregada em uma única chamada. Collections são carregadas em uma página limitada e unidas no browser apenas por id para metadata de apresentação.

Nenhuma migration ou índice novo foi necessário: as consultas usam as dimensões já indexadas pela 23.17 e as agregações existentes da 23.18.

## Segurança e independência de domínios

Esta etapa não consulta Cost Explorer e não altera Billing 23.14–23.16. Também não lê ou muta o ledger de Fluxo, não cria Opportunity/Finding, não altera Pricing OCI e não realiza FX.

Não existe reconciliação automática entre DeepOps estimate e line items de CloudWatch no Cost Explorer.

Não existe KPI global de ROI porque savings e custo operacional podem possuir currency e base temporal incompatíveis.

## Testes

Backend:

- summary por CollectionRun;
- uso sem CollectionRun preservado;
- failed run com requests preservado;
- filtros existentes continuam reutilizados;
- shared analyzer é filtrado por `IS NULL` sem redistribuição.

Frontend helper tests:

- default Este mês e end date exclusivo;
- daily/monthly granularity;
- custom range inválido;
- canonical query filters;
- requests e metric queries somados separadamente;
- currency grouping sem total cross-currency;
- small value não-zero não formatado como zero;
- labels de collector/shared analyzer;
- múltiplas pricing versions derivadas de provenance.

Settings navigation tests cobrem visibilidade admin-only e existência da nova página.

O CI cumulativo executa backend `ruff check .`, `ruff format --check .`, `pytest -q`; frontend `npm test` e `npm run build`; além do job de security existente.

## Limitações deliberadas

Ficam fora da 23.19:

- pricing editor completo;
- atualização automática/scraper de CloudWatch pricing;
- anomaly detection;
- budgets/tetos internos;
- push/realtime após CollectionRun;
- reconciliação com Cost Explorer;
- ROI global;
- FX;
- geração de ledger entries;
- Opportunities/Findings;
- export pipeline novo;
- redesign global, reservado para a Task 23.20.
