# Etapa 23.17 — Instrumentação de chamadas CloudWatch do DeepOps

## Objetivo

Esta etapa mede o uso técnico do Amazon CloudWatch realizado pelo DeepOps. Ela não calcula custo monetário, não aplica free tier, não cria tabela de preços e não implementa dashboard de custos.

Billing via AWS Cost Explorer e custo operacional das chamadas CloudWatch do DeepOps são domínios distintos.

## Inventário atual

Na `main` usada como base da implementação, a integração CloudWatch Metrics está concentrada em `backend/app/services/collectors.py` e utiliza somente `GetMetricStatistics`:

- `load_balancer_no_traffic`
  - `AWS/ApplicationELB` / `RequestCount` / `Sum`;
  - `AWS/NetworkELB` / `ProcessedBytes` / `Sum`;
  - `AWS/ELB` / `RequestCount` / `Sum`.
- `rds_nonprod_idle`
  - `AWS/RDS` / `CPUUtilization` / `Average`;
  - `AWS/RDS` / `DatabaseConnections` / `Maximum`.

Não foram encontrados usos atuais de `GetMetricData`, `ListMetrics` ou CloudWatch Logs APIs. Os demais collectors não criam clientes CloudWatch.

O helper `_metric_statistics()` é compartilhado pelos caminhos acima. Os collectors criam o client com `session.client("cloudwatch", region_name=region, config=BOTO_CONFIG)`. `BOTO_CONFIG` usa retry adaptativo do botocore com `max_attempts=6`.

## Semântica de cobrança consultada

Documentação AWS consultada em 2026-10-15:

- Amazon CloudWatch — *Analyzing, optimizing, and reducing CloudWatch costs*;
- Amazon CloudWatch API Reference — `GetMetricStatistics`;
- Amazon CloudWatch API Reference — `GetMetricData`;
- Amazon CloudWatch — *CloudWatch usage metrics*.

A documentação atual classifica:

- `GetMetricStatistics` em `UsageType=Requests`, agregado como API requests; esse UsageType participa do limite de free tier documentado pela AWS;
- `ListMetrics` também em `UsageType=Requests`;
- `GetMetricData` em `UsageType=GMD-Metrics` (bulk get), com estrutura de cobrança distinta; a API aceita até 500 `MetricDataQuery` por chamada e pagina via `NextToken`;
- `GetMetricStatistics` é uma API single-metric e retorna no máximo 1.440 datapoints por chamada. Ela não possui paginação por `NextToken`.

Por isso uma chamada SDK não é assumida automaticamente como uma unidade faturável para todas as operações. A telemetria preserva a operação e as quantidades necessárias para que a 23.18 aplique a semântica correspondente sem reconstruir payloads.

## Arquitetura

`assume_account_session()` devolve um `InstrumentedAwsSession`. O proxy delega todos os serviços AWS sem alteração e envolve somente clientes cujo `service_name` é `cloudwatch`.

Fluxo:

```text
collector
  -> InstrumentedAwsSession
  -> InstrumentedCloudWatchClient
  -> boto3/botocore
  -> buffer process-local
  -> Session.before_commit
  -> batch insert cloudwatch_usage_events
```

A resposta do SDK é devolvida sem transformação. Exceções são registradas e relançadas.

A persistência não cria uma transaction/commit por request CloudWatch. Eventos são acumulados no thread do worker e inseridos em lote no próximo commit SQLAlchemy. O insert de telemetria usa savepoint próprio: se a escrita secundária falhar, o savepoint é revertido, um warning agregado é emitido e a transação principal da coleta pode continuar.

## Modelo `CloudWatchUsageEvent`

A migration `0028_cloudwatch_usage_telemetry` cria `cloudwatch_usage_events` com:

- `id`, `occurred_at` UTC-aware;
- `provider=aws`, `aws_service=cloudwatch`;
- `cloud_account_id` interno, nullable com `ON DELETE SET NULL`;
- `aws_account_id` nativo;
- `region`, `operation`;
- `collector`, `analyzer` quando factual;
- `collection_run_id`, nullable com `ON DELETE SET NULL`;
- `request_count`, `retry_count`, `request_count_is_exact`;
- `metrics_requested`;
- `metric_query_count`, `metric_stat_query_count`, `expression_query_count`, `metrics_insights_query_count`;
- `success`, `error_type`;
- `request_duration_ms`, `aws_request_id`;
- JSON `metadata` estritamente whitelisted.

Não existem campos de preço ou custo.

## Account, region e CollectionRun

A conta vem do `AwsAccount` usado para assumir a role: são preservados tanto `cloud_account_id` quanto o AWS Account ID. A região é obtida do `region_name` usado na criação do client CloudWatch, com fallback para `client.meta.region_name`.

