# Atividade 22.16 — Auditoria, observabilidade e tratamento operacional de erros multi-cloud

## Objetivo

Consolidar a trilha operacional comum de AWS e OCI sem alterar a lógica FinOps. A implementação reutiliza `Scan`, `CollectionRun`, `CloudAccountAuditEvent`, logging Python e os executores já existentes. Nenhuma migration ou plataforma externa de observabilidade é necessária.

## Correlação operacional

Execuções passam a produzir eventos agregados com os campos disponíveis entre:

- `provider`;
- `cloud_account_id`;
- `native_account_id`;
- `scan_id`;
- `collection_run_id`;
- `trigger` (`manual`/`scheduled`);
- `executor`;
- `stage`;
- `duration_ms`;
- counts agregados quando reais e disponíveis.

O worker registra lifecycle de enqueue/start/completion/failure e o executor registra estágios. O scheduler registra enqueue e skip por scan ativo sem gerar INFO para cada conta não-due.

## Estágios

AWS usa os estágios operacionais `credentials`, `collectors` e `persistence`. OCI usa `credentials`, `discovery`, `cloud_advisor`, `usage`, `monitoring`, `correlation`, `analyzers` e `persistence`.

Não existe persistência de um evento por recurso. O volume de INFO é proporcional à execução e aos estágios, não à quantidade de recursos.

## Taxonomia de erros

A taxonomia operacional é pequena e independente de payloads raw do SDK:

- `configuration`;
- `authentication`;
- `authorization`;
- `rate_limit`;
- `timeout`;
- `provider_service`;
- `data_coverage`;
- `validation`;
- `persistence`;
- `internal`.

`retryable` é preenchido somente quando a natureza é conhecida, como throttling, timeout e erro transitório de serviço. Esta atividade não implementa retry automático.

Mensagens públicas continuam passando por allowlist. `ProviderExecutionError` preserva o erro original como causa técnica, mas sua própria string é sanitizada e carrega somente metadata operacional segura.

## Authentication x authorization e connection_status

Falha real de autenticação pode invalidar `connection_status`. Falha parcial de autorização em collector/fonte, erro de analyzer, persistência ou serviço do provider não invalida automaticamente a credencial.

OCI mantém a semântica de partial coverage de Cloud Advisor, Usage e Monitoring. AWS mantém `collector_errors` e continua usando os demais collectors quando o comportamento atual permitir.

## Partial failure

Falha parcial não é transformada em zero. O pipeline continua usando dados válidos, registra warnings/collector errors e conclui o `Scan` com o estado de warning já existente. `CollectionRun` permanece `SUCCESS` quando a coleta é utilizável; não foi criado status `PARTIAL` novo.

## Estado terminal

O boundary do worker continua responsável por finalizar falhas fatais. `Scan.error` e `CollectionRun.error_detail` recebem apenas mensagens sanitizadas. Quando existe `CollectionRun`, falha fatal atualiza seu estado para `FAILED` e `finished_at`; o `Scan` recebe `failed` e `completed_at`.

## Auditoria

`CloudAccountAuditEvent` é reutilizado, sem nova tabela. Ações auditadas incluem:

- solicitação de coleta manual com actor humano;
- ativação de scheduling;
- desativação de scheduling;
- alteração de intervalo.

Execuções automáticas são identificadas por `trigger=scheduled` nos eventos operacionais e não recebem usuário humano fictício.

## Segurança e redaction

Não são serializados objetos de credential/config. OCI já usa `repr=False` para private key/passphrase no snapshot em memória. A sanitização pública usa allowlist e testes incluem marcadores artificiais de secrets OCI e AWS.

Não entram em logs/audit/evidence:

- OCI private key, passphrase, encryption key ou signer;
- AWS access key, secret key, session token ou sessão SDK;
- headers de autorização;
- payload completo de request/response do provider.

## Compatibilidade

A atividade não altera:

- fingerprint;
- lifecycle de Opportunities;
- savings/thresholds/regras FinOps;
- fila;
- worker;
- scheduler;
- modelo de scheduling;
- healthcheck;
- retenção;
- schema do banco.

Manual e scheduled continuam compartilhando o mesmo pipeline por provider. AWS e OCI usam a mesma abordagem de correlação, classificação e lifecycle operacional.

## Frontend

Nenhum redesign foi necessário. `CollectionRun.error_detail` e `Scan.error` continuam sendo a fonte sanitizada já disponível para falhas. Não foi criado endpoint de logs, log viewer ou nova página operacional.

## Infraestrutura

Nenhum OpenTelemetry, Prometheus, Sentry, Datadog, ELK, Grafana, Loki, CloudWatch ou OCI Logging foi adicionado como dependência obrigatória.

## Validação

A validação oficial permanece definida pelo workflow `.github/workflows/ci.yml`:

Backend: `ruff check .`, `ruff format --check .`, `pytest -q`.

Frontend: `npm ci`, `npm test`, `npm run build`.

Security: readiness checker e `cfn-lint` da infraestrutura existente.

A atividade deve ser considerada pronta para merge apenas após esses jobs passarem no PR. O merge na `main` fica explicitamente fora desta execução.

## Próxima atividade

22.17 — validação integrada e fechamento da Etapa 22, corrigindo apenas regressões e formalizando o estado final de migrations, AWS/OCI manual e scheduled, coleta, oportunidades, auditoria, observabilidade, segurança e documentação.
