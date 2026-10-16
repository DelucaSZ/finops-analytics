# Etapa 23.18 — CloudWatch Cost Engine do DeepOps

## Objetivo

Esta etapa transforma a telemetria técnica criada na 23.17 em uma **estimativa operacional do custo CloudWatch gerado pelo próprio DeepOps**.

> O custo calculado nesta etapa é uma estimativa operacional baseada no uso CloudWatch observado pelo DeepOps e nas regras oficiais de pricing verificadas.

Uso e custo permanecem conceitos separados: `cloudwatch_usage_events` é a fonte factual de usage observado; `cloudwatch_pricing_rules` representa pricing público versionado; o `CloudWatchCostEngine` combina ambos sem alterar a telemetria bruta.

> Cost Explorer Billing e CloudWatch Cost Engine são domínios distintos: o primeiro consulta custos AWS consolidados; o segundo estima especificamente o custo das chamadas geradas pelo próprio DeepOps.

> Nenhuma conversão cambial é realizada.

## Estado da telemetria 23.17

A 23.17 está presente na `main` e o inventário atual do DeepOps usa somente `GetMetricStatistics`:

- `rds_nonprod_idle`: `AWS/RDS` para CPU e conexões;
- `load_balancer_no_traffic`: métricas de Application Load Balancer, Network Load Balancer e Classic Load Balancer.

A instrumentação já registra `request_count`, `retry_count`, `request_count_is_exact`, success/failure, account, region, collector, analyzer e CollectionRun. `GetMetricData` e `ListMetrics` são reconhecidos pelo wrapper, mas não são utilizados pelos collectors atuais e por isso **não recebem regra de pricing nesta etapa**.

## Documentação AWS consultada

Pricing verificado em 16/10/2026 nas fontes oficiais:

- Amazon CloudWatch Pricing: <https://aws.amazon.com/cloudwatch/pricing/>;
- Analyzing, optimizing, and reducing CloudWatch costs: <https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_billing.html>;
- GetMetricStatistics API Reference: <https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricStatistics.html>;
- Retrieve metric data / GetMetricData: <https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/metrics-classic-getdata.html>;
- CloudWatch usage metrics: <https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Usage-Metrics.html>.

A documentação classifica `GetMetricStatistics` em `UsageType=Requests`. O preço público corrente usado nesta etapa é **USD 0,01 por 1.000 API requests**. A página de pricing também documenta 1.000.000 de API requests no free tier para as APIs genéricas, enquanto operações como `GetMetricData` possuem estrutura diferente.

`GetMetricStatistics` é uma API single-metric e não é paginada por `NextToken`. `GetMetricData` é uma operação distinta e tem pricing por métricas solicitadas; ela não é precificada nesta etapa porque o DeepOps não a utiliza hoje.

## Pricing model

`CloudWatchPricingRule` é independente do Pricing Catalog OCI e registra:

- `operation`;
- `pricing_dimension`;
- `region_scope`;
- `unit` e `unit_quantity`;
- `price` com `Numeric(28,12)` / `Decimal`;
- `currency` explícita;
- `effective_from` / `effective_until`;
- `tier_from` / `tier_to` e `tier_scope`;
- `applicability`;
- `source` e `source_reference`;
- `pricing_verified_at`;
- `enabled` e timestamps.

A identidade inclui operação, dimensão, escopo regional, início de vigência e início do tier. Alteração futura de preço deve encerrar a versão anterior e criar outra; preço histórico não deve ser sobrescrito destrutivamente.

## Seed oficial atual

A migration `0029_cloudwatch_cost_engine` cria a tabela e cadastra deterministicamente a regra necessária ao usage realmente encontrado:

```text
operation: GetMetricStatistics
pricing_dimension: API_REQUEST
region_scope: AWS_COMMERCIAL
unit: REQUEST
unit_quantity: 1000
price: 0.01
currency: USD
effective_from: 2026-10-16T00:00:00Z
tier_from: 0
tier_to: open
source: AWS_OFFICIAL_PRICING
```

Regiões China, GovCloud, ISO/ISOB e `unknown` não usam essa regra comercial e permanecem explicitamente não precificadas até existir fonte oficial cadastrada para seus escopos.

## Fórmula

Para a regra atual:

```text
gross_estimated_cost = request_count / 1000 × USD 0.01
```

O cálculo usa `Decimal` de ponta a ponta e não arredonda eventos antes da agregação. `unit_quantity=1000` é persistido; não existe normalização implícita nem arredondamento do usage para blocos de mil.

## Pricing Resolver

`CloudWatchPricingResolver` carrega as regras habilitadas uma única vez por instância e resolve usando:

```text
operation
+ pricing_dimension
+ region
+ occurred_at
+ posição no tier, quando aplicável
```

Ausência gera `CloudWatchPricingNotFoundError`. Mais de uma regra aplicável gera `CloudWatchPricingAmbiguousError`. O resolver nunca escolhe a primeira row e nunca converte missing price em zero.

O helper de tier suporta faixas contínuas com `Decimal`, limites inclusivo/exclusivo e falha se existir gap de cobertura. O pricing corrente de `GetMetricStatistics` não possui tiers pagos: o patamar relevante é o free tier compartilhado, que não é aplicado à estimativa bruta.

## Cost Engine

`CloudWatchCostEngine` mantém raw usage como fonte de verdade e calcula custo sob demanda. Não é criada uma linha materializada de custo por telemetry event.

A engine:

