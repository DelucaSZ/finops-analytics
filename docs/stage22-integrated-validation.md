# Etapa 22 — validação integrada e fechamento técnico

## Escopo

Este documento formaliza a Atividade 22.17: validação integrada das entregas 22.1–22.16 sem ampliação funcional. A fonte de verdade analisada foi a `main` no commit `197ce61281b5abc134ca17418296916159c84855`, merge do PR #46 (Atividade 22.16).

A validação combina inspeção direta do código, migrations e testes com a suíte cumulativa executada pelo GitHub Actions. O critério de fechamento da 22.17 é a consistência do repositório, da arquitetura, das migrations, dos contratos e dos gates automatizados do PR. Validações operacionais contra contas AWS/OCI reais são deliberadamente tratadas como uma atividade posterior e não constituem critério de aceite da 22.17.

## Matriz 22.1–22.17

| Atividade | Evidência | Estado final |
| --- | --- | --- |
| 22.1 | PR #31 — tabs de status em Oportunidades abaixo dos filtros | concluída e validada |
| 22.2 | PR #32 — `Scan.cloud_account_id`, migration `0016_provider_neutral_scan_queue` | concluída e validada |
| 22.3 | PR #33 — fila/worker provider-aware e registry de executores | concluída e validada |
| 22.4 | PR #34 — resolução segura de credenciais OCI no worker | concluída e validada |
| 22.5 | PR #35 — OCI Discovery/Inventory | concluída e validada |
| 22.6 | PR #36 — OCI Cloud Advisor | concluída e validada |
| 22.7 | PR #37 — OCI Usage API | concluída e validada |
| 22.8 | PR #38 — OCI Monitoring/MQL | concluída e validada |
| 22.9 | PR #39 — OCI Correlation Engine | concluída e validada |
| 22.10 | PR #40 — primeira Wave de analyzers OCI | concluída e validada |
| 22.11 | PR #41 — coleta manual OCI, migration `0017_oci_manual_collection` | concluída e validada |
| 22.12 | PR #42 — `Executar coleta` provider-neutral em Coletas | concluída e validada |
| 22.13 | PR #43 — scheduling em `CloudAccount`, migration `0018_cloud_account_scheduling` | concluída e validada |
| 22.14 | PR #44 — scheduler OCI no scheduler comum | concluída e validada |
| 22.15 | PR #45 — interface compartilhada de recorrência AWS/OCI | concluída e validada |
| 22.16 | PR #46 — observabilidade, auditoria e taxonomia de erro | concluída e validada |
| 22.17 | PR #47 — validação integrada, reconciliação documental e fechamento técnico | concluída no escopo técnico/documental; publicação na `main` depende de merge explícito |

O `docs/implementation-roadmap.md` foi reconciliado na 22.17 por uma seção final autoritativa da Etapa 22. Essa consolidação substitui, para efeito de estado corrente, anotações históricas intermediárias como “aguardando merge”, sem reescrever o contexto de implementação registrado nas seções anteriores.

## Arquitetura final confirmada

```text
CloudAccount
  |
  +-- AWS -- manual/scheduled
  |           |
  |           -> Scan -> common worker -> AwsCollectionExecutor
  |
  +-- OCI -- manual/scheduled
              |
              -> Scan -> common worker -> OciCollectionExecutor
                                      -> Discovery
                                      -> Cloud Advisor
                                      -> Usage API
                                      -> Monitoring
                                      -> Correlation
                                      -> OCI analyzers

Ambos -> CollectedFinding -> fingerprint/dedup -> Opportunity
                                   -> OpportunityObservation
                                   -> CollectionRun
```

`Scan.cloud_account_id` é a identidade provider-neutral obrigatória. `Scan.account_id` permanece somente como vínculo legado AWS e é nullable para OCI. Não existe `AwsAccount` fictício para tenancy OCI e o tenancy OCID não é gravado em `Scan.account_id`.

`CloudAccount` é a fonte autoritativa de `schedule_enabled`, `scan_interval_hours` e `next_scan_at`. Os campos equivalentes de `AwsAccount` permanecem como mirrors de compatibilidade sincronizados; `OciAccountConfiguration` não possui scheduling.