O `CollectionRun` é correlacionado no flush por `Scan.cloud_account_id` e pela janela temporal `started_at <= evento <= finished_at`, aceitando `finished_at IS NULL`. O queue atual impede dois scans `pending/running` simultâneos para a mesma conta, evitando atribuição ambígua. Chamadas fora de um run podem permanecer com `collection_run_id=NULL`; nenhum run artificial é criado.

## Collector/analyzer

A arquitetura AWS atual executa cada consulta CloudWatch diretamente dentro do collector associado à regra. A atribuição factual da versão atual é:

- namespaces ELB -> `load_balancer_no_traffic`;
- namespace RDS -> `rds_nonprod_idle`.

Para operações/namespaces não reconhecidos, `collector` e `analyzer` permanecem nulos. Não existe fan-out de um request para vários analyzers e uma chamada compartilhada não é duplicada.

## Operações e billing dimensions

### GetMetricStatistics

Cada invocação real do wrapper gera um usage event. `metrics_requested=1`, coerente com o contrato single-metric. `statistics_requested` e `period_seconds` são mantidos apenas como metadata whitelisted para auditoria; dimensões, resource IDs e payload completo não são persistidos.

### GetMetricData

Não é usada pela aplicação hoje. O wrapper já sabe registrar, se esse método passar a ser usado pelo mesmo client:

- total de `MetricDataQueries`;
- queries com `MetricStat`;
- expressions;
- Metrics Insights identificável por expressão `SELECT`;
- `MaxDatapoints`, `ScanBy` e presença de `NextToken`.

Cada página executada é um novo método SDK e portanto produz um novo evento. A 23.18 deverá aplicar a regra de preço vigente sem assumir que todas as query classes têm a mesma unidade faturável.

### ListMetrics

Não é usada hoje. Se utilizada pelo client instrumentado, cada chamada/página gera um evento e registra apenas o fato de paginação, sem filtros completos.

## Retries

Botocore já usa retry adaptativo. Quando `ResponseMetadata.RetryAttempts` é fornecido, a telemetria registra `retry_count` e `request_count=1+RetryAttempts`, com `request_count_is_exact=true` para a observação disponibilizada pelo SDK.

Algumas falhas de transporte não expõem `RetryAttempts`. Nesses casos a telemetria grava apenas o mínimo factual (`request_count=1`), `retry_count=NULL`, `request_count_is_exact=false` e `metadata.request_count_basis=logical_minimum`. A 23.18 não deve tratar esse caso como precisão física garantida.

## Segurança e volume

Nunca são armazenados access key, secret key, session token, authorization headers, request payload completo ou resposta CloudWatch completa. `error_type` contém somente código/tipo estruturado, nunca stack trace ou mensagem upstream.

O modelo mantém uma linha por chamada lógica instrumentada, com contagens agregadas dentro do request. Não existe uma linha por métrica, datapoint ou resource. O batch insert reduz round trips de banco e o raw histórico é preservado; purge/rollup automático fica fora desta etapa.

Índices foram definidos para `occurred_at`, `collection_run_id` e combinações de tempo com conta, operação, collector, analyzer e região, refletindo os filtros/read models atuais.

## API de leitura

Endpoints administrativos read-only:

```text
GET /api/v1/usage/cloudwatch
GET /api/v1/usage/cloudwatch/summary
```

Raw events usam paginação `page/page_size` (máximo 200) e filtros por período, conta interna, AWS Account ID, região, operação, collector, analyzer, CollectionRun e success.

O summary é executado no banco e pode agrupar por operação, account, região, collector ou analyzer. Expõe somente contagens técnicas: events, requests, metric queries, metrics requested e falhas.

## Testes

A cobertura focada valida:

- sucesso e preservação semântica da resposta;
- erro AWS relançado com telemetria estruturada;
- retry count e RequestId;
- account/region;
- atribuição RDS/ELB;
- ausência de evento para clients não-CloudWatch;
- `GetMetricData` com query classes e páginas distintas;
- batch flush e correlação com `CollectionRun`;
- raw filters/paginação e summary SQL.

A suíte de migration valida a tabela/índices/FKs e ausência de drift como parte do `pytest` cumulativo em SQLite/PostgreSQL.

## Limitações deliberadas

23.17 não implementa:

- tabela de preços CloudWatch;
- cálculo USD/BRL ou qualquer moeda;
- free tier;
- custo estimado;
- dashboard Usage & Costs;
- integração com Fluxo;
- alteração de AWS Billing/Cost Explorer;
- alteração de OCI/pricing OCI.

A 23.18 é responsável por transformar usage observado em custo estimado. A 23.19 é responsável pela experiência de dashboard/visualização.