1. carrega o snapshot de pricing uma vez;
2. valida overlaps ambíguos;
3. agrupa usage em SQL por regra/vigência e dimensões analíticas;
4. aplica `Decimal` e tiers quando representados;
5. preserva provenance de cada componente;
6. agrega somente dentro da mesma currency;
7. executa consulta separada para identificar usage sem regra válida.

Isso evita N+1 de pricing por event e mantém a possibilidade de recomputar histórico com a versão aplicável ao timestamp do usage.

## Gross estimate e free tier

A métrica principal é `gross_estimated_cost`.

> Por padrão, a estimativa é bruta e não desconta free tier compartilhado da conta quando o DeepOps não possui visibilidade suficiente sobre o consumo CloudWatch de outras workloads.

`free_tier_applied=false` é retornado pela API. Não existe tentativa de inferir o saldo do free tier apenas a partir das chamadas produzidas pelo DeepOps.

Também não são aplicados EDP, private pricing, enterprise discounts, tax, credits ou negotiated rates.

## Failures, retries e paginação

A AWS documenta a cobrança pela categoria de API requests, mas a documentação consultada não estabelece uma exclusão confiável para tentativas que retornam erro. Por isso a estimativa bruta contabiliza o `request_count` observado mesmo quando `success=false`, e sinaliza `failed_events` separadamente.

Quando botocore expõe `RetryAttempts`, a 23.17 já registra `request_count=1+RetryAttempts`; a engine usa essa quantidade, portanto retries físicos observados participam da estimativa. Falhas de transporte sem metadata de retry têm somente mínimo factual e são sinalizadas por `request_count_is_exact=false` / `inexact_request_events`.

`GetMetricStatistics` não pagina. Para futuras operações paginadas, cada invocação física já é um usage event da 23.17; nenhuma página deve ser colapsada antes da precificação quando request count for a unidade faturável.

## GetMetricData, ListMetrics e Metrics Insights

Essas operações **não são usadas pelos collectors atuais** e, conforme o escopo da task, não receberam seeds “por completude”. Se eventos surgirem para elas antes de uma regra oficial ser cadastrada, o resultado será `UNPRICED_USAGE` e `is_complete=false`.

Isso é especialmente importante para `GetMetricData`: sua cobrança é distinta de `GetMetricStatistics`, e Metrics Insights depende de métricas analisadas. A engine não reutiliza a fórmula de API requests genéricas.

## Region e currency

A regra atual usa `AWS_COMMERCIAL`. Regiões de partições com pricing separado ficam sem preço em vez de herdar USD silenciosamente.

Toda regra possui `currency`. Toda resposta agrega custo por currency. Valores de moedas diferentes nunca são somados. Não existe USD → BRL nem qualquer FX.

## Provenance

Cada componente calculado retorna:

- `pricing_rule_id`;
- usage quantity;
- unit price;
- unit quantity e pricing unit;
- currency;
- effective interval;
- source e source reference;
- `pricing_verified_at`.

Assim o custo pode ser explicado e reproduzido a partir do raw usage e da regra temporal usada.

## API

Endpoints administrativos read-only:

```text
GET /api/v1/deepops-costs/cloudwatch/summary
GET /api/v1/deepops-costs/cloudwatch/timeseries?granularity=daily|monthly
GET /api/v1/deepops-costs/cloudwatch/breakdown?group_by=account|region|operation|collector|analyzer|collection_run
```

Filtros comuns:

```text
date_from
date_to
cloud_account_id
aws_account_id
region
operation
collector
analyzer
collection_run_id
```

A autorização segue o modelo administrativo já usado pelos endpoints de telemetria CloudWatch. A resposta inclui totals por currency, gross estimate, usage quantity, priced/unpriced events, inexact request events, failures, provenance, pricing source/date e assumptions.

## Incomplete / unpriced usage

Usage fora de uma regra válida não é omitido e não recebe custo zero. A API retorna `unpriced_usage` com operação, região, events, requests e `reason=UNPRICED_USAGE`. Qualquer usage não precificado força `is_complete=false`.

## Performance

O resolver não executa query de pricing por evento. Pricing é carregado uma vez; o cost engine agrega usage no banco por versão de regra e dimensão analítica. A estratégia atual de cálculo sob demanda evita backfill e duplicação de milhões de rows de custo.

Se volume futuro exigir materialização, raw usage + pricing versionado continuam sendo as fontes necessárias para um job idempotente e reproduzível.

## Migration

`0029_cloudwatch_cost_engine` parte diretamente de `0028_cloudwatch_usage_telemetry`, cria somente `cloudwatch_pricing_rules`, constraints, índice de lookup e o seed oficial corrente de `GetMetricStatistics`. Nenhuma row de telemetria é removida, regravada ou backfilled por migration.

## Testes

A cobertura específica valida:

- resolução por vigência e mudança histórica;
- missing price e overlapping/ambiguous price;
- precisão Decimal;
- `unit_quantity` e boundaries de tiers;
- `GetMetricStatistics` baseado em request count;
- retries e failures;
- unpriced operation;
- partições/regiões não cobertas;
- breakdown por account, region, operation, collector, analyzer e CollectionRun;
- timeseries daily/monthly;
- currencies distintas sem soma;
- free tier não aplicado por default.

A suíte cumulativa mantém a regressão da instrumentação 23.17, collectors AWS, Billing/Cost Explorer, Fluxo, Pricing OCI, migrations e frontend.

## Limitações deliberadas para 23.19

A 23.18 não implementa dashboard em Settings, gráficos, ROI, reconciliação com Cost Explorer, auto-sync/scraper de pricing, pricing admin UI, FX, savings, findings ou redesign global.

A 23.19 consumirá os read models desta etapa para a experiência visual de Usage & Costs.