O scheduler seleciona contas pela capability `scheduling`; o worker seleciona executor por provider. AWS e OCI compartilham scheduler, fila, state machine de Scan, worker, persistência e lifecycle. Azure/GCP permanecem sem capabilities operacionais.

## Capabilities finais

| Capability | AWS | OCI | Azure | GCP |
| --- | --- | --- | --- | --- |
| registration | true | true | false | false |
| editing | true | true | false | false |
| connection_test | true | true | false | false |
| manual_collection | true | true | false | false |
| scheduling | true | true | false | false |
| finops_policies | true | false | false | false |

A capability não substitui RBAC, `CloudAccount.enabled`, estado de conexão nem pré-condições do executor.

## Migrations e integridade

A head da cadeia é `0018_cloud_account_scheduling`.

- `0016_provider_neutral_scan_queue` adiciona e valida `scans.cloud_account_id`, faz backfill dos scans AWS históricos e aplica FK/índice/NOT NULL somente após verificar consistência.
- `0017_oci_manual_collection` torna `scans.account_id` nullable para permitir OCI sem vínculo AWS artificial.
- `0018_cloud_account_scheduling` move a fonte autoritativa do schedule para `CloudAccount`, preservando exatamente `schedule_enabled`, `scan_interval_hours` e `next_scan_at` dos registros AWS e validando o backfill.
- O downgrade de 0018 copia os valores autoritativos de volta para os mirrors AWS antes de remover as colunas comuns.

A suíte de migrations executa banco vazio e banco com dados preexistentes. Em PostgreSQL 17 e SQLite ela confirma a revisão head, `compare_metadata(...) == []`, preservação de contas AWS, Scan, CollectionRun, Opportunity/Finding, OpportunityObservation e decisões humanas. Há teste dedicado para preservação de schedule AWS, inclusive `next_scan_at`.

Não foi criada migration na 22.17 porque não foi encontrada divergência real entre models e schema que a justificasse.

## Fluxos integrados

### AWS manual

O request canônico resolve `CloudAccount`, valida capability/estado, cria Scan, o worker cria CollectionRun, o `AwsCollectionExecutor` executa STS/collectors e o pipeline comum persiste Findings, Opportunities e Observations. Os testes cumulativos cobrem claim, execução, deduplicação, lifecycle e terminação do CollectionRun.

### AWS scheduled

O scheduler comum seleciona `CloudAccount` AWS due, protege contra Scan ativo, cria `trigger=scheduled`, avança `next_scan_at` na mesma transação e entrega ao mesmo worker/executor. Não há executor/scheduler paralelo.

### OCI manual

O endpoint canônico usa `CloudAccount.id`; `Scan.account_id` permanece NULL. O `OciCollectionExecutor` executa Discovery -> Cloud Advisor -> Usage -> Monitoring -> Correlation -> analyzers e devolve `CollectedFinding[]` ao pipeline comum. O pipeline comum persiste a identidade provider-aware, Observation e CollectionRun.

### OCI scheduled

A suíte `test_oci_scheduled_collection.py` cobre scheduler -> Scan scheduled -> common worker -> mesmo `OciCollectionExecutor` -> pipeline completo. Também cobre manual seguido de scheduled reutilizando Opportunities e criando novas Observations.

## Deduplicação, fingerprint e lifecycle

O fingerprint v1 continua baseado em identidade estável: provider, account nativo, região/escopo, service, resource ID e rule key. Trigger, Scan ID, CollectionRun ID, timestamps, evidence e custo corrente não participam. Provider e conta fazem parte da identidade, evitando colisão entre clouds/contas.

O worker usa a unicidade do fingerprint e `UNIQUE(opportunity_id, collection_run_id)` para manter uma Opportunity lógica e uma Observation por execução. O cenário manual -> scheduled OCI é coberto explicitamente: a quantidade de Findings lógicos permanece estável e a contagem de Observations cresce por run.

O lifecycle humano permanece independente da detecção. Uma Opportunity `TREATED` ou `REJECTED` reaparecida mantém a decisão; `TREATED` pode receber `needs_review` conforme regra existente. A suíte OCI scheduled cobre ambos os estados após nova coleta.

## OCI acquisition e analyzers

### Discovery

O Discovery é read-only, pagina APIs, respeita regiões/compartments/root/subcompartments, deduplica por OCID, preserva coverage e partial failures e cobre Compute, Block/Boot Volumes, attachments e Public IP/VNIC conforme necessidade. Não converte ausência por erro em zero.

### Cloud Advisor

Usa `OptimizerClient`, `list_recommendations` e `list_resource_actions`; preserva recommendations/actions separadas, pagina, correlaciona por resource ID quando disponível e mantém native savings como evidência Oracle, não como saving DeepOps. Não chama apply/dismiss/postpone.

### Usage API

Usa janela UTC, `Decimal`, grouping agregado e paginação. Custos sem `resourceId`, créditos/negativos e moedas diferentes são preservados. Moedas incompatíveis não são somadas e não há consulta N+1 por recurso.

### Monitoring

Usa client regional, MQL agregado e `groupBy(resourceId)`. CPU, memória quando disponível e rede são preservadas com coverage; métrica ausente não vira zero. A quantidade de chamadas depende de região/compartment/query, não de número de recursos.

### Correlation Engine

É puro: não chama OCI. Usa OCID como chave, Inventory como âncora, preserva dados unmatched/unallocated, relationships, provenance, coverage e janelas temporais. Saída é determinística/idempotente e usa índices/maps, não nested scans O(N²) entre datasets.

### Analyzers Wave 1

Continuam implementados apenas os analyzers comprovados no código:

- `oci_block_volume_unattached`;
- `oci_public_ip_unassigned`;
- `oci_stopped_compute_with_storage`;
- `oci_untagged_resource`.

Eles exigem coverage suficiente e fatos autoritativos; `unknown` não é tratado como `false`. Não fazem chamadas OCI e não inventam savings. Rightsizing e analyzers adicionais permanecem fora da Etapa 22.

## Falhas, observabilidade e auditoria

O pipeline correlaciona `provider`, `cloud_account_id`, `native_account_id`, `scan_id`, `collection_run_id`, `trigger`, `executor`, `stage` e status em eventos agregados.

A taxonomia operacional distingue configuration, authentication, authorization, rate limit, timeout, provider service, persistence/internal e data coverage conforme o contrato implementado. 403 em Advisor/Usage/Monitoring é cobertura/autorização da fonte e não invalida automaticamente credenciais OCI. Falhas de signing/credential/tenancy são fatais e podem alterar `connection_status`.

Scan e CollectionRun são levados a estado terminal na fronteira do worker. Partial failure OCI termina coerentemente com warnings, sem fabricar zero. Erro de persistência não é classificado como autenticação do provider.

A auditoria cobre request manual e mudanças administrativas de scheduling com ator humano quando aplicável. Uma execução scheduled usa `trigger=scheduled` e não inventa actor humano.

## Segurança

- OCI private key e passphrase permanecem somente como ciphertext em banco; plaintext é resolvido em memória.
- `NUVEMIQ_OCI_CREDENTIALS_KEY` não é persistida no banco/repositório e deve ser a mesma configuração estável para API e worker.
- Respostas de conta não devolvem private key, passphrase nem ciphertext.
- Patch somente de scheduling OCI não reenvia credenciais nem configuração OCI inalterada.
- Scope de CollectionRun não inclui material sensível.
- erros públicos e persistidos são sanitizados; raw SDK config, signer, session AWS e traceback não fazem parte do contrato público.
- o pipeline OCI é read-only: não há create/update/delete/terminate/detach/release/apply/dismiss/postpone no fluxo operacional.
- nenhuma auto-remediation foi implementada.

A 22.17 não introduziu armazenamento adicional de secrets nem nova superfície de credenciais.

## Frontend

A suíte cumulativa confirma:

- Oportunidades com tabs `Abertas / Tratadas / Rejeitadas` abaixo do bloco de filtros, estado em URL, paginação, filtros provider/account e detalhe/evidence;
- Coletas com listagem, filtros, detalhe, comparação, refresh/polling e ação `Executar coleta` capability-driven usando `CloudAccount.id`;
- Settings > Accounts com AWS/OCI, criação/edição/teste de conexão e scheduling provider-neutral;
- scheduling AWS/OCI usando o mesmo componente e lendo/escrevendo somente campos comuns;
- `next_scan_at` read-only e backend-owned;
- updates OCI somente de schedule sem reenvio de secrets;
- Home e agregações provider-aware e currency-aware.

O frontend não fabrica `CollectionRun` depois de POST de coleta; a execução real é criada pelo worker.

## Baseline de validação automatizada

O CI do PR #46, imediatamente anterior à 22.17, foi revisado como baseline:

- backend PostgreSQL 17: `ruff check .` aprovado;
- `ruff format --check .` aprovado;
- `pytest -q`: **548 passed**, 6 warnings de depreciação;
- frontend: `npm test`: **67 passed**, 0 failures;
- `npm run build`: aprovado; o `next build` compilou e executou lint/type checking, gerando 21 páginas;
- job de segurança: aprovado;
- Stage 21 Compose smoke: aprovado no mesmo head da trilha;
- Auto deploy tests: aprovado.

A 22.17 exige que o próprio head do PR #47 também permaneça verde nos gates aplicáveis antes do merge. Warnings de Starlette/FastAPI/Actions e o relatório de dependências npm não são tratados nesta atividade porque não constituem regressão funcional comprovada da Etapa 22 e uma atualização ampla de dependências estaria fora do escopo.

## Validação operacional futura — fora do critério de aceite da 22.17

A validação com contas cloud reais foi explicitamente separada do fechamento técnico desta atividade:

- **OCI real:** não executada na 22.17. Uma coleta contra tenancy autorizada deverá ser realizada futuramente como validação operacional própria.
- **AWS real:** não executada na 22.17. Uma coleta contra conta autorizada deverá ser realizada futuramente como validação operacional própria.
- **Browser E2E/manual em ambiente implantado:** não executado nesta validação; foram usados testes de contrato/frontend, build de produção e smoke Compose automatizado.

Esses itens não são pendências da 22.17 e não reduzem seu status de conclusão. Também não são convertidos em afirmações de smoke real: quando a validação operacional futura ocorrer, deverá ser registrada separadamente com ambiente, escopo, evidências e resultado próprios.

## Limitações reais restantes

- a primeira Wave OCI permanece limitada aos quatro analyzers listados acima;
- métricas de memória dependem da disponibilidade do agent/dados no OCI Monitoring;
- Usage sem resource ID permanece unallocated e não é atribuído heuristically;
- Cloud Advisor/Usage/Monitoring dependem das permissões read-only específicas de cada fonte;
- native estimated savings do Advisor não é automaticamente DeepOps saving;
- rightsizing avançado, novos analyzers e auto-remediation não fazem parte da Etapa 22;
- não existe conversão cambial implícita.

Essas limitações descrevem o produto atual e não são defeitos de fechamento da 22.17.

## Critério de conclusão

A Atividade 22.17 é considerada concluída quando:

1. o estado final 22.1–22.17 está reconciliado no roadmap e nesta validação integrada;
2. a documentação de onboarding OCI descreve o pipeline realmente implementado;
3. não existem regressões funcionais identificadas que exijam correção dentro do escopo;
4. o diff permanece sem nova feature, provider, analyzer, migration ou refactor amplo;
5. o head do PR #47 passa pelos gates automatizados do repositório.

Validação cloud real fica para uma atividade operacional futura e não integra os critérios acima.

## Fechamento

A Etapa 22 deixa uma arquitetura multi-cloud operacional para AWS e OCI, com manual e scheduled convergindo para o mesmo `Scan` provider-neutral, scheduler, fila, worker e pipeline de persistência. OCI acrescenta aquisição read-only, correlação e analyzers locais sem criar pipeline paralelo.

Nenhuma feature nova, provider novo, auto-remediation, analyzer adicional, endpoint OCI específico ou migration foi introduzido na 22.17. Dentro do escopo de repositório, CI, migrations, contratos e documentação definido para a atividade, **a 22.17 está concluída**. A publicação desse fechamento na `main` depende apenas do merge explícito do PR #47.