# DeepOps implementation roadmap

Este documento registra o estado real das etapas estruturais do DeepOps para que futuras implementações não dependam do histórico de conversa.

## Etapa 1 — CollectionRun

**Status:** concluída, validada e publicada na `main` em 24/09/2026.

### Resumo

Foi introduzida a entidade `CollectionRun` para representar cada execução efetiva de coleta, separando a execução auditável do objeto legado `Scan`, que continua sendo usado como fila/comando de scan. A criação do run ocorre atomicamente quando o worker reivindica um scan pendente. O run termina como `SUCCESS` quando o scanner conclui e como `FAILED` quando a fronteira do worker captura uma exceção.

A estrutura é provider-neutral no histórico: `provider` é texto e `account_id` guarda o identificador nativo da conta do provider (hoje, o AWS Account ID), sem FK para `aws_accounts`. O vínculo opcional `scan_id` existe somente para compatibilidade com o fluxo legado e para rastreabilidade da migração gradual.

### Decisões técnicas

- `Scan` e `Finding.scan_id` foram preservados para não alterar o comportamento atual das oportunidades.
- `CollectionRun.status` usa `RUNNING`, `SUCCESS` e `FAILED`.
- IDs continuam em UUID textual de 36 caracteres, seguindo `Scan`/`Finding`.
- Timestamps usam `DateTime(timezone=True)` e UTC.
- `provider`, `account_id`, `status` e `started_at` possuem índices individuais; existe também índice composto `(provider, account_id, started_at)`.
- `analyzer_version` foi deixado opcional porque a arquitetura atual não versiona o conjunto de regras/analisadores.
- O contrato legado de `run_collectors` retorna apenas oportunidades e erros, não o total de recursos examinados. Por isso `resources_analyzed` existe desde já, mas fica em `0` no scanner legado até o contrato dos collectors passar a emitir essa telemetria. Não é inferida uma contagem falsa a partir das oportunidades encontradas.
- `opportunities_found` recebe o total exato de resultados produzidos pelos collectors.
- A API de leitura foi adicionada em `GET /api/v1/collections` e `GET /api/v1/collections/{id}`, com filtros por provider, account, status e paginação.

### Migration

- `backend/app/migrations/versions/0005_collection_runs.py`
- Cria somente `collection_runs`; nenhuma tabela existente é recriada ou destruída.
- Não há backfill dos scans históricos: runs representam execuções observadas após a implantação desta etapa.

### Componentes principais afetados

- `backend/app/models/collection_run.py`
- `backend/app/models/__init__.py`
- `backend/app/worker.py`
- `backend/app/api/routes/collections.py`
- `backend/app/schemas/collection.py`
- `backend/app/main.py`
- `backend/app/migrations/versions/0005_collection_runs.py`
- `backend/app/tests/test_collection_runs.py`
- `backend/app/tests/test_migrations.py`

### Testes e validações executados

- GitHub Actions CI do PR #7, run `36055122427`: aprovado.
- Backend: `ruff check .` aprovado; `ruff format --check .` aprovado.
- Backend: `pytest -q` com **153 testes aprovados** e 1 warning em 28,57 s.
- A suite de migrations executou SQLite e PostgreSQL 17 real, confirmou a revisão
  `0005_collection_runs` e `compare_metadata(...) == []`.
- Teste novo confirmou criação de `CollectionRun=RUNNING` no claim do scan.
- Teste novo confirmou finalização `SUCCESS`, `finished_at` e contagem de
  oportunidades em uma coleta simulada bem-sucedida.
- Teste novo confirmou finalização `FAILED`, persistência do erro e
  `finished_at`, sem deixar o run em `RUNNING` após exceção tratada.
- Os testes existentes de findings/oportunidades permaneceram verdes na mesma suite.
- Frontend build aprovado; job de segurança aprovado.
- Auto deploy tests aprovado para o head validado.
- A inicialização de banco/API e a prontidão do worker continuam cobertas pelos
  testes existentes de migrations. Logs dos containers da EC2 de produção não
  foram inspecionados nesta etapa porque a execução foi feita via repositório/CI,
  sem sessão operacional no host.

### Pendências conhecidas

- Instrumentar o contrato dos collectors para produzir a quantidade real de recursos avaliados. O campo já existe para evitar nova mudança de schema.
- `OpportunityObservation`, nova deduplicação/fingerprint e novo lifecycle de oportunidades permanecem fora desta etapa.
- Generalização da entidade de conta para OCI/Azure/GCP permanece fora desta etapa; `CollectionRun` já evita FK específica de AWS.

### Commit

Head de implementação validado antes do merge: `491118e39a26ea1c954684f92f9d1aeb9fb540bd`.

PR #7 publicado por squash merge na `main`: `842c75f0ff843fd4075a458d0fea62dab2d8fd6f`.

## Etapa 2 — Fingerprint determinístico, deduplicação e OpportunityObservation

**Status:** concluída e validada no PR #8.

### Resumo da implementação

- `Finding` permanece como a entidade de oportunidade lógica para preservar a API e o frontend atuais. Não houve renomeação destrutiva de tabela nesta etapa.
- Foi criada `OpportunityObservation`, ligada a `Finding` por `opportunity_id` e a `CollectionRun` por `collection_run_id`, para registrar o snapshot encontrado em cada coleta.
- `Finding` continua mantendo os campos voláteis mais recentes (`evidence`, custos, severidade e confiança) como snapshot de compatibilidade; o histórico verdadeiro passa a residir nas observações.
- `first_seen_at` é preservado desde a primeira detecção e `last_seen_at` só avança quando uma observação mais recente é criada; execuções concorrentes ou fora de ordem não fazem o snapshot atual regredir no tempo.
- Não foi criado `occurrence_count`: a contagem é derivável por `COUNT(opportunity_observations)`, evitando estado redundante.

### Fingerprint

- A geração foi centralizada em `backend/app/services/opportunity_fingerprint.py`.
- O formato v1 usa SHA-256 sobre uma representação JSON canônica e versionada.
- Participam da identidade: `provider`, identificador nativo da conta, `region`, escopo estável do recurso (`service` no coletor AWS atual), `resource_id` e `rule_id`.
- `provider`, região, escopo e regra são normalizados para minúsculas; IDs de conta e recurso têm apenas whitespace removido para não alterar identificadores potencialmente case-sensitive de outros providers.
- Custos, severidade, timestamps, descrição, título, dias de ociosidade e demais evidências não participam do fingerprint.
- O helper é provider-neutral e já aceita identidades de conta/recurso de AWS, OCI, Azure ou GCP sem depender do PK interno de `aws_accounts`.

### Deduplicação e atomicidade

- O worker agrupa resultados pelo fingerprint antes de persistir, então chamadas repetidas do mesmo analyzer dentro do mesmo `CollectionRun` produzem no máximo uma observação.
- `findings.fingerprint` continua protegido por unicidade no banco.
- `opportunity_observations` possui `UNIQUE(opportunity_id, collection_run_id)`.
- Inserts sujeitos a corrida usam SAVEPOINT (`begin_nested`) + tratamento de `IntegrityError` e releitura com `FOR UPDATE`; a deduplicação não depende apenas de `SELECT` seguido de `INSERT`.
- O fluxo faz leitura em lote das oportunidades e observações já existentes para evitar um `SELECT` por item no caminho comum.
- `CollectionRun.opportunities_found` e `Scan.findings_count` passam a registrar o número de oportunidades únicas observadas na coleta, não o número bruto de resultados duplicados emitidos por collectors.

### Compatibilidade com dados existentes

- A migration recalcula os fingerprints legados usando AWS Account ID nativo + região + escopo de serviço + recurso + regra, preservando a identidade lógica do algoritmo antigo sem depender do PK interno da conta.
- Se algum finding não puder ser associado a uma conta AWS ou se o backfill gerar uma colisão determinística inesperada, a migration aborta em vez de fabricar uma identidade.
- Findings cujo `scan_id` já possua `CollectionRun` recebem uma `OpportunityObservation` de backfill usando o último snapshot conhecido.
- Findings anteriores à Etapa 1 permanecem sem observação sintética; na próxima coleta real passam a receber observações normalmente.

### Migration, constraints e índices

- `backend/app/migrations/versions/0006_opportunity_observations.py`.
- Nova tabela `opportunity_observations` com FKs para `findings.id` e `collection_runs.id`, ambas com `ON DELETE CASCADE`.
- Constraint única `uq_opportunity_observation_run (opportunity_id, collection_run_id)`.
- Índices novos em `opportunity_observations.collection_run_id`, `opportunity_observations.observed_at` e `findings.last_seen_at`.
- Não foi criado índice separado em `opportunity_id`, pois a constraint única composta já começa por essa coluna e atende consultas por oportunidade sem índice redundante.
- O downgrade permanece bloqueado por segurança, seguindo a política das migrations de histórico já adotada pelo projeto.

### Principais arquivos

- `backend/app/services/opportunity_fingerprint.py`
- `backend/app/models/opportunity_observation.py`
- `backend/app/models/finding.py`
- `backend/app/models/__init__.py`
- `backend/app/worker.py`
- `backend/app/migrations/versions/0006_opportunity_observations.py`
- `backend/app/tests/test_opportunity_observations.py`
- `backend/app/tests/test_opportunity_migration.py`
- `backend/app/tests/test_migrations.py`

### Testes adicionados

- determinismo do fingerprint e diferenciação por conta, recurso e regra;
- duas coletas consecutivas reutilizando a mesma oportunidade e criando duas observações;
- fluxo integrado `claim_scan -> execute_scan` executado duas vezes para a mesma conta/recurso, confirmando `2 CollectionRuns / 1 Finding / 2 OpportunityObservations`;
- alteração de savings/evidência sem criar nova oportunidade;
- retry da mesma coleta sem duplicar observação;
- recurso/regra distintos gerando oportunidades distintas;
- migration de dados já existentes com e sem `CollectionRun` associado.

### Compatibilidade de API/frontend

- Os endpoints atuais de findings e o frontend continuam consumindo `Finding` sem mudança de contrato obrigatória.
- O fluxo `accepted`/`dismissed` não foi redesenhado nesta etapa; a mudança de lifecycle permanece reservada para a Etapa 3.

### Pendências conhecidas

- A entidade de conta do domínio ainda é AWS-específica (`Finding.account_id -> aws_accounts.id`). O fingerprint e `CollectionRun` já são provider-neutral, mas a generalização completa de contas permanece para a etapa de multi-cloud.
- A API de histórico de observações não foi exposta ainda; a estrutura já está pronta para telas futuras de comparação entre coletas.

### Validação

- Head de código validado antes da atualização documental: `c4ca7adb9b1fe1df03ba746e3b802693eed72567`.
- GitHub Actions CI do PR #8, run `36071610621`: aprovado.
- Backend: `ruff check .` aprovado; `ruff format --check .` aprovado.
- Backend: `pytest -q` com **159 testes aprovados** e 1 warning em 30,67 s.
- A suite de migrations executou a revisão `0006_opportunity_observations` e manteve os testes de schema/migrations em PostgreSQL 17 e SQLite aprovados.
- O teste de duas coletas consecutivas confirmou **1 Finding / 2 OpportunityObservations / 2 CollectionRuns**, preservação de `first_seen_at`, avanço de `last_seen_at` e evidências/savings independentes por coleta.
- O teste de retry confirmou **1 Finding / 1 OpportunityObservation** dentro do mesmo `CollectionRun`.
- O teste de compatibilidade legada confirmou recálculo seguro de fingerprint e criação de observation retroativa somente quando existe `CollectionRun` confiável.
- Frontend build aprovado no mesmo CI; job de segurança aprovado.
- Auto deploy tests do PR #8, run `36071610602`: aprovado.
- Os logs do runner e do PostgreSQL de CI foram revisados durante a validação. Os logs operacionais dos containers da EC2 de produção não foram inspecionados porque esta etapa foi executada pelo repositório/CI, sem sessão operacional no host.


## Etapa 3 — Ciclo de vida das oportunidades

**Status:** concluída e publicada na `main`; o comportamento permanece coberto pelas suítes cumulativas executadas nas etapas posteriores.

### Estados e migração

- Estados correntes: `open`, `treated` e `rejected`.
- Dados legados são migrados por `0007_opportunity_lifecycle.py`: `accepted -> treated`, `dismissed -> rejected` e o antigo `resolved -> open`.
- A migração não inventa ator, timestamp ou motivo para decisões legadas; esses novos campos permanecem nulos quando não existe evidência confiável.
- A resolução automática por ausência em coleta foi removida do worker nesta etapa para separar detecção de decisão humana.

### Decisões humanas e auditoria

- `treated`: registra `treated_at`, `treated_by` e `treatment_note`.
- `rejected`: registra `rejected_at`, `rejected_by`, `rejection_reason` e `rejection_note`.
- Motivos estruturados: `FALSE_POSITIVE`, `OPERATIONAL_EXCEPTION`, `ACCEPTABLE_COST`, `RESOURCE_REQUIRED`, `RISK_ACCEPTED` e `OTHER`; `OTHER` exige observação.
- O ator é obtido exclusivamente do usuário autenticado pelo backend.
- `OpportunityStatusHistory` registra cada transição manual com origem, destino, ação, motivo, nota, ator e timestamp.
- Reabertura é permitida somente de `treated` ou `rejected` para `open`; campos históricos de decisões anteriores não são apagados.

### Reaparecimento em coletas

- Fingerprint e `OpportunityObservation` da Etapa 2 permanecem a identidade e o histórico factual.
- Uma oportunidade `rejected` que reaparece mantém `rejected` e recebe nova observation.
- Uma oportunidade `treated` que reaparece mantém `treated`, recebe nova observation e marca `needs_review=true` quando a nova detecção é posterior ao tratamento.
- Nenhuma nova coleta reabre silenciosamente uma decisão humana.

### API e frontend

- `POST /api/v1/findings/{id}/treat`
- `POST /api/v1/findings/{id}/reject`
- `POST /api/v1/findings/{id}/reopen`
- `POST /api/v1/findings/bulk/action` com semântica transacional.
- `GET /api/v1/findings/{id}/history`.
- A listagem aceita explicitamente `status=open|treated|rejected`.
- A tela de oportunidades passa a permitir consultar abertas, tratadas e rejeitadas, tratar/rejeitar abertas e reabrir decisões anteriores. O redesenho amplo da tela permanece fora desta etapa.

### Migration e arquivos principais

- Migration: `backend/app/migrations/versions/0007_opportunity_lifecycle.py`.
- Modelos: `backend/app/models/finding.py`, `backend/app/models/opportunity_status_history.py`.
- Serviço: `backend/app/services/opportunity_lifecycle.py`.
- API/schemas: `backend/app/api/routes/findings.py`, `backend/app/schemas/finding.py`.
- Worker: `backend/app/worker.py`.
- Frontend: `frontend/app/opportunities/page.tsx`, `frontend/lib/types.ts`, `frontend/components/status-badge.tsx`, `frontend/app/globals.css`.
- Testes: `backend/app/tests/test_opportunity_lifecycle.py`, `backend/app/tests/test_findings.py`, `backend/app/tests/test_migrations.py`.

### Testes e pendências

- Foram adicionados testes de tratamento, rejeição, reabertura, auditoria, transições inválidas e atomicidade da ação em massa; a suite de migration foi atualizada para esperar `0007_opportunity_lifecycle`.
- Os testes existentes de OpportunityObservation continuam responsáveis por deduplicação/fingerprint; o worker foi ajustado para não sobrescrever `treated/rejected`.
- Validação final de CI, build do frontend e execução em PostgreSQL 17 devem ser confirmadas pelo GitHub Actions após a publicação desta implementação.
- Não foi implementada comparação heurística de mudança significativa para rejeitados; a arquitetura preserva observations para uma etapa futura.


## Etapa 4 — API escalável de oportunidades

**Status:** concluída e validada no PR #9; CI completo aprovado antes do merge.

### Estado anterior

A API pública de oportunidades era o endpoint legado `GET /api/v1/findings`, com
`limit/offset`, filtro por ID interno da conta, regra e status. O frontend percorria
essa rota em blocos de até 500 registros e executava busca, severidade, conta e regra
em memória. O histórico exposto em `/findings/{id}/history` era somente o histórico
de decisões humanas da Etapa 3.

### Contrato principal

Foi criada a API `/api/v1/opportunities`, mantendo `/api/v1/findings` como contrato
legado de compatibilidade.

Endpoints de leitura:

- `GET /api/v1/opportunities`
- `GET /api/v1/opportunities/stats`
- `GET /api/v1/opportunities/{id}`
- `GET /api/v1/opportunities/{id}/history`
- `GET /api/v1/opportunities/{id}/status-history`

Ações individuais:

- `POST /api/v1/opportunities/{id}/treat`
- `POST /api/v1/opportunities/{id}/reject`
- `POST /api/v1/opportunities/{id}/reopen`

Ações em massa, com transação atômica:

- `POST /api/v1/opportunities/bulk/treat`
- `POST /api/v1/opportunities/bulk/reject`
- `POST /api/v1/opportunities/bulk/reopen`

### Paginação, filtros e ordenação

A listagem usa paginação server-side por `page/page_size`, com padrão 50 e máximo
200. A resposta contém `items`, `page`, `page_size`, `total` e `total_pages`.

Filtros implementados:

- `provider`;
- `account_id` — Account ID nativo do provider; o ID inteiro interno da conta AWS
  também é aceito temporariamente para compatibilidade;
- `region`;
- `status`;
- `severity`;
- `rule`;
- `collection_run_id`;
- `resource_id`;
- `search`.

A busca textual é feita no banco sobre `resource_id`, `resource_name`, `title`,
`description`, `rule_key` e `service`. Nesta etapa usa `ILIKE`; em volumes muito
maiores poderá evoluir para índice trigram/full-text sem alterar o contrato HTTP.

Campos permitidos para `sort`:

- `created_at`;
- `first_seen_at`;
- `last_seen_at`;
- `severity`;
- `estimated_savings`;
- `status`.

A direção é validada por `order=asc|desc`. Nomes arbitrários de colunas não são
interpolados em `ORDER BY`.

### Histórico

`GET /opportunities/{id}/history` representa exclusivamente o que o scanner viu.
Ele lê `OpportunityObservation`, inclui o contexto do `CollectionRun`, é paginado e
ordena da observação mais recente para a mais antiga.

`GET /opportunities/{id}/status-history` representa exclusivamente decisões humanas
registradas em `OpportunityStatusHistory`, incluindo o ator quando disponível.

O filtro `collection_run_id` também consulta `OpportunityObservation` por
`EXISTS`; portanto uma coleta antiga continua consultável mesmo depois de novas
observações da mesma oportunidade.

### Performance e índices

A listagem executa uma contagem e uma query limitada por `LIMIT/OFFSET`; ela não
carrega todas as oportunidades para paginar em memória. Conta é resolvida no mesmo
join e históricos não são carregados na listagem, evitando N+1.

A migration `0008_opportunity_api_indexes.py` adiciona somente:

- `ix_findings_account_status_last_seen (account_id, status, last_seen_at)`;
- `ix_findings_status_severity (status, severity)`.

Os índices de `OpportunityObservation.collection_run_id`,
`OpportunityObservation.observed_at` e a constraint iniciada por
`opportunity_id` já existiam desde a Etapa 2 e não foram duplicados.

### Segurança e lifecycle

Todas as leituras seguem `require_user`. Treat/reject/reopen e ações em massa seguem
`require_operator`; o ator continua vindo da sessão autenticada. A lógica de
transição permanece centralizada em `opportunity_lifecycle.py`. A ação em massa
bloqueia as linhas selecionadas em uma única leitura, valida IDs e aplica tudo na
mesma transação; erro de ID ou transição provoca rollback completo.

### Compatibilidade

- `GET /api/v1/findings` foi preservado.
- Treat/reject/reopen legados foram preservados.
- `POST /findings/bulk/action` foi preservado.
- Os aliases `PATCH /findings/bulk/action` e `PATCH /findings/bulk/status` foram
  mantidos para consumidores/testes legados. `/bulk/status` aceita tanto o payload
  de ação da Etapa 3 quanto o payload histórico baseado em `status`.
- `PATCH /findings/{id}/status` foi restaurado como compatibilidade controlada:
  `accepted` mapeia para `treated`, `dismissed` para `rejected` e `open`
  reabre quando necessário, sempre usando o service de lifecycle e auditoria.
- `GET /findings/{id}/history` mantém a semântica legada de histórico de decisões.
- O endpoint de IA `POST /findings/{id}/explain` permanece disponível.
- A Home atual continua usando `/dashboard/summary`; não foi redesenhada nesta etapa.

O frontend de oportunidades passou a consumir `/opportunities` com 50 itens por
página e filtros/busca server-side. A evidência continua presente no item da listagem
por compatibilidade com a expansão inline atual; uma separação visual maior entre
lista e detalhe pertence à Etapa 5.

### Principais arquivos alterados

- `backend/app/api/routes/opportunities.py`
- `backend/app/api/routes/findings.py`
- `backend/app/schemas/opportunity.py`
- `backend/app/schemas/finding.py`
- `backend/app/services/opportunity_query.py`
- `backend/app/services/opportunity_lifecycle.py`
- `backend/app/models/finding.py`
- `backend/app/migrations/versions/0008_opportunity_api_indexes.py`
- `backend/app/main.py`
- `backend/app/tests/test_opportunities_api.py`
- `backend/app/tests/test_findings.py`
- `backend/app/tests/test_opportunity_lifecycle.py`
- `backend/app/tests/test_migrations.py`
- `frontend/app/opportunities/page.tsx`
- `frontend/lib/types.ts`

### Validação final

A suite cobre paginação 100/20, status, conta, provider, filtros combinados,
`CollectionRun`, ordenação, busca, detalhe, histórico factual, histórico de decisão,
transições individuais, bulk atômico, stats, limites inválidos e uma verificação de
queries confirmando contagem + SELECT paginado sem N+1.

Resultado do CI do PR #9 antes do merge:

- `ruff check .`: aprovado;
- `ruff format --check .`: aprovado;
- `pytest -q`: **173 testes aprovados**, 1 warning, em 28,50 s;
- `npm run build`: aprovado;
- validações estáticas de segurança/exposição: aprovadas;
- workflow `Auto deploy tests`: aprovado.

A validação de migração roda em SQLite e PostgreSQL 17. O teste de upgrade de banco
legado foi corrigido para criar de fato o schema histórico `0001_legacy`, em vez de
tentar simular o passado com os models ORM atuais.

Também foram corrigidas as violações de formatação deixadas pela Etapa 3 que faziam o
job backend da `main` falhar no `ruff check` antes da implementação desta etapa.

### Pendências deliberadamente fora do escopo

- generalização da entidade persistida de conta, que ainda é `AwsAccount`;
- provider OCI/Azure/GCP real;
- nova Home;
- redesenho completo da tela de oportunidades;
- tela e comparação de coletas;
- full-text/trigram para volumes que justifiquem essa otimização;
- agregações/materializações avançadas.

Esses itens permanecem para etapas posteriores; nenhuma implementação da Etapa 5 foi
incluída aqui.


## Etapa 5 — Workspace operacional de oportunidades

**Status:** concluída e validada no PR #10. O código funcional foi aprovado pelo CI run #86 antes do merge na `main`.

### Estado anterior

A tela já consumia a API escalável da Etapa 4, mas ainda funcionava como uma listagem de transição: status em select, paginação parcialmente local à sessão, busca fora da URL, decisões via `window.prompt()`, ausência de `/opportunities/stats` e sem uma visão de detalhe que reunisse observações e decisões. Isso dificultava refresh, compartilhamento de links, drill-down futuro da Home e a investigação do motivo de um achado.

### Estrutura final da tela

- abas operacionais `Abertas / Tratadas / Rejeitadas`, mapeadas diretamente para `open / treated / rejected`;
- contagens das abas obtidas por `GET /api/v1/opportunities/stats`, sem carregar toda a base;
- filtros combináveis por provider, conta, região, severidade, regra/analyzer, CollectionRun e busca;
- busca com debounce de 350 ms;
- conta apresentada em campo pesquisável via `datalist`, mantendo o identificador nativo como valor;
- provider montado de forma genérica a partir dos CollectionRuns conhecidos, preservando AWS como provider existente;
- CollectionRun limitado às 100 execuções recentes para montar opções, sem usar esse conjunto para filtrar oportunidades no browser;
- status, filtros, busca, paginação, tamanho de página, ordenação e detalhe aberto persistidos na query string;
- filtros restaurados após refresh e preservados ao abrir/fechar detalhe ou usar o histórico do navegador;
- tabela operacional com título, regra, recurso, provider, conta, região, serviço, severidade, status, impacto, custo atual, primeira e última detecção;
- paginação server-side por `page/page_size` e ordenação server-side por campos permitidos pela Etapa 4;
- seleção somente da página carregada, sem representar falsamente uma seleção global do banco.

### Lifecycle e ações

- `OPEN`: ações individuais e em massa de tratar e rejeitar;
- `TREATED` e `REJECTED`: ação individual e em massa de reabrir;
- os prompts nativos foram removidos e substituídos por dialog acessível;
- rejeição usa exclusivamente os motivos reais da API: `FALSE_POSITIVE`, `OPERATIONAL_EXCEPTION`, `ACCEPTABLE_COST`, `RESOURCE_REQUIRED`, `RISK_ACCEPTED` e `OTHER`;
- `OTHER` exige observação no frontend e continua validado pelo backend;
- nenhuma transição é otimista: a UI só atualiza lista/contagens depois do sucesso da API;
- falhas mantêm o contexto visível e informam que a alteração não foi aplicada.

### Detalhe e histórico

O detalhe foi implementado em drawer, identificado por `opportunity_id` na URL. Ele usa:

- `GET /opportunities/{id}`;
- `GET /opportunities/{id}/history`;
- `GET /opportunities/{id}/status-history`.

O drawer mostra contexto comum de cloud/conta/região/serviço/recurso/regra, status, severidade, impacto, custo, primeira/última detecção, total real de observações e decisão atual. A seção de evidência foi renomeada para **“Por que o DeepOps chegou nessa conclusão?”** e continua usando somente a evidência real já persistida; nenhuma explicação factual é inventada no frontend.

Histórico de detecção e histórico de decisões permanecem visualmente separados. O histórico técnico carrega inicialmente somente 8 observações; `Ver histórico completo` habilita paginação de 50 itens por página sob demanda. O histórico de decisão continua separado e limitado à página solicitada da API.

### URL, loading e performance percebida

A lógica de query string foi isolada em `frontend/lib/opportunity-query.mjs`, com declaração TypeScript correspondente. Alterar filtro volta para página 1; paginação explícita preserva a página escolhida. Abrir o drawer não altera a query usada na listagem e, portanto, não dispara refetch da tabela apenas por abrir o detalhe.

Durante refetch, filtros/header/sidebar permanecem montados e a tabela anterior é mantida com indicador local. No primeiro carregamento são usados skeletons. Erros possuem retry local e não desmontam a aplicação. Não foi adicionada biblioteca de cache nesta etapa.

### Componentes e arquivos principais

- `frontend/app/opportunities/page.tsx`;
- `frontend/components/opportunity-detail.tsx`;
- `frontend/components/opportunity-decision-dialog.tsx`;
- `frontend/components/finding-evidence.tsx`;
- `frontend/lib/opportunity-query.mjs`;
- `frontend/lib/opportunity-query.d.mts`;
- `frontend/lib/types.ts`;
- `frontend/app/opportunities-stage5.css`;
- `frontend/app/layout.tsx`;
- `frontend/tests/opportunity-query.test.mjs`;
- `frontend/package.json`;
- `.github/workflows/ci.yml`.

### Testes e validações

Foi criado um conjunto sem dependência adicional, baseado no `node:test`, cobrindo:

- defaults da aba OPEN;
- restauração de status/filtros/paginação/ordenação pela URL;
- contrato exato da query server-side da Etapa 4;
- stats sem status/paginação;
- reset de página quando filtros mudam;
- payloads/endpoints individuais e bulk de treat/reject/reopen;
- validação de `OTHER`;
- mapeamento das três abas para os três estados;
- verificação estática de que a workspace contém stats, detalhe, seleção por página e não voltou a usar `window.prompt()` ou reload completo.

Execução local do módulo de testes antes do PR: **9 testes aprovados, 0 falhas**. No PR #10, o CI run **#86** concluiu com sucesso os jobs **frontend**, **backend** e **security**; no frontend, `npm test` e `npm run build` passaram. O workflow separado **Auto deploy tests #79** também concluiu com sucesso.

### Pendências deliberadas

- não foi criada classificação heurística `Nova / Persistente / Recorrente / Alterada`, porque a API atual não expõe um campo confiável para isso;
- não foi criado filtro de ambiente/categoria, pois a API da Etapa 4 não possui esses filtros;
- a entidade persistida de conta ainda é AWS-específica; a tela usa conceitos comuns e provider genérico, mas a generalização de contas pertence a etapa posterior;
- nenhuma tela completa de CollectionRun/comparação entre coletas foi criada;
- nenhuma explicabilidade avançada da Etapa 6 foi antecipada;
- o teste integrado manual em browser/host operacional depende de uma sessão de execução da aplicação e não é substituído por suposição no roadmap.



## Etapa 6 — Explicabilidade das oportunidades

**Status:** concluída e validada no PR #12. O contrato determinístico de explicabilidade está implementado para os 9 analyzers atuais e a suíte automatizada da etapa está verde.

### Estado anterior

A Etapa 5 já apresentava a seção **“Por que o DeepOps chegou nessa conclusão?”**, porém a interpretação de cada payload de `evidence` acontecia no frontend. `Finding.evidence` e `OpportunityObservation.evidence` continham JSONs específicos por analyzer, incluindo a configuração completa da policy. O detalhe não expunha `latest_observation` de forma explícita e o frontend precisava consultar o histórico separadamente para acessar uma observation. A listagem também carregava o JSON completo de `evidence` em cada item.

### Contrato de evidência adotado

`OpportunityObservation.evidence` continua sendo JSON para permitir domínios diferentes sem criar uma tabela por analyzer, mas novos achados passam a persistir um contrato versionado e mínimo:

- `schema_version`;
- `summary`: conclusão humana curta, determinística e produzida no backend;
- `metrics[]`: `key`, `label`, valor numérico/estruturado, unidade e natureza (`observed`, `estimate` ou `projection`);
- `criteria[]`: valor observado, operador, threshold realmente aplicado e unidade;
- `details`: evidência técnica necessária para auditoria/troubleshooting;
- `parameters`: somente parâmetros relevantes da regra utilizados naquela coleta;
- `rule`: identificador técnico, nome amigável e descrição da regra;
- `source`, `notes`, `contributors[]` e `evaluated_at`.

Não é armazenado HTML. O frontend apenas formata o contrato. Valores monetários preservam número e unidade (por exemplo `USD` e `USD_MONTH`), permitindo novas moedas sem espalhar texto fixo pela UI.

### Estrutura temporal

Não foi criada migration de tabela nesta etapa: `OpportunityObservation.evidence` já é o local correto para a evidência temporal. Cada `CollectionRun` continua gerando sua própria observation e seu próprio JSON de evidência. `Finding.evidence` permanece somente como snapshot mais recente por compatibilidade com endpoints/fluxos legados; ele não é a fonte do histórico.

Observações antigas com o formato anterior são normalizadas no momento da leitura, usando somente campos realmente persistidos. Se uma observation antiga não possui um threshold/configuração, o backend não consulta a policy atual para fingir que aquele valor foi aplicado no passado.

### Analyzers adaptados

Todos os 9 analyzers atualmente registrados em `COLLECTORS` foram mapeados para o contrato:

- `ebs_unattached`: estado, tamanho, tipo, idade desde a criação, custo estimado e thresholds; deixa explícito que idade do volume não é tempo desde o detach;
- `eip_unassociated`: IP/alocação, ausência de associação e custo estimado; não inventa duração sem associação;
- `snapshot_retention`: idade, retenção, excesso em dias, tamanho de origem e custo como limite superior; preserva o aviso de snapshots incrementais;
- `ec2_stopped_with_ebs`: estado, tempo parada quando conhecido, volumes, capacidade total, custo estimado e threshold; quando o horário de parada não é confiável, nenhum número de dias é inferido;
- `ec2_nonprod_outside_hours`: estado observado, horário da observação, timezone, janela permitida, tags de ambiente relevantes e estimativas; não transforma um snapshot em contagem de horas/ocorrências;
- `load_balancer_no_traffic`: métrica, total, datapoints, período, threshold e custo. O texto agora diferencia zero observado, tráfego abaixo de um threshold não-zero e ausência de datapoints;
- `rds_nonprod_idle`: classe/engine, CPU média, conexões máximas, período, thresholds e custo estimado. I/O não é exibido porque o analyzer atual não coleta I/O;
- `missing_required_tags`: tags obrigatórias, tags obrigatórias encontradas e ausentes; tags não relacionadas à policy não são copiadas para a evidência estruturada;
- `cost_growth_anomaly`: período anterior/atual, custo esperado normalizado, custo atual, delta, percentual, thresholds e até 5 contribuidores positivos por `USAGE_TYPE`, quando a consulta adicional ao Cost Explorer está disponível.

### Configuração e thresholds

O `run_collectors` não grava mais uma cópia indiscriminada de `policy_config`. O builder de evidência seleciona apenas os parâmetros relevantes para explicar/reproduzir a decisão. Overrides globais ou por conta já chegam ao collector como policy efetiva, portanto os valores persistidos representam o que foi realmente utilizado na coleta.

Para dados históricos legados, `policy_config` é lido somente quando ele já fazia parte daquela observation. A configuração corrente não é usada como substituto silencioso de configuração histórica ausente.

### Segurança e minimização

A evidência estruturada evita copiar respostas completas de AWS. Tags completas deixam de ser persistidas no novo contrato quando não são necessárias. Regras de ambiente guardam somente as chaves usadas para classificar ambiente; a regra de tagging guarda somente as tags obrigatórias relevantes. Não são incluídos user data, secrets, tokens, credenciais ou connection strings.

### API

- `GET /api/v1/opportunities` não retorna mais o JSON completo de evidência, mantendo a listagem leve;
- `GET /api/v1/opportunities/{id}` retorna `rule`, `latest_observation` e `latest_evidence`;
- a latest observation é obtida por query ordenada e `LIMIT 1`, sem carregar/ordenar todo o histórico no frontend;
- `GET /api/v1/opportunities/{id}/history` continua paginado e cada item retorna sua evidência estruturada específica;
- foram criados schemas explícitos para `OpportunityEvidence`, `EvidenceMetric`, `EvidenceCriterion`, `EvidenceContributor` e `RuleExplanation`;
- o endpoint legado de findings permanece compatível.

A listagem mantém o padrão da Etapa 4 de duas queries limitadas (count + página) e não adiciona join de observation. Detalhe e histórico são carregados somente sob demanda.

### Frontend

`FindingEvidence` não recalcula mais regras FinOps a partir de JSON cru. O componente recebe o contrato do backend e renderiza:

1. resumo/conclusão;
2. métricas principais;
3. critério observado versus threshold;
4. contribuidores quando disponíveis;
5. notas de precisão/estimativa;
6. seção recolhível **“Ver evidência técnica”**.

O drawer apresenta nome e descrição amigáveis da regra, mantém **Histórico de decisões** separado da detecção técnica e permite selecionar **“Ver evidência desta coleta”** em qualquer observation carregada. Ao selecionar uma observation histórica, a seção principal passa a renderizar exatamente a evidência daquela coleta e oferece retorno à evidência mais recente. JSON cru não é exibido por padrão.

O helper antigo `frontend/lib/finding-explanation.ts`, que continha lógica de FinOps no cliente, foi removido.

### Limitações factuais mantidas

Esta etapa não inventa dados que os collectors não possuem:

- EIP: não existe duração sem associação;
- EC2 fora do expediente: não existe contagem histórica de ocorrências nem número exato de horas fora da janela;
- Load Balancer: conexões não são coletadas atualmente; somente a métrica efetivamente consultada é exibida;
- RDS: I/O não é coletado pelo analyzer atual;
- crescimento de custo: contribuidores são por `USAGE_TYPE` no agrupamento serviço/região; atribuição por recurso só será exibida quando a coleta passar a fornecê-la.

Essas limitações não bloqueiam o contrato e podem ser enriquecidas por analyzers futuros sem migration específica.

### Principais arquivos

- `backend/app/services/opportunity_evidence.py`;
- `backend/app/services/collectors.py`;
- `backend/app/services/policies.py`;
- `backend/app/services/opportunity_query.py`;
- `backend/app/schemas/opportunity.py`;
- `backend/app/tests/test_opportunity_evidence.py`;
- `backend/app/tests/test_cost_evidence.py`;
- `backend/app/tests/test_opportunity_observations.py`;
- `backend/app/tests/test_opportunities_api.py`;
- `frontend/components/finding-evidence.tsx`;
- `frontend/components/opportunity-detail.tsx`;
- `frontend/lib/types.ts`;
- `frontend/app/opportunities-stage5.css`;
- `frontend/tests/opportunity-evidence.test.mjs`.

### Testes incluídos

Foram adicionados/ajustados testes para:

- contrato estruturado dos 9 analyzers atuais;
- EC2 parada com dias/capacidade/custo reais;
- ausência de duração de parada sem inferência;
- Load Balancer sem datapoints sem afirmar tráfego zero;
- crescimento anormal com períodos, thresholds, valores e contribuidores;
- minimização de tags na regra de tagging;
- persistência de evidências estruturadas diferentes em dois `CollectionRun` sem sobrescrever a primeira;
- listagem sem payload completo de evidência;
- detalhe com latest observation/latest evidence;
- histórico paginado com evidência correspondente a cada coleta;
- frontend usando o contrato do backend, fallback de evidência ausente e seleção de evidência histórica.

Validação automatizada do PR #12 concluída em 25/09/2026:

- backend: `ruff check .` aprovado, `ruff format --check .` aprovado e **189 testes aprovados**;
- frontend: **11 testes aprovados** e `npm run build` compilado com sucesso;
- security: validações de readiness, exposição pública do Compose e template de Security Group aprovadas;
- Auto Deploy Tests: workflow aprovado.

O teste operacional ponta a ponta contra uma conta AWS real, com backend/worker/frontend do ambiente implantado e duas coletas reais, não foi executado a partir desta sessão. A execução atual possui acesso ao repositório/CI, mas não uma sessão shell no host DeepOps com as credenciais cloud nem um browser conectado ao ambiente implantado. A cobertura automatizada valida explicitamente duas `OpportunityObservation` de `CollectionRun` diferentes e confirma que a segunda evidência não sobrescreve a primeira.

### Fora de escopo preservado

Não foram implementados tela completa de CollectionRun, comparação avançada entre coletas, nova Home, dashboard multi-cloud, cache/materialização global, retenção histórica nem geração por IA como mecanismo principal de explicação. O botão de análise Bedrock que já existia permanece apenas como aprofundamento opcional e separado da explicação determinística/auditável desta etapa.

## Etapa 7 — Workspace de coletas

**Status:** concluída e publicada na `main`; o workspace permanece coberto pelas suítes cumulativas de frontend/backend das etapas posteriores.

### Inspeção da base antes das alterações

Base: `main` em `8905988ad2f4184710fd019174bf7e1a229cd6ea`. Confirmados no código:
Etapa 1 em `CollectionRun`/worker/migration 0005; Etapa 2 em fingerprint,
`persist_findings`, observation e migration 0006; Etapa 3 em lifecycle/migration
0007; Etapa 4 em API/query de opportunities/migration 0008; Etapas 5–6 no workspace,
drawer, histórico paginado e evidência estruturada por observation.

Campos reais de CollectionRun: `id`, `scan_id`, `provider`, `account_id`,
`started_at`, `finished_at`, `status`, `resources_analyzed`, `opportunities_found`,
`analyzer_version`, `error_detail`, `created_at`, `updated_at`. Provider e conta são
texto genérico; `scan_id` é opcional/único, FK para Scan com SET NULL. Estados reais:
RUNNING, SUCCESS, FAILED. Índices individuais em provider/account_id/status/started_at
e composto (provider, account_id, started_at). Observation possui FK para run com
CASCADE, índice collection_run_id e unicidade (opportunity_id, collection_run_id).

O worker cria RUNNING no claim transacional do Scan, finaliza SUCCESS após persistir
achados deduplicados e FAILED na fronteira de exceção. Antes desta etapa, exceções
eram persistidas como texto livre. Falhas parciais dos analyzers resultam em Scan
completed_with_warnings e CollectionRun SUCCESS. Recursos não são medidos (0 é
placeholder), analyzer_version é nulo. Os endpoints existentes são GET /collections
(lista limit/offset com filtros provider/account/status) e GET /collections/{id}.
A tela de oportunidades consome a lista legada limitada a 100 itens.

### Estrutura final e navegação

- Entrada de primeiro nível **Coletas**, mantendo Execuções/Scan legado e demais itens.
- `/collections`: tabela de início/fim, provider, nome e identificador nativo de conta,
  status com ícone/texto, duração, recursos quando disponíveis e oportunidades encontradas.
- `/collections/{id}`: detalhe com UUID completo, contexto, horários com segundos,
  duração derivada, versão dos analyzers, trigger e Scan de origem quando disponíveis,
  contagem factual de observations e erro/avisos sanitizados.
- RUNNING apresenta tempo decorrido, sem percentual inventado ou classificação STUCK.
- Atualização local a cada 15 segundos quando a página está visível e botão Atualizar.
  Shell preservado entre rotas protegidas (autorização continua validada em cada API).
- Skeleton inicial, loading local, retry, 404 e estados vazios distintos. Tabela com
  scroll horizontal local em telas pequenas. Voltar ao histórico preserva sua query.

### API, filtros, paginação e ordenação

Endpoints reaproveitados/evoluídos:

- `GET /api/v1/collections?page=1&page_size=50`: envelope `items`, `page`, `page_size`,
  `total`, `total_pages`, `account_summary`. Máximo 200 por página; UI oferece 25/50/100.
- Compatibilidade: sem page/page_size, a mesma rota mantém o array `limit/offset`
  consumido pela Etapa 5, com limite máximo 200. Não existe endpoint duplicado de listagem.
- `GET /api/v1/collections/{id}`: detalhe leve, sem JSON de evidências nem histórico completo.
- Novo `GET /api/v1/collections/options`: providers conhecidos e sugestões pesquisáveis
  de conta (provider/search/limit; padrão 50, máximo 100, `has_more_accounts`). Busca por
  nome ou ID no banco; contas não AWS/desconhecidas continuam visíveis pelo ID nativo.

Filtros combináveis no servidor: `provider`, `account_id`, `status`, `date_from`,
`date_to`, `analyzer_version`. Datas filtram started_at com intervalo
`[date_from, date_to)`: início inclusivo, fim exclusivo. API aceita offsets e normaliza
UTC; datas sem timezone são UTC. UI edita horários locais e grava ISO com timezone na
URL; oferece também Últimos 30 dias. Estados inválidos/intervalos invertidos retornam 422.

Ordenação server-side: `started_at` (padrão DESC) e `opportunities_found`, com
`order=asc|desc` e desempate por ID. Não há ordenação enganosa somente da página atual.
Duração é derivada, não armazenada; ordenação por duração/recursos não foi exposta.
Filtros, página, tamanho e ordenação sobrevivem a refresh e navegação voltar/avançar.
Aplicar filtros ou alterar tamanho/ordenação retorna à página 1.

### Métricas e integração com oportunidades

- Listagem usa `opportunities_found`, contagem deduplicada persistida pelo worker.
- Detalhe usa `COUNT(OpportunityObservation)` por `collection_run_id`, e não o total
  de Finding nem o último `Finding.scan_id`. Não carrega observations no navegador.
- Link **Ver oportunidades desta coleta** reutiliza `/opportunities` com
  `collection_run_id` explícito. Abre a aba Abertas; Tratadas/Rejeitadas mantêm o filtro,
  conforme explicado na interface. Valores/evidências históricas continuam no drawer.
- Histórico de observations no drawer agora oferece link para `/collections/{id}`.
- Com provider e account_id selecionados, contexto separado consulta última execução
  e última SUCCESS do histórico inteiro, ignorando filtros de período/status da tabela.
  SUCCESS com avisos aparece explicitamente e não é chamada de coleta válida/completa.

### Falhas e proteção de dados

`collection_errors.py` centraliza uma allowlist de mensagens públicas para falhas de
permissão, autenticação, limites, conexão e timeout; erros desconhecidos recebem uma
mensagem genérica. Nunca copia payload, URL, header, token, credencial, SQL ou traceback
arbitrário, mesmo após uma falha de um serviço remoto.

Worker aplica essa proteção antes de gravar erro em CollectionRun/Scan/conta e antes
de registrar a falha no log. Leitura de CollectionRun e Scan aplica a mesma proteção
para registros históricos, sem reescrever dados antigos. O detalhe mostra FAILED com
motivo seguro. SUCCESS associado a Scan completed_with_warnings mostra aviso de
resultado incompleto e motivo seguro, sem inventar novo estado PARTIAL.

### Queries e índices

- Listagem normal: duas queries, COUNT + página com LIMIT/OFFSET, LEFT JOIN de nome de
  conta e status do Scan; não há query por linha nem join de todas as observations.
- Contexto de uma conta/cloud: duas queries adicionais fixas com LIMIT 1.
- Detalhe: leitura do run/contexto, COUNT indexado de observations e Scan opcional.
- Nomes de conta são enriquecidos para AWS, sem excluir providers desconhecidos.
- Migration `0010_collection_workspace`: substitui índices simples account_id/status
  por `(account_id, started_at)` e `(status, started_at)`, evitando manter prefixos
  redundantes. Mantém provider, started_at e `(provider, account_id, started_at)`.
- Reutiliza o índice existente de `OpportunityObservation.collection_run_id`.

### Principais arquivos

- Backend: `api/routes/collections.py`, `services/collection_query.py`,
  `services/collection_errors.py`, `schemas/collection.py`, `schemas/scan.py`,
  `models/collection_run.py`, `worker.py`, migration 0010.
- Frontend: `app/collections/page.tsx`, `app/collections/[collectionId]/page.tsx`,
  `components/collection-workspace.tsx`, `lib/collection-query.mjs` + declaração TS,
  `components/app-shell.tsx`, `components/opportunity-detail.tsx`, `lib/types.ts`,
  `app/globals.css`.
- Testes: `test_collections_api.py`, expectativas de migration em `test_migrations.py`
  e `test_opportunity_migration.py`, `test_collection_runs.py`,
  `frontend/tests/collection-query.test.mjs`.

### Validação e teste integrado

- Ruff check e format aprovados; frontend compilado em produção com as duas novas rotas.
- Frontend: 16 testes node:test aprovados, incluindo query/URL, reset de página,
  sanitização de parâmetros de navegação, link por coleta e duração.
- Backend: **206 testes aprovados**, **11 testes PostgreSQL pulados** por ausência de
  servidor local, 1 aviso de depreciação do TestClient. Suíte cobre filtros, limites de período,
  timezone, paginação, ordenação, detalhe/404, autenticação, compatibilidade legada,
  sanitização de erros históricos/novos, avisos parciais e contagem constante de queries.
- Migração de banco vazio e legado, equivalência metadata/schema e prontidão do worker
  validadas em SQLite. PostgreSQL não disponível localmente; testes correspondentes
  são pulados explicitamente e permanecem configurados para PostgreSQL 17 no CI.
- Teste integrado em Chromium, API FastAPI, worker real e frontend Next.js local,
  com chamadas AWS substituídas por fixtures controladas: 31 runs (29 históricos de
  teste + uma coleta SUCCESS e uma FAILED), 2 contas AWS e histórico de provider OCI.
- Confirmados no navegador: login; shell/navegação; listagem; cloud/conta/status;
  paginação 25 itens e segunda página; refresh mantendo filtros/página; detalhe,
  timestamps/duração; indisponibilidade honesta de recursos; uma observation vinculada;
  navegação à oportunidade filtrada e retorno pelo histórico; FAILED/AccessDenied
  sem segredo simulado; viewport desktop e mobile sem overflow global.
- Console do navegador sem erros JavaScript ou erros de console no teste integrado
  concluído. Logs API/worker revisados: requisições bem-sucedidas e única falha
  intencional sanitizada. Nenhum acesso à conta AWS real/EC2 de produção foi feito.

### Pendências conhecidas e escopo preservado

- Recursos: collectors ainda não medem esse total; zero legado aparece como
  **Não disponível** (`resources_analyzed_available=false`), nunca como zero medido.
- Versão de analyzers permanece **Não registrada** quando o worker não a fornece.
- Novas/persistentes ficam para Etapa 8: backfill da Etapa 2 só preservou snapshots
  disponíveis e oportunidades anteriores ao histórico podem não ter a primeira
  observation original. Não foi inferida classificação falsa a partir de created_at.
- Nenhum motor de comparação, desaparecidas/alteradas, nova Home, materialização,
  cache global, retenção ou novo provider de coleta foi implementado.
- Modelo persistido de conta e execução de collectors continuam AWS-específicos;
  o workspace e CollectionRun aceitam providers/identificadores genéricos.
- Validar coleta e deploy na EC2 real continua sendo uma verificação operacional
  posterior: o teste integrado desta entrega usa AWS simulada, não credenciais reais.

## Etapa 8 — Comparação temporal entre CollectionRuns

**Status:** concluída e validada no PR #13; CI run #113 aprovado antes do merge.

### Pré-condição encontrada

A fonte de verdade no início desta etapa era a `main` em `8905988ad2f4184710fd019174bf7e1a229cd6ea`, com as Etapas 1–6. A Etapa 7 (tela completa de Coletas) não estava publicada na `main` nem em branch disponível. Esta implementação não assume componentes inexistentes: adiciona a comparação e a navegação mínima a partir da tela de Execuções, sem reconstruir ou declarar concluída a Etapa 7.

### Definições

As categorias são mutuamente exclusivas no resumo:

- `NEW`: não existe `OpportunityObservation` da oportunidade lógica na baseline e existe na target.
- `PERSISTENT`: existe observation da mesma oportunidade lógica nas duas coletas e nenhum atributo semanticamente relevante mudou.
- `NO_LONGER_DETECTED`: existe observation na baseline e não existe na target. Significa somente ausência de detecção na target; não implica resolução e não altera lifecycle.
- `CHANGED`: existe observation da mesma oportunidade lógica nas duas coletas e mudou severidade, impacto financeiro canônico, confiança, métrica estruturada relevante, threshold, parâmetro da regra, contribuidores ou detalhe semântico explicitamente suportado.

A identidade usa `OpportunityObservation.opportunity_id`, que referencia o `Finding` persistente protegido pelo fingerprint determinístico da Etapa 2. Título, descrição, posição em lista e ID da observation não participam da equivalência.

### Detection state versus lifecycle

O lifecycle atual (`open`, `treated`, `rejected`) é somente metadado do item comparado. As categorias são derivadas exclusivamente das observations. Uma oportunidade `rejected` ou `treated` presente nas duas coletas continua `PERSISTENT` ou `CHANGED`. Nenhuma transição automática foi adicionada; em especial, `NO_LONGER_DETECTED` não vira `TREATED`.

### Comparabilidade e baseline

Somente CollectionRuns distintos, `SUCCESS`, do mesmo `provider`, mesmo `account_id` nativo e com baseline anterior à target são comparáveis. O schema atual não possui `PARTIAL`.

A baseline automática é a última `SUCCESS` anterior da mesma combinação `provider + account_id`. Runs `FAILED`, `RUNNING`, de outras contas ou providers são ignorados. Para a primeira coleta válida a API retorna `available=false`, `reason=NO_BASELINE`, sem erro 500.

O modelo atual de `CollectionRun` não persiste snapshot de regiões, escopo ou tipo de coleta. Esses atributos não são inferidos. A API emite `SCOPE_METADATA_UNAVAILABLE` para registrar que a comparabilidade atual pôde validar provider/conta, mas não mudanças de configuração de escopo.

### Rules version

O campo real existente é `analyzer_version`; não foi criada coluna duplicada. No contrato de comparação ele é exposto como `rules_version`.

- versões iguais e presentes: sem warning;
- versões diferentes: `RULES_VERSION_CHANGED`, sem marcar tudo como `CHANGED`;
- versão ausente em uma ou ambas: `RULES_VERSION_UNAVAILABLE`.

A versão é contexto interpretativo. A classificação continua baseada nas observations.

### Backend e API

A lógica está centralizada em `backend/app/services/collection_comparison.py`.

Endpoints:

- `GET /api/v1/collections/{target_id}/comparison-options?limit=100`
- `GET /api/v1/collections/{target_id}/compare?baseline_id=...&category=...&page=...&page_size=...`

O endpoint retorna metadata de baseline/target, resumo, resumo financeiro compatível, warnings e a lista paginada da categoria solicitada. Baselines explícitas incompatíveis retornam HTTP 409 com código de negócio legível.

### Estratégia de diff

Cada request carrega somente os dois conjuntos de `OpportunityObservation` envolvidos, em duas queries em lote com join para `Finding`. Não existe query por opportunity e o frontend não baixa os dois históricos para executar diff.

O serviço usa mapas por `opportunity_id`, operações de conjunto para novas/não detectadas e compara apenas a interseção para separar persistentes de alteradas.

A comparação semântica ignora timestamps, IDs técnicos, `created_at`, `evaluated_at`, texto-resumo e ordem de chaves/listas. Métricas de evolução temporal natural como `stopped_days`, `age_days`, `lookback_days` e contagem de datapoints não criam, sozinhas, `CHANGED`. Thresholds, parâmetros, métricas relevantes, contribuidores e detalhes semânticos conhecidos da Etapa 6 são comparados.

Não foi criado um diff universal de JSON.

### Financeiro

O agregado usa exclusivamente `OpportunityObservation.estimated_monthly_savings`, cuja semântica atual é economia potencial em USD/mês. Não soma `current_monthly_cost` com savings, nem agrega métricas `USD` de períodos avulsos.

Retorna `baseline_total`, `target_total`, `delta`, `delta_percent` quando aplicável, `currency=USD`, `period=month` e `metric=estimated_monthly_savings`. Quando ambos os totais são zero, o resumo é omitido.

Mudanças individuais de `current_monthly_cost` ou `estimated_monthly_savings` são registradas como `financial_impact` com unidade `USD_MONTH`.

### Performance e índice

O resumo é server-side. Somente a categoria/página solicitada é serializada na resposta. A estratégia é O(n + m) sobre as observations dos dois runs, e não sobre todas as opportunities da conta.

Foi adicionado:

- `ix_opportunity_observations_run_opportunity (collection_run_id, opportunity_id)`

A constraint única existente `(opportunity_id, collection_run_id)` foi preservada. O novo índice cobre o acesso inverso iniciado pelo run. Migration: `0009_collection_comparison_indexes.py`.

Não foi introduzido Redis, cache global ou materialized view.

### Frontend

Como a Etapa 7 não existe na fonte de verdade atual:

- `/scans` continua sendo a lista operacional e passa a vincular o scan ao `CollectionRun`;
- `/collections/{id}` mostra o run auditável e as ações de investigação;
- `/collections/{target_id}/compare?baseline_id=...&category=...&page=...` é a URL compartilhável;
- a baseline pode ser automática ou manual dentre opções compatíveis;
- cards de Novas, Persistentes, Não detectadas e Alteradas filtram a lista;
- detalhe é paginado pelo backend;
- mudanças são exibidas baseline → target;
- lifecycle é mostrado separadamente;
- cada item abre a oportunidade existente;
- baseline e target podem ser abertas individualmente.

### Principais arquivos

- `backend/app/services/collection_comparison.py`
- `backend/app/api/routes/collections.py`
- `backend/app/schemas/collection.py`
- `backend/app/models/opportunity_observation.py`
- `backend/app/migrations/versions/0009_collection_comparison_indexes.py`
- `backend/app/tests/test_collection_comparison.py`
- `backend/app/tests/test_migrations.py`
- `frontend/app/scans/page.tsx`
- `frontend/app/collections/[collectionId]/page.tsx`
- `frontend/app/collections/[collectionId]/compare/page.tsx`
- `frontend/app/collections/collection.module.css`
- `frontend/lib/types.ts`
- `frontend/tests/collection-comparison.test.mjs`

### Testes incluídos

A cobertura adicionada valida:

- `NEW`, `PERSISTENT`, `NO_LONGER_DETECTED`, `CHANGED`;
- mudança de severidade e impacto financeiro;
- evolução natural `14 -> 15 dias` sem falso `CHANGED`;
- `REJECTED`/`TREATED` sem interferir na categoria técnica;
- delta financeiro em USD/mês;
- warning de rules version;
- baseline automática ignorando `FAILED` e outra conta;
- rejeição de baseline `FAILED`, conta diferente e target inválida;
- paginação;
- exatamente duas queries de observations no caminho principal, sem N+1;
- contrato HTTP e erro 409;
- ausência de baseline como estado informativo;
- contrato/navegação frontend.

Validação automatizada do PR #13, CI run #113:

- `ruff check .`: aprovado;
- `ruff format --check .`: aprovado;
- `pytest -q`: **202 testes aprovados**, 1 warning, em 36,95 s;
- frontend: **13 testes aprovados** e `npm run build` concluído com sucesso;
- security: aprovado;
- Auto Deploy Tests run #106: aprovado.

Uma execução anterior do CI detectou dois problemas antes do merge: o identificador da revisão Alembic excedia o `VARCHAR(32)` do version table PostgreSQL e o percentual `56,25%` usava arredondamento bancário. A revisão foi encurtada para `0009_collection_compare_idx` e o cálculo passou a `ROUND_HALF_UP`; o CI #113 validou as correções em PostgreSQL 17 e na suite completa.

### Limitações e pendências

- `CollectionRun` ainda não registra snapshot de regiões/escopo/tipo da coleta.
- `analyzer_version` ainda pode estar nulo porque o worker não o preenche sistematicamente.
- `Finding`/conta persistida ainda são AWS-específicos.
- o agregado financeiro atual é somente `estimated_monthly_savings` USD/mês; múltiplas moedas exigirão metadata persistida.
- o teste operacional ponta a ponta com alteração real de infraestrutura não é reproduzível apenas pelo repositório/CI sem sessão no host implantado e credenciais do provider; a suite cobre duas coletas e observations controladas.
- não foram implementados nova Home, benchmark entre contas/clouds, cache global ou automação de lifecycle.

Persistir metadata de escopo/região/tipo e uma versão de regras preenchida consistentemente permitirá endurecer a comparabilidade em etapa futura.



### Integração tardia da Etapa 7 — 27/09/2026

O commit local da Etapa 7 não havia sido publicado por falta de credenciais no git
HTTPS. A main avançou para `0ea94dc` (Etapa 8) nesse intervalo. A entrega foi integrada
preservando integralmente o motor, schemas, endpoints e tela de comparação da Etapa 8.
A migration do workspace passa a `0010_collection_workspace`, após
`0009_collection_compare_idx`, evitando duas heads Alembic. A rota dinâmica unificada
usa `[collectionId]`; o detalhe operacional mantém os links Comparar e Comparar com
coleta anterior, cujas opções são carregadas separadamente. As afirmações anteriores
sobre ausência de Etapa 7 na seção 8 descrevem a base histórica daquela implementação.
Os testes das duas etapas foram executados juntos antes desta publicação.

Validação conjunta após integração: **219 testes backend aprovados**, 11 testes
PostgreSQL pulados localmente, **18 testes frontend aprovados**; Ruff check/format
aprovados e uma única head Alembic (`0010_collection_workspace`).


## Etapa 9 — Home operacional multi-account e multi-cloud

**Status:** concluída e validada no PR #14. O head de implementação foi aprovado pelo CI #118 e pelo Auto Deploy Tests #111 antes do merge.

### Estado anterior

A Home consumia um `/dashboard/summary` legado que agregava todos os `Finding`
abertos independentemente da coleta em que foram observados, somava
`estimated_monthly_savings` diretamente no snapshot atual de `Finding`, consultava
`Scan` para atividade recente e carregava `/accounts` no frontend para enriquecer
nomes. A página era explicitamente AWS, possuía o card fixo `9/9` de regras e não
distinguia última execução de última coleta válida.

### Definição formal de estado atual

O estado atual consolidado passa a ser a união das observations da **última
`CollectionRun SUCCESS` de cada par `provider + account_id`** dentro do escopo
selecionado.

Em termos conceituais:

```text
estado atual =
latest SUCCESS(provider A, account X)
+ latest SUCCESS(provider A, account Y)
+ latest SUCCESS(provider B, account Z)
+ ...
```

O backend usa `row_number() over (partition by provider, account_id order by
started_at desc, id desc)` e escolhe `rank = 1` somente após restringir runs a
`SUCCESS`. Não existe `ORDER BY ... LIMIT 1` global para representar o ambiente.

Os únicos estados reais do modelo são `RUNNING`, `SUCCESS` e `FAILED`.
`SUCCESS` é a coleta válida. `FAILED` e `RUNNING` nunca substituem o snapshot
corrente. Um `SUCCESS` associado a `Scan.completed_with_warnings` continua sendo
válido porque o domínio não possui `PARTIAL`; a Home, porém, o identifica
explicitamente na saúde das coletas para evitar interpretação de completude que o
modelo não garante.

### Última execução versus última coleta válida

A saúde das coletas calcula dois rankings independentes por `provider + account_id`:

- última execução: qualquer status;
- última coleta válida: somente `SUCCESS`.

Assim, se `#101 FAILED` vier depois de `#100 SUCCESS`, a Home mostra a falha de
`#101` e continua usando `#100` como fonte do estado atual. A mesma separação é
exposta por conta na tabela compacta de saúde.

Não existe política persistida de atraso/freshness no domínio. A Etapa 9 não inventa
um threshold de “coleta atrasada”; mostra horário da coleta válida mais recente,
horário da mais antiga no consolidado e informa que a política de stale ainda não foi
configurada.

### Filtros e URL

Filtros globais implementados:

- `provider`;
- `account_id` nativo do provider.

A URL é a fonte de estado do filtro, por exemplo
`/?provider=aws&account_id=111111111111`. Refresh, histórico do navegador e links
compartilháveis preservam o escopo. Os providers e contas disponíveis vêm de
`GET /api/v1/collections/options`; não existe lista fixa de clouds no frontend.

Região e ambiente não foram promovidos a filtro global nesta etapa. `CollectionRun`
ainda não persiste snapshot de regiões/escopo e o domínio não possui uma dimensão
provider-neutral confiável de ambiente; expor esses filtros na Home produziria uma
semântica inconsistente entre estado atual e histórico.

### KPIs e definições

Os cards principais são links operacionais:

- **Oportunidades abertas:** `Finding.status = open`, contando cada oportunidade
  lógica uma vez e somente se ela possui `OpportunityObservation` na última
  `SUCCESS` de seu provider/conta.
- **Economia potencial:** soma de
  `OpportunityObservation.estimated_monthly_savings` das oportunidades `open`
  pertencentes ao estado atual. Não soma `current_monthly_cost` nem outras grandezas.
- **Novas desde a coleta anterior:** `NEW` entre a última `SUCCESS` e a
  `SUCCESS` anterior da mesma conta/provider. Escopos sem baseline são excluídos
  dessa contagem e reportados separadamente.
- **Tratadas:** lifecycle `treated` das oportunidades presentes no estado atual.
- **Rejeitadas:** lifecycle `rejected` das oportunidades presentes no estado atual.
- **Falhas na última execução:** quantidade de pares provider/conta cuja execução mais
  recente possui status `FAILED`.

Lifecycle (`open/treated/rejected`) continua independente de detection state
(`NEW/PERSISTENT/NO_LONGER_DETECTED/CHANGED`). Uma oportunidade rejeitada observada
novamente continua rejeitada.

### Mudanças recentes e baseline

O backend ranqueia as duas últimas `SUCCESS` de cada `provider + account_id`.
`NEW` é obtido por anti-join de observations da target contra a baseline da mesma
conta; `NO_LONGER_DETECTED` faz o anti-join inverso. Não existe comparação cruzada
entre contas.

Para uma conta com somente uma `SUCCESS`, a Home registra “sem baseline” e **não**
classifica todo o primeiro snapshot como novo.

`analyzer_version` é usada como contexto: a resposta informa quantos escopos
comparáveis trocaram versão e quantos não possuem versão suficiente para confirmar
igualdade.

A contagem consolidada de `CHANGED` não é aproximada nesta etapa. A Etapa 8 define
`CHANGED` por diff semântico de evidence, parâmetros, critérios e contribuidores;
reproduzir corretamente essa regra em um agregado SQL exigiria duplicar/carregar a
lógica de evidence. A Home deixa `changed` indisponível e direciona a investigação à
comparação de coletas, em vez de produzir um número enganoso.

### Financeiro e moeda

A única métrica financeira semanticamente agregável hoje é
`estimated_monthly_savings`, definida pela Etapa 8 como USD/mês. A API não retorna um
campo global fixo “USD total”; retorna uma coleção de totais por moeda:

```json
{"totals": [{"currency": "USD", "amount": "..."}]}
```

Isso preserva o comportamento real atual e deixa o contrato apto a representar
USD/BRL/EUR separadamente quando a moeda for persistida no domínio. Não foi
implementada conversão cambial implícita.

### Severidade, clouds, contas e principais oportunidades

A distribuição de severidade usa os enums existentes `high/medium/low` e somente
oportunidades `open` do estado atual. Cada linha é clicável e leva ao filtro
correspondente; severidades desconhecidas são contabilizadas como `other` e não são
reclassificadas pela Home.

A distribuição por provider é dinâmica e agrupada no banco. A distribuição por conta
mostra no máximo oito contas ordenadas pela quantidade objetiva de oportunidades
abertas; nomes AWS são apenas enriquecimento opcional por `LEFT JOIN`, sem excluir
providers desconhecidos.

“Oportunidades abertas para atenção” usa critério explícito: maior
`estimated_monthly_savings` do estado atual, com severidade apenas como desempate.
São retornados no máximo cinco itens e cada um abre a oportunidade existente.

### Drill-down e preservação de contexto

Foi introduzido o filtro `current=true` na API de oportunidades. Ele restringe a
listagem/stats às oportunidades observadas na última `SUCCESS` de cada conta do
escopo, permitindo reconciliar exatamente os números da Home.

Exemplos:

```text
/?provider=aws&account_id=111...
  -> /opportunities?provider=aws&account_id=111...&current=true&status=open
  -> /opportunities?provider=aws&account_id=111...&current=true&status=open&severity=high
  -> /opportunities?provider=aws&account_id=111...&current=true&status=treated
  -> /collections?provider=aws&account_id=111...&status=FAILED
```

A tela de Oportunidades mantém `current=true` ao trocar lifecycle, paginação e
demais filtros e sinaliza visualmente que está mostrando o estado atual.

### APIs

Endpoints alterados/criados:

- `GET /api/v1/dashboard/summary?provider=&account_id=`;
- `GET /api/v1/dashboard/collection-health?provider=&account_id=&limit=8`;
- `GET /api/v1/opportunities?...&current=true` e
  `GET /api/v1/opportunities/stats?...&current=true`;
- reutilizado `GET /api/v1/collections/options` para opções de escopo.

A Home faz três requests independentes: summary, collection-health e options. Summary
e health possuem loading/erro local; falha na saúde das coletas não derruba os KPIs e
vice-versa. Os payloads contêm agregados, metadados e no máximo pequenos top-N; não
incluem evidence completo nem históricos.

### Queries e performance

`dashboard/summary` foi desenhado para nove statements agregados/limitados no caminho
atual: seleção de escopos válidos, lifecycle+financeiro, severidade, provider, conta,
top opportunities e três agregações da comparação recente.
`dashboard/collection-health` usa três statements: agregado de saúde, lista compacta
e escopo com dado válido mais antigo.

As consultas usam `COUNT`, `SUM`, `CASE`, `GROUP BY`, window function, `EXISTS`
e anti-joins no banco. O frontend não baixa todas as opportunities,
`OpportunityObservation` ou `CollectionRun` para montar indicadores. Não existe
N+1 por oportunidade/conta no dashboard.

Nenhum índice novo foi criado. A revisão das queries confirmou reaproveitamento dos
índices existentes:

- `collection_runs(provider, account_id, started_at)`;
- `collection_runs(account_id, started_at)`;
- `collection_runs(status, started_at)`;
- `opportunity_observations(collection_run_id, opportunity_id)`;
- `findings(account_id, status, last_seen_at)`;
- `findings(status, severity)`.

Materialized view, tabela de resumo, Redis e cache global permanecem deliberadamente
fora da Etapa 9.

### UX e estados

A primeira viewport prioriza escopo, freshness e seis KPIs investigáveis. Blocos
secundários cobrem severidade, clouds/contas, top opportunities, mudanças e saúde das
coletas. A página usa skeletons locais, mantém shell/header/filtros visíveis e não
bloqueia summary à espera de health.

Estados distintos:

- nenhuma `CollectionRun`: orientação para executar a primeira coleta;
- runs existentes sem `SUCCESS`: alerta de ausência de estado atual válido;
- `SUCCESS` sem oportunidade aberta: mensagem explícita de nenhuma oportunidade;
- erro parcial de summary/health: bloco de erro e retry local.

Gráficos/barras de severidade possuem labels e valores; a informação não depende
somente de cor.

### Segurança

Os endpoints continuam sob `require_user`. A Etapa 9 não introduz autorização
paralela nem contorna as dependências existentes. O produto ainda não possui uma
camada de ACL por conta/provider; portanto não existe regra adicional de escopo para
replicar nesta etapa.

### Principais arquivos

- `backend/app/services/dashboard.py`;
- `backend/app/schemas/dashboard.py`;
- `backend/app/api/routes/dashboard.py`;
- `backend/app/api/routes/opportunities.py`;
- `backend/app/services/opportunity_query.py`;
- `backend/app/tests/test_dashboard.py`;
- `frontend/app/page.tsx`;
- `frontend/app/globals.css`;
- `frontend/lib/dashboard-query.mjs` e `.d.mts`;
- `frontend/lib/opportunity-query.mjs` e `.d.mts`;
- `frontend/app/opportunities/page.tsx`;
- `frontend/lib/types.ts`;
- testes frontend de dashboard/query.

### Testes e validação

A cobertura adicionada inclui:

- lifecycle `open/treated/rejected` sem inflar pela quantidade de observations;
- duas contas usando sua própria última `SUCCESS`;
- última execução `FAILED` preservando a `SUCCESS` anterior como estado atual;
- filtros de provider e conta;
- `NEW` por baseline de cada conta e primeira coleta sem falso “novo”;
- `NO_LONGER_DETECTED` separado de lifecycle;
- warning de mudança de rules version;
- reconciliação entre KPI aberto e drill-down `current=true`;
- contagem constante de queries do summary e health;
- autenticação;
- persistência dos filtros e parâmetros de drill-down no frontend;
- remoção da dependência da Home em `/accounts` para calcular indicadores.

Validação automatizada do head de implementação no PR #14:

- CI #118: aprovado integralmente;
- `ruff check .`: aprovado;
- `ruff format --check .`: aprovado;
- `pytest -q`: **236 testes aprovados**, 1 warning de depreciação do TestClient,
  em 39,11 s;
- PostgreSQL **17.11** inicializado no job backend; as suites de migrations e
  compatibilidade PostgreSQL incluídas no pytest foram executadas no mesmo pipeline;
- frontend: **23 testes aprovados**;
- `next build`: compilação de produção aprovada, 21/21 páginas estáticas geradas;
- security job: aprovado, incluindo readiness checker, exposição do Compose e
  `cfn-lint` do Security Group público;
- Auto Deploy Tests #111: aprovado;
- teste de performance da Etapa 9 confirmou **9 statements** no summary e
  **3 statements** no collection-health, sem crescimento por quantidade de itens;
- teste de drill-down confirmou que `/opportunities?current=true&status=open`
  devolve exatamente as mesmas oportunidades abertas contabilizadas pela Home.

A validação disponível neste ambiente é de repositório/CI. Não houve sessão remota na
EC2 implantada nem acesso a credenciais reais de cloud; portanto não foram afirmados
teste manual do console do navegador em produção, inspeção dos logs dos containers do
host ou uma coleta real contra AWS. O build de produção, API/test client, PostgreSQL
17, migrations, worker/readiness existentes e os testes controlados do fluxo foram
validados pelo pipeline sem introduzir credenciais operacionais.

### Limitações e pendências futuras

- `Finding.account_id` ainda referencia `aws_accounts`; portanto o lifecycle/lista de
  oportunidades continuará AWS até a etapa de generalização do domínio. A Home e
  `CollectionRun` já não dependem de uma lista fixa de providers.
- `CollectionRun` não possui snapshot de região/ambiente/escopo.
- moeda não é persistida por observation; hoje a semântica confiável é USD/mês.
- `analyzer_version` ainda pode ser nula.
- não existe política configurada de atraso de coleta.
- `CHANGED` consolidado permanece na comparação da Etapa 8 até existir estratégia
  correta de agregação do diff semântico.
- cache global/materialização e demais otimizações futuras permanecem fora desta etapa.

---

## Etapa 10 — preparação estrutural multi-cloud

**Status:** concluída e validada em CI. Esta etapa prepara o núcleo para AWS, OCI,
Azure e GCP sem implementar coletores, autenticação ou regras completas para novos
providers.

### Acoplamentos AWS encontrados

A revisão das Etapas 1–9 confirmou que `CollectionRun`, a comparação temporal e o
fingerprint v1 já possuíam parte importante do contrato provider-aware. Os
acoplamentos que impediam a expansão estavam principalmente em:

- `Finding.account_id` como FK inteira obrigatória para `aws_accounts.id`;
- queries de oportunidades usando `INNER JOIN aws_accounts`;
- filtro de provider de oportunidades descartando qualquer valor diferente de AWS;
- tela de Oportunidades carregando contas via `/accounts` e regras via configuração
  global AWS;
- `region` obrigatória e com modelagem curta herdada do inventário AWS;
- ausência de `resource_type`, metadata específica de provider e moeda na entidade
  central;
- fallback de evidence assumindo `AWS inventory` mesmo para regra desconhecida;
- formatação financeira e labels de provider distribuídos pelo frontend;
- logs do worker sem `provider/account_id/collection_run_id`.

Também existem acoplamentos AWS que **permanecem propositalmente específicos**:
`AwsAccount`, `Scan`, assume-role/STS, `boto3`, EC2, EBS, RDS, ELB, CloudWatch,
Cost Explorer, policies atuais e os analyzers/regras AWS. Eles representam a
implementação concreta do provider AWS e não o domínio comum.

### Estratégia de provider

Foi criado `CloudProvider` em `app/core/cloud.py`, com chaves canônicas:

- `aws`;
- `oci`;
- `azure`;
- `gcp`.

O enum representa providers reconhecidos pela arquitetura, não providers
operacionalmente integrados. A UI não cria opções OCI/Azure/GCP artificialmente:
providers e contas exibidos nos filtros continuam derivados dos dados realmente
persistidos.

A apresentação dos nomes também foi centralizada no frontend. O núcleo não depende de
comparações espalhadas como `provider == "AWS"`; verificações AWS restantes servem
somente para enriquecimento/configuração específica desse provider.

### Estratégia de identidade de conta

`Finding.account_id` deixou de significar a PK interna de `aws_accounts` e passou a
armazenar o identificador externo nativo do provider como string.

Exemplos representáveis pelo mesmo domínio:

```text
aws   / 123456789012
oci   / ocid1.tenancy...
azure / <subscription-id>
gcp   / <project-id>
```

Não existe validação global de 12 dígitos. O `account_id` comum suporta IDs não
numéricos e formatos diferentes.

Não foi criada uma tabela `CloudAccount` nesta etapa. `AwsAccount` continua sendo
a configuração operacional segura do collector AWS (role ARN, external ID, regiões,
agendamento etc.). Criar uma entidade universal de credenciais antes de existirem
contratos reais de autenticação OCI/Azure/GCP adicionaria joins e modelagem
especulativa sem benefício para o núcleo.

Para AWS, nome amigável continua sendo enriquecido por `LEFT JOIN` usando
`provider=aws + account_id=aws_account_id`. Providers sem configuração correspondente
permanecem visíveis com o identificador nativo.

### Resource identity e escopo

`Opportunity/Finding` agora possui como contrato comum:

- `provider`;
- `account_id`;
- `region` opcional;
- `service`;
- `resource_id`;
- `resource_name`;
- `resource_type`;
- `rule_key`.

Nenhum ARN é exigido como identidade universal. ARN, OCID, resource group,
availability zone e outros atributos específicos podem ser preservados em
`provider_metadata` quando necessário.

`CollectionRun` ganhou `scope` JSON provider-neutral. Novas coletas AWS registram
snapshot das regiões configuradas. Runs históricos recebem `{}`, pois a migration
não inventa escopo passado.

A comparação continua exigindo mesmo provider e mesma conta. Quando baseline e target
possuem `scope` conhecido, escopos diferentes geram `DIFFERENT_SCOPE`. Quando um
run histórico não possui snapshot, a comparação continua por compatibilidade
retroativa e retorna `SCOPE_METADATA_UNAVAILABLE`.

### Fingerprint e compatibilidade histórica

O algoritmo `opportunity-fingerprint:v1` **não foi alterado**. Ele já inclui:

```text
provider
account_id externo
region/escopo
service/scope
resource_id
rule_id
```

A migration não recalcula fingerprints existentes. Portanto uma implantação da Etapa
10 não faz todas as oportunidades AWS reaparecerem como novas.

Os testes confirmam:

- fingerprint AWS v1 existente permanece bit a bit estável;
- AWS e OCI com os mesmos valores lógicos de conta/recurso/regra não colidem porque o
  provider participa da identidade.

### Migration 0011

Foi criada `0011_multicloud_core.py`.

Para dados existentes, a migration:

1. resolve cada `findings.account_id` antigo pela FK de `aws_accounts`;
2. persiste `provider="aws"`;
3. substitui o ID inteiro interno pelo `aws_account_id` externo;
4. preserva `Finding.id`, fingerprint, lifecycle, evidence, observations e histórico;
5. torna `scan_id` opcional, mantendo-o como link de compatibilidade do fluxo AWS;
6. torna `region` opcional e amplia `region/service`;
7. adiciona `resource_type`, `provider_metadata` e `currency`;
8. adiciona `currency/provider_metadata` às observations;
9. adiciona `scope` ao `CollectionRun`;
10. recria os índices necessários para as consultas provider/account/status.

Se algum Finding legado não resolver para uma conta AWS, a migration falha
explicitamente em vez de gerar identidade incorreta. O downgrade é bloqueado porque
reverter o significado de `account_id` seria potencialmente destrutivo; a recuperação
indicada é backup verificado pré-0011.

### OpportunityObservation e evidence

`OpportunityObservation` continua provider-neutral e ganhou:

- `currency`;
- `provider_metadata`.

O schema de evidence continua baseado em summary, metrics, criteria, details,
parameters e contributors. Não foi criado um schema gigante contendo campos de todas
as clouds.

Regras AWS específicas continuam podendo produzir evidence específica de EC2/EBS/RDS,
CloudWatch ou Cost Explorer. Para uma regra de outro provider que ainda não possua
normalizador dedicado, o fallback não afirma mais que a fonte é `AWS inventory`.

### API e filtros

As APIs principais usam dimensões genéricas:

```text
provider
account_id
region
service
resource_type
rule
collection_run_id
resource_id
```

Foi criado `GET /api/v1/opportunities/options`, que deriva dinamicamente providers,
contas, regiões, serviços, tipos de recurso e regras dos dados persistidos.

O filtro `account_id` utiliza o identificador provider-native. O endpoint legado
`/findings` mantém compatibilidade temporária com a antiga PK inteira AWS,
normalizando-a internamente para o Account ID externo.

### Home e moeda

A Home continua agrupando por `provider + account_id` e não depende de widgets de
EC2/EBS/RDS.

A moeda passou a ser persistida nas opportunities/observations e os agregados
financeiros da Home são agrupados por currency. Valores de moedas diferentes não são
somados implicitamente e não foi implementada conversão cambial.

A implementação manteve o limite anterior de queries do dashboard: o summary executa
9 statements agregados/limitados e collection-health executa 3.

### Frontend

A tela de Oportunidades deixou de depender de `/accounts` para construir o domínio
dos filtros. Ela usa `/opportunities/options` e suporta:

- provider dinâmico;
- conta com ID provider-native e nome opcional;
- região dinâmica e opcional;
- serviço;
- tipo de recurso;
- regra;
- oportunidade sem ARN;
- oportunidade sem `AwsAccount`;
- metadata específica de provider no detalhe.

Labels de provider e formatação financeira foram centralizados em
`frontend/lib/cloud.mjs`. Home, Oportunidades, Coletas e Comparação usam esses
helpers.

A tela de Coletas exibe o `scope` quando disponível. A comparação usa a moeda real
das observations e não assume mais `USD_MONTH` como unidade universal.

### Worker e collector architecture

O worker atual continua consumindo a fila AWS existente, mas persiste a identidade
central a partir do `CollectionRun`:

```text
provider
account_id
scope
collection_run_id
```

Os logs de início/fim/falha incluem provider, conta e CollectionRun.

Não foi criada uma interface vazia de collector apenas por antecipação. O contrato
`CollectedFinding` foi generalizado para resource_type, provider_metadata, moeda e
região opcional, preservando a assinatura posicional anterior para não quebrar
collectors/testes AWS. Um futuro collector OCI/Azure/GCP pode emitir esse mesmo
contrato e reutilizar o núcleo.

### Índices e performance

A Etapa 10 mantém/adiciona índices coerentes com os acessos comuns:

- `findings(provider, account_id, status, last_seen_at)`;
- `findings(account_id)`;
- `findings(provider)`;
- `collection_runs(provider, account_id, started_at)`;
- índices existentes de status, severity, observations e histórico.

Não foi adicionada cadeia obrigatória Opportunity → CloudAccount → ProviderConfig em
toda listagem.

### Segurança e credenciais

Nenhum secret, access key, token, private key ou client secret foi introduzido. A
Etapa 10 não cria armazenamento genérico de credenciais.

Role ARN, External ID e STS continuam restritos ao adapter/configuração AWS existente.
Autenticação OCI/Azure/GCP foi explicitamente deixada para etapas futuras.

### Testes multi-provider

Fixtures estruturais cobrem:

- Opportunity OCI sem linha correspondente em `aws_accounts`;
- account ID OCI não numérico;
- Subscription ID estilo Azure;
- recurso global com `region=None`;
- `resource_type` e `provider_metadata`;
- fingerprint diferente entre AWS e OCI;
- fingerprint AWS v1 estável;
- rejeição de comparação entre providers;
- rejeição de comparação entre escopos conhecidos diferentes;
- Home consolidando AWS + OCI;
- evidence de provider alternativo sem origem AWS falsa;
- filtros frontend com account/region/resource type não AWS;
- UI sem dependência da configuração de contas AWS;
- formatação financeira baseada em currency.

### Validação automatizada

Validação do head funcional da Etapa 10 no CI #130:

- `ruff check .`: aprovado;
- `ruff format --check .`: aprovado;
- backend: **242 testes aprovados**, 1 warning, em 45,22 s;
- frontend: **27 testes aprovados**, 0 falhas;
- `next build`: aprovado, incluindo type-check e 21/21 páginas estáticas;
- security job: aprovado;
- Auto Deploy Tests: aprovado.

A suíte executou PostgreSQL 17 no job backend e cobre migrations, API, worker,
lifecycle, CollectionRun, comparação, Home e compatibilidade existente.

Não houve acesso remoto à EC2 implantada nem uso de credenciais cloud reais nesta
validação. Portanto esta etapa não afirma uma coleta real AWS/OCI/Azure/GCP em
produção; a regressão do fluxo AWS foi validada pela suíte automatizada e contratos
existentes.

### Compatibilidade retroativa

AWS permanece o único collector operacional. O fluxo existente de AwsAccount,
Scan/worker, assume-role, collectors e rules foi preservado.

A mudança de identidade de `Finding.account_id` é feita por migration integral e
atômica; não existem duas fontes persistentes de verdade para a conta da Opportunity.
O enriquecimento AWS por nome é opcional e não bloqueia outros providers.

### Itens explicitamente não implementados

Ficam fora desta etapa:

- collector OCI;
- collector Azure;
- collector GCP;
- autenticação/credenciais desses providers;
- CloudAccount universal;
- equivalência universal de regras/serviços;
- catálogo fixo de regiões de outras clouds;
- conversão cambial;
- feature/capability framework completo;
- plugin framework, SDK universal, event bus ou microservices por cloud.

A próxima integração de provider pode seguir o fluxo:

```text
provider collector
  -> CollectionRun(provider, account_id, scope)
  -> Opportunity(provider, account_id, resource identity)
  -> OpportunityObservation
  -> APIs atuais
  -> Home / Oportunidades / Coletas / Comparação
```

sem reescrever o núcleo implementado nas Etapas 1–9.

---

## Etapa 11 — otimização de performance e navegação do frontend

**Status:** concluída e publicada na `main`. A validação original e as suítes cumulativas posteriores confirmam cache, navegação e preservação de contexto. A documentação original desta
etapa antes da publicação no `main`.

### Diagnóstico

A aplicação já utilizava Next.js App Router e o `AppShell` estava corretamente
posicionado no `RootLayout`. Sidebar e navegação principal já usavam `next/link`
e não eram remontadas entre rotas privadas. Portanto a principal sensação de reload
não vinha de hard navigation do shell.

Os gargalos encontrados estavam no server-state do cliente:

- Home mantinha summary, collection-health e options em estados locais alimentados por
  três `useEffect` independentes; ao voltar para a rota, os três GETs eram executados
  novamente e a tela reconstruía o estado do zero;
- Oportunidades repetia options, picker de CollectionRun, listagem e stats após
  remontagem, apesar de filtros e paginação já estarem corretamente persistidos na URL;
- detalhe de oportunidade executava novamente detail + observation history + status
  history a cada abertura, sem compartilhar resultado com prefetch ou visitas recentes;
- Coletas mantinha list/detail/options em estado local e incrementava `revision` a
  cada 15 segundos, refazendo requests mesmo sem qualquer `CollectionRun RUNNING`;
- Comparação buscava novamente comparação e opções de baseline em cada montagem e
  mudança de página/categoria;
- `api()` centralizava autenticação e erros, mas não possuía timeout de request;
- não existia TanStack Query, SWR, RTK Query, Apollo ou outra camada de server-state.

Os redirects com `window.location.assign` encontrados em `api.ts` são restritos a
401 e enrollment MFA. Eles permanecem como navegação completa por serem fronteiras de
sessão/autenticação, não navegação interna normal.

As telas administrativas/configurações continuam usando fetching explícito onde a
freshness de segurança é mais importante que reaproveitamento prolongado, especialmente
sessões, MFA, usuários e TLS. O shell continua estável nessas rotas e a nova limpeza de
cache impede reutilização de dados privados após troca de sessão.

### Estratégia de server-state

Foi adotada uma camada pequena e centralizada, sem dependência nova:

- `frontend/lib/query-cache.mjs`: cache em memória, deduplicação de requests
  simultâneas, stale time, retenção, invalidação por prefixo e limpeza;
- `frontend/lib/query-keys.mjs`: keys determinísticas e políticas comuns;
- `frontend/lib/server-state.ts`: hook `useApiQuery`, prefetch e helpers de
  invalidação/limpeza.

TanStack Query foi avaliado, mas não foi introduzido nesta etapa. A aplicação possui
um conjunto pequeno de telas operacionais e a necessidade atual é coberta pela camada
acima sem troca de stack nem alteração de `package-lock.json`. A implementação evita
caches paralelos por tela: toda a nova estratégia operacional passa pelo mesmo store.

O `fetch` de `api.ts` continua com `cache: "no-store"`. O cache é exclusivamente
em memória na SPA autenticada e é descartado nas fronteiras de sessão.

### Query keys principais

As identidades incluem todos os parâmetros que alteram resultado. Exemplos:

```text
["dashboard", "summary", { provider, account_id }]
["dashboard", "health", { provider, account_id }]

["opportunities", "list", serialized_api_query]
["opportunities", "stats", serialized_stats_query]
["opportunities", "options", { provider, account_id }]
["opportunities", "detail", opportunity_id]
["opportunities", "history", opportunity_id, { page, page_size }]
["opportunities", "status-history", opportunity_id]

["collections", "list", serialized_api_query]
["collections", "detail", collection_run_id]
["collections", "options", { provider, search, limit }]
["collections", "comparison", {
  target_id,
  baseline_id,
  category,
  page,
  page_size
}]
["collections", "comparison-options", target_id]
```

A serialização do cache ordena chaves de objetos de forma determinística. Provider e
`account_id` participam da identidade das queries em que alteram o resultado.

### Políticas de stale/cache

Políticas adotadas:

- dados operacionais de lista/dashboard: `staleTime = 45s`, retenção de 5 min;
- detalhes: `staleTime = 2 min`, retenção de 10 min;
- metadata/options: `staleTime = 5 min`, retenção de 30 min;
- comparação: `staleTime = 2 min`, retenção de 15 min.

O cache não é infinito. Entradas sem listeners são removidas quando ultrapassam sua
janela de retenção durante a manutenção oportunística do cache.

### Navegação e loaders

Home, Oportunidades, Coletas e Comparação agora distinguem primeiro carregamento de
revalidação:

- cache válido é renderizado imediatamente;
- dado stale pode permanecer visível enquanto ocorre refresh em background;
- skeleton/tela de carregamento é reservado ao primeiro carregamento sem dado;
- filtros e shell permanecem estáveis;
- falha de revalidação não apaga dado válido já cacheado.

`keepPreviousData` foi aplicado apenas em transições seguras, como paginação dentro
do mesmo escopo. A identidade do placeholder inclui provider, conta e demais filtros.
Troca AWS/Conta A -> OCI/Conta B não reaproveita visualmente a página anterior.

Os filtros e paginação continuam sendo preservados pela URL, conforme as Etapas 5 e
7. O cache complementa essa persistência: voltar de detail para list consegue mostrar
a página já visitada sem reconstruir o server-state.

### Prefetch

Prefetch foi mantido seletivo:

- hover de uma oportunidade -> detalhe da oportunidade;
- página de oportunidades -> próxima página, quando existe;
- hover de uma coleta -> detalhe do CollectionRun;
- comparação -> próxima página;
- hover de oportunidade na comparação -> detalhe da oportunidade.

Não existe prefetch em massa de todas as linhas nem preload global da aplicação.
Next App Router já fornece code splitting por rota; não foi adicionada fragmentação
manual de componentes pequenos.

### Mutations e invalidação

Após `treat/reject/reopen`, a aplicação não usa mais `reloadKey` para reconstruir
manualmente os dados. A mutation invalida:

```text
["opportunities"]
["dashboard"]
```

Queries montadas relacionadas revalidam; variantes não montadas ficam marcadas como
stale e revalidam quando voltarem a ser usadas. CollectionRun não é invalidado por
lifecycle porque `opportunities_found` representa detecção da coleta, não estado
humano posterior.

Optimistic update não foi introduzido nesta etapa. O domínio de lifecycle possui
efeitos em listas, contagens e dashboard, e a invalidação seletiva fornece consistência
com complexidade menor.

### Deduplicação, concorrência e erros

Requests simultâneas com a mesma key compartilham a mesma Promise. Respostas de filtros
antigos são escritas somente na key antiga; por isso uma resposta lenta de um escopo
anterior não sobrescreve o estado do escopo atual.

Não há retry automático para 400/401/403/404. A camada preserva o erro e permite retry
explícito pela UI.

`api.ts` passou a aplicar timeout de 30 segundos. Sinais de abort fornecidos pelo
caller continuam sendo respeitados. Endpoints que permanecerem lentos mesmo com cache
devem ser tratados na Etapa 12 em vez de receber timeout artificialmente maior ou
cache infinito.

### Polling de CollectionRun

O polling de 15 segundos deixou de executar em toda permanência na tela de Coletas.

Agora ele só existe enquanto:

```text
detail.status == RUNNING
ou
algum item visível da lista está RUNNING
```

e somente com a aba visível. Ao chegar em `SUCCESS` ou `FAILED`, o polling para.

### Cache, autenticação e autorização

O cache é apagado quando:

- logout é concluído;
- a aplicação entra em uma rota pública de autenticação;
- a API sinaliza 401/expiração de sessão;
- o fluxo exige enrollment MFA.

Isso cobre logout normal, logout-all/self-revocation que redirecionam para login e
troca de sessão. Nenhum payload privado é gravado em localStorage/sessionStorage.

O modelo de autorização não foi alterado.

### Comparativo estático antes/depois

A comparação abaixo é derivada do fluxo do código, não de benchmark inventado:

- Home recém-montada: continua com três endpoints independentes, porém voltar à Home
  dentro do `staleTime` reaproveita os três resultados em memória em vez de começar
  com três GETs e tela vazia;
- Oportunidades: list/stats/options/picker deixam de ser reconstruídos em toda volta à
  rota; paginação pode reaproveitar página anterior e prefetch da próxima;
- detalhe: detail/history/status-history passam a ter keys independentes e reutilizáveis;
- Coletas: remove-se o refetch periódico de list/detail/options quando não existe run
  em andamento;
- Comparação: options de baseline deixam de ser acopladas ao fetch de cada página e a
  resposta paginada passa a ser cacheada pela identidade completa;
- duas solicitações simultâneas da mesma key passam a produzir uma única chamada de
  rede.

Medições de latência real e waterfall do navegador implantado não são afirmadas por
esta etapa porque o ambiente de execução do repositório não fornece uma sessão remota
do browser de produção.

### Testes e validação

Foram adicionados testes unitários do cache cobrindo:

- serialização determinística;
- isolamento provider/account;
- identidade de comparação por baseline/categoria/página;
- invalidação por prefixo;
- deduplicação de requests simultâneas;
- reaproveitamento dentro do `staleTime`;
- refetch após invalidação;
- limpeza de cache privado.

A validação automatizada da etapa executa o conjunto existente do frontend e backend,
`npm test`, `next build`, ruff/pytest e o job de segurança do CI. Os resultados
finais do pipeline são registrados na entrega da Etapa 11.

### Principais arquivos

- `frontend/lib/query-cache.mjs` e `.d.mts`;
- `frontend/lib/query-keys.mjs` e `.d.mts`;
- `frontend/lib/server-state.ts`;
- `frontend/lib/api.ts`;
- `frontend/components/app-shell.tsx`;
- `frontend/app/page.tsx`;
- `frontend/app/opportunities/page.tsx`;
- `frontend/components/opportunity-detail.tsx`;
- `frontend/components/collection-workspace.tsx`;
- `frontend/app/collections/[collectionId]/compare/page.tsx`;
- `frontend/tests/server-state.test.mjs`.

### Gargalos deixados para a Etapa 12

Esta etapa não altera SQL, materialized views, Redis, tabelas de resumo, workers de
agregação, particionamento ou retenção.

Se `dashboard/summary`, comparação, listagens ou detalhes continuarem lentos no
primeiro carregamento sem cache, o próximo diagnóstico deve medir o backend e o banco.
O cache da Etapa 11 melhora navegação recorrente, mas não é tratado como correção para
endpoint estruturalmente lento.


## Etapa 12 — performance do backend e banco

**Status:** concluída e validada. CI do PR #17 aprovado no código
`7ee31586975ab425f512de2ce4e6fc028616df8e` (run `36467922841`).

Base conferida diretamente: `db654436627e3956bcf72f7ee3e971a32a3d33f8`, incluindo
CollectionRun, fingerprint/observations, lifecycle, APIs/telas/evidence, coletas,
comparação, Home, domínio multi-cloud e cache da Etapa 11. Código é a fonte de verdade.

- Home: severidade compartilhada com agregação SQL por moeda/lifecycle, 9 → 8 queries;
  última SUCCESS por provider/conta e saúde da última execução mantidas.
- Oportunidades: listagem exclui evidence/notas/configuração sensível de conta do SELECT;
  COUNT/stats sem JOIN desnecessário; legado account PK via EXISTS; sem N+1 ou alteração
  de total/paginação/ordem/filtros/autorização. Detalhe/histórico seguem sob demanda.
- Comparison: SQL para totais financeiros/counts, interseção e anti-join; NEW/ausentes
  paginados no banco; CHANGED/PERSISTENT em lotes de 200, mantendo só a página de saída.
  Teste sintético reduz objetos ORM de 1.402 para 2, mantendo todos os hashes de payload.
- Coletas: mantém listagem paginada sem consultas por linha; detalhe inclui warning e
  trigger no JOIN existente (3 → 2 queries quando scan vinculado).
- Worker: fecha transação de leitura antes de chamadas externas; recarrega estado antes
  da persistência. Locks/savepoints/constraints e atomicidade de lifecycle preservados.
- Nenhum índice adicionado/removido, migration ou mudança de pool/timeouts. Sem cache
  de backend/materialização. JSON continua JSON, sem GIN/pg_trgm sem caso comprovado.
- Novo harness `backend/benchmarks/backend_reads.py`, isolado de dados reais, com opção
  de EXPLAIN e PostgreSQL de testes. Testes de contratos/carregamento também em PG no CI.

Baseline, números completos antes/depois, inventário de índices, planos observados,
revisão de transações/pool, experimentos descartados e limites estão em
[`docs/backend-performance.md`](backend-performance.md).

Validação local: 233 testes backend aprovados (12 PostgreSQL ignorados sem serviço
local), ruff/format aprovados; 34 testes frontend e build Next aprovados. O pipeline
valida PostgreSQL 17; não confundir com benchmark de produção. Teste integrado usa
collectors sintéticos, sem acesso AWS real. Não houve deploy operacional na EC2.

Pendências Etapa 13: custo O(interseção) de CHANGED, agregados da Home repetidos,
escopos JSON de baselines, planos/históricos longos em PostgreSQL e concorrência.
Não houve avanço de implementação para Etapa 13.

Teste integrado Chromium aprovado em Home, filtros, detalhes, históricos, coletas,
comparação e lifecycle individual/em lote, sem erros JavaScript. Em teste adicional
com 4.500 snapshots por run, comparação CHANGED caiu de 672,17 para 139,85 ms e
14.002 → 2 objetos ORM. Ambos os datasets mantiveram os 11 payloads idênticos.

Validação final remota: **245 testes backend aprovados**, incluindo PostgreSQL 17
(45,96 s), ruff/format aprovados, frontend/testes/build e segurança aprovados;
Auto deploy tests run `36467923015` aprovado. A documentação posterior a esse head
apenas registra esses resultados; não altera o código validado.

## Etapa 13 — agregação persistida da Home

**Status:** concluída e validada no PR #18. A implementação foi motivada pelo gargalo
remanescente da Etapa 12 em `GET /dashboard/summary`: 8 queries e 129,58 ms no dataset
sintético padrão, com repetição de agregados que só mudam após nova coleta válida ou
decisão humana.

### Estratégia escolhida

Foi adotada uma **summary table corrente por `provider + account_id`**, sem Redis,
materialized view ou cache de backend adicional. A fonte de verdade continua sendo
`Finding`/Opportunity, `OpportunityObservation`, `CollectionRun` e histórico de
lifecycle; `dashboard_account_summaries` é exclusivamente derivada e reconstruível.

Cada linha representa a última `CollectionRun SUCCESS` comparável daquela conta e
persiste somente dados reutilizados pela Home:

- lifecycle: `open_count`, `treated_count`, `rejected_count`;
- severidade corrente: high/medium/low/other;
- economia potencial mensal, preservada por moeda;
- `new_count` e `no_longer_detected_count` em relação à mesma baseline da Etapa 8;
- referência da coleta atual e da baseline;
- flags de baseline e de mudança/desconhecimento de `rules_version`;
- `updated_at`.

Não são materializados Top 5, saúde de coleta, histórico detalhado nem `CHANGED`.
Top opportunities continua sendo uma query indexada com LIMIT 5. Saúde continua em
`CollectionRun`, o que preserva a distinção entre última execução e última coleta
válida sem duplicar `last_execution_status`. `CHANGED` mantém a comparação semântica
de evidence da Etapa 8 e segue calculado sob demanda.

### Atualização e consistência

Ao concluir uma coleta, o worker primeiro confirma `CollectionRun SUCCESS` e os dados
operacionais. Em seguida reconstrói o summary da conta em transação separada. Falha no
rebuild é registrada e revertida somente na camada derivada; não converte uma coleta
válida em FAILED.

Uma coleta FAILED nunca avança `collection_run_id` do summary. Assim, com `#100
SUCCESS` e `#101 FAILED`, o estado consolidado continua em #100, enquanto
`/dashboard/collection-health` informa #101 como última execução.

TREAT/REJECT/REOPEN recalculam lifecycle, severidade e financeiro da conta afetada na
mesma transação da decisão. Bulk deduplica `provider/account` e recalcula uma vez por
escopo, em vez de uma vez por oportunidade. A linha de summary é bloqueada com
`FOR UPDATE` antes do recálculo para serializar writers da mesma conta e evitar drift;
contas diferentes permanecem independentes.

A baseline é obtida por `previous_comparable_run()`, reutilizando exatamente a
semântica da Etapa 8. Primeira coleta sem baseline produz contagens comparativas zero,
sem classificar artificialmente todos os achados como NEW.

### Multi-account, multi-cloud e financeiro

A identidade persistida é a chave composta `(provider, account_id)`; portanto AWS e
OCI com o mesmo identificador textual não compartilham summary. `AwsAccount` continua
apenas enriquecendo nome para AWS, conforme a arquitetura real da Etapa 10.

Financeiro é armazenado como `estimated_monthly_savings`, período `month`, com totais
separados por `currency`. Não há soma implícita entre USD/BRL/EUR e não foi introduzido
sistema cambial.

### Cache, TTL e invalidação

Não foi criado cache de backend. Logo não existe TTL, cache key, stampede ou invalidação
de resposta a administrar nesta etapa. O cache frontend da Etapa 11 permanece com sua
política existente e é invalidado pelas mutations já implementadas. A atualização do
summary é dirigida por eventos de domínio e por reparo/rebuild, não por expiração.

### Recovery, backfill e freshness

`python -m app.commands.rebuild_dashboard_summaries` reconstrói dados derivados a
partir da fonte operacional. O comando aceita filtro por provider/conta e por
CollectionRun corrente; o backfill global trabalha em lotes e sempre resolve a última
SUCCESS antes de publicar o estado corrente.

A migration não executa um backfill potencialmente bloqueante. Em instalações já com
histórico, o comando faz o preenchimento inicial; adicionalmente, a Home detecta summary
ausente/stale, tenta reparar o escopo e, se o reparo falhar, usa o cálculo direto antigo
como fallback correto. Summary nunca é tratado como autoridade sobre os dados
operacionais.

### Migration e índices

Nova revisão: `0012_dashboard_summaries`.

A tabela usa PK composta `(provider, account_id)`, FKs para target/baseline
`CollectionRun` e índice UNIQUE em `collection_run_id`. Não foram adicionados índices
em JSON, materialized views ou infraestrutura Redis.

### Benchmark

Mesmo dataset sintético padrão da Etapa 12: 20 contas, 10.000 opportunities, 2.000
CollectionRuns e 98.000 observations; mediana de três requests.

| Medida | Etapa 12 | Etapa 13 |
|---|---:|---:|
| SQLite `/dashboard/summary` | 129,58 ms / 8 queries | 38,11 ms / 2 queries |
| Payload da Home | 3.541 bytes | 3.541 bytes |
| SQLite backfill 20 escopos | n/a | 197,32 ms |
| SQLite rebuild 1 conta | n/a | 8,74 ms |
| PostgreSQL 17 `/dashboard/summary` | sem baseline publicado | 37,66 ms / 2 queries |
| PostgreSQL 17 backfill 20 escopos | n/a | 289,45 ms |
| PostgreSQL 17 rebuild 1 conta | n/a | 11,31 ms |

A redução observada da Home SQLite em relação ao estado pós-Etapa 12 foi de
aproximadamente 70,6% em latência e 75% em número de queries. Esses números são de
harness sintético/CI e não constituem SLA de produção.

### Testes e arquivos principais

CI final da implementação aprovou 250 testes backend em PostgreSQL 17, ruff, format,
frontend tests/build, segurança e auto-deploy tests. O benchmark Stage 13 também passou
em SQLite e PostgreSQL 17.

Arquivos principais: `app/models/dashboard_summary.py`,
`app/services/dashboard_aggregation.py`, `app/services/dashboard.py`,
`app/services/opportunity_lifecycle.py`, `app/worker.py`,
`app/commands/rebuild_dashboard_summaries.py`,
`app/migrations/versions/0012_dashboard_summaries.py` e
`benchmarks/backend_reads.py`.

### Limitações e pendências

A etapa não materializa CHANGED/PERSISTENT, não altera retenção, não cria novos
providers e não mede produção real. O primeiro insert de um summary ainda depende da
constraint composta para arbitrar corrida rara antes da linha-mutex existir; qualquer
conflito falha/rollbacka em vez de publicar dado silenciosamente incorreto e pode ser
reparado pelo rebuild.

**Etapa 14 permanece exclusivamente para retenção, arquivamento e limpeza controlada
de histórico. Nenhuma retenção foi implementada aqui.**



## Etapa 14 — retenção histórica controlada

**Status:** concluída, validada no PR #19 e publicada na `main`; validação CI registrada ao final desta seção.
O objetivo é limitar o crescimento de histórico repetitivo sem remover identidade lógica,
decisões humanas, rastreabilidade de execução ou produzir interpretações temporais falsas.

### Inventário e classificação semântica

| Entidade | Papel | Fonte de verdade | Reconstruível | Política | Crescimento esperado / dependências |
|---|---|---|---|---|---|
| `Finding` / Opportunity | identidade lógica por fingerprint, snapshot corrente e lifecycle | sim | não integralmente | permanente | uma linha por problema lógico; depende de conta/provider e usuário nas decisões |
| `OpportunityStatusHistory` | auditoria das transições manuais, motivo, nota, ator e data | sim para auditoria | não | permanente | baixo; cresce por decisão humana |
| `OpportunityObservation` | snapshot técnico/evidence de uma oportunidade em uma coleta | histórico detalhado | não após expirar a fonte cloud | **90 dias por default**, configurável | principal crescimento: até uma linha por opportunity/run |
| `CollectionRun` | execução, provider, conta, timestamps, status, contagens, versão e erro | sim operacional | não integralmente | permanente nesta etapa | uma linha por execução; muito menor que observations |
| `DashboardAccountSummary` | estado consolidado corrente da Home | não; derivado | sim | sem retenção histórica; rebuild | uma linha por provider/conta; depende da última SUCCESS e baseline |
| evidence em `Finding` | snapshot técnico corrente | parte do estado lógico corrente | atualizado por nova coleta | permanente junto da Opportunity | não cresce por ocorrência |
| evidence em `OpportunityObservation` | evidência histórica detalhada | histórico | não | acompanha a observation | payload JSON é parte relevante do custo de storage |
| `AwsAccount` / configuração de conta | configuração operacional AWS atual | sim | não | fora do purge | baixo; Stage 10 mantém domínio provider-neutral onde aplicável |
| logs da aplicação | observabilidade operacional | não há tabela persistida dedicada | n/a | fora deste cleanup | stdout/logging; retenção pertence à plataforma de logs |

Não existe `AccountSummaryHistory`; a estrutura criada na Etapa 13 é
`dashboard_account_summaries` e contém somente o estado corrente derivado.

No dataset sintético usado nas Etapas 12/13 havia 10.000 Opportunities, 2.000
CollectionRuns e 98.000 OpportunityObservations. Isso não é medição de produção, mas
confirma a assimetria esperada: observations são a tabela que multiplica por execução e
o alvo apropriado para retenção; Opportunity, lifecycle e CollectionRun não são.

### Dados permanentes e auditabilidade

A política comum de retenção **não apaga**:

- `Finding` / Opportunity, fingerprint, status, first/last seen e snapshot corrente;
- TREATED/REJECTED, motivo, nota, usuário e timestamps persistidos na Opportunity;
- `OpportunityStatusHistory`, incluindo reaberturas;
- `CollectionRun` e suas contagens/resumos;
- `DashboardAccountSummary` corrente, que continua reconstruível.

Não foi implementado purge de Opportunity nem de StatusHistory. As FKs existentes com
`ON DELETE CASCADE` em observations/status-history continuam documentando o
comportamento caso um pai seja removido explicitamente no futuro, mas a rotina de
retenção nunca remove esses pais e nunca depende de cascade.

### Política default e configuração

A configuração continua centralizada em `app.core.config.Settings`:

```text
NUVEMIQ_RETENTION_ENABLED=true
NUVEMIQ_OPPORTUNITY_OBSERVATION_RETENTION_DAYS=90
NUVEMIQ_RETENTION_BATCH_SIZE=5000
NUVEMIQ_RETENTION_MAX_ROWS_PER_RUN=10000
```

`RETENTION_DAYS` e `BATCH_SIZE` precisam ser positivos. `MAX_ROWS_PER_RUN=0`
significa sem limite explícito; valor negativo é inválido. O limite default de 10.000
é deliberadamente conservador para a primeira operação real.

O cutoff é calculado em UTC como `now - retention_days`. Apenas
`observed_at < cutoff` é elegível: a observação exatamente no limite permanece. A
arquitetura de serviço já aceita filtro por provider/conta, mas a política default é
global; não há configuração por conta nesta etapa.

### Proteções antes de qualquer DELETE

Mesmo estando antes do cutoff, observations são protegidas quando pertencem:

1. às **duas CollectionRuns SUCCESS mais recentes** de cada `provider/account_id`;
2. a uma CollectionRun referenciada como target ou baseline pelo
   `DashboardAccountSummary` corrente.

Isso impede que retenção por idade quebre a Home, sua baseline corrente ou a comparação
operacional recente em contas que coletam com baixa frequência. A rotina somente
seleciona IDs elegíveis depois dessas proteções.

Quando qualquer observation de uma CollectionRun é removida,
`collection_runs.detailed_observations_available` passa a `false`. O summary da
coleta (`opportunities_found`, provider, conta, timestamps, status, versão, erro)
permanece disponível.

### Contagem histórica, first seen e last seen

A migration `0013_historical_retention` adiciona
`findings.total_occurrence_count`. O contador é incrementado **somente** quando uma
nova `OpportunityObservation` é efetivamente criada; retry da mesma CollectionRun não
incrementa. O cleanup nunca decrementa esse campo.

Na migration o valor é backfilled com o número de observations conhecidas naquele
momento. O DeepOps não inventa ocorrências anteriores ao modelo histórico da Etapa 2 que
não estejam materializadas no banco; essa é uma limitação de dados legados, não uma
contagem sintetizada.

`first_seen_at` e `last_seen_at` já pertencem a `Finding` e não são derivados da
observation mais antiga/recente retida. Portanto continuam representando os timestamps
históricos persistidos após o cleanup.

### Dry-run, execução manual e batches

O comando operacional é:

```bash
python -m app.commands.retention_cleanup --dry-run
python -m app.commands.retention_cleanup --execute
python -m app.commands.retention_cleanup --execute --batch-size 1000 --max-rows 10000
python -m app.commands.retention_cleanup --dry-run --before 2026-06-30T00:00:00Z
python -m app.commands.retention_cleanup --dry-run --provider aws --account-id 123456789012
```

Sem flag de modo o comando é dry-run. O preview informa cutoff, total de observations no
escopo, quantidade anterior ao cutoff, elegíveis, protegidas, observation mais antiga e
elegível mais antiga. Dry-run não modifica o banco.

Cada batch seleciona IDs em ordem de `observed_at/id`, marca as CollectionRuns afetadas
como histórico parcial, remove somente esses IDs e faz commit. Uma falha faz rollback
apenas do lote corrente; batches anteriores permanecem commitados. Reexecutar é seguro:
registros já removidos não voltam a ser elegíveis, portanto a operação é idempotente.

`MAX_ROWS_PER_RUN` limita o total removido em uma execução. Não há sleep/throttle
artificial nesta etapa; batch size + safety cap dão controle sem introduzir complexidade
não justificada pelo volume atual.

### Execução automática

Não existe Celery beat, scheduler genérico ou infraestrutura equivalente no projeto.
Por isso a Etapa 14 **não adiciona scheduler novo** e retenção não roda após cada coleta.

Para operação recorrente, a CLI pode ser chamada por cron/systemd timer externo,
tipicamente diariamente ou semanalmente. O rollout recomendado é operacional, não
codificado como workflow obrigatório: dry-run, revisão, execução com safety cap pequeno
e aumento posterior se necessário. `NUVEMIQ_RETENTION_ENABLED=false` bloqueia
`--execute` sem remover a capacidade de preview.

### Comparações e APIs após expiração

Ausência causada por retenção nunca é interpretada como `NO_LONGER_DETECTED`.

- `CollectionRun.detailed_observations_available=false` sinaliza explicitamente perda
  de detalhe.
- comparação envolvendo baseline ou target parcial retorna
  `available=false`, `reason=OBSERVATIONS_EXPIRED`, sem summary/diff fabricado;
- filtro de Opportunities por uma CollectionRun expirada retorna HTTP **410 Gone** com
  `COLLECTION_OBSERVATIONS_EXPIRED`, em vez de `200 []`;
- o detalhe da CollectionRun preserva o resumo e diferencia
  `opportunities_found` do número de observations ainda retidas;
- a tela de comparação identifica baselines cujo detalhe expirou.

A Home continua baseada nas últimas coletas válidas e no summary da Etapa 13. O serviço
de agregação também recusa usar observation sets marcados como parciais caso encontre
essa condição defensivamente.

### UI de Opportunity e histórico parcial

A Opportunity expõe `total_occurrence_count`. O endpoint de histórico informa:

- `retained_total`;
- `total_occurrence_count`;
- `history_complete`;
- política configurada e cutoff corrente.

A UI mostra ocorrências históricas separadas de detalhes retidos. Quando o histórico é
parcial, explica que evidências intermediárias expiraram sem sugerir que nunca
existiram. Histórico de decisões permanece separado e permanente.

### Evidência ligada a decisão

O modelo atual não possui FK entre `OpportunityStatusHistory` e uma
`OpportunityObservation` específica. Criar retrospectivamente esse vínculo exigiria
inferir qual observation embasou uma decisão, o que seria auditavelmente pior do que
admitir a ausência do vínculo. A Etapa 14, portanto, preserva permanentemente quem,
quando, transição, motivo e nota, além do snapshot corrente/first/last seen, mas uma
evidência histórica intermediária não explicitamente vinculada pode expirar.

Se a exigência futura for preservar a evidência exata usada na decisão, o domínio deve
registrar explicitamente `decision_observation_id` no momento da decisão e proteger
essa observation; não será inferido retroativamente.

### Migration, índices, FKs e PostgreSQL

Nova revisão: `0013_historical_retention`.

A migration adiciona:

- `findings.total_occurrence_count INTEGER NOT NULL DEFAULT 0`, com backfill;
- `collection_runs.detailed_observations_available BOOLEAN NOT NULL DEFAULT TRUE`,
  marcada como false no backfill quando a contagem detalhada existente diverge de
  `opportunities_found`.

Nenhum índice novo foi necessário. `opportunity_observations.observed_at` já possui
índice desde a migration 0006, e `collection_run_id`/combinação run+opportunity já
estão indexados. Não foram alteradas FKs nem cascades apenas para facilitar cleanup.

No PostgreSQL, DELETE libera tuples para reutilização após VACUUM/autovacuum; não há
`VACUUM FULL` automático porque ele pode bloquear e não deve fazer parte de cada
retenção. Se deletes recorrentes relevantes gerarem bloat, autovacuum e bloat devem ser
monitorados operacionalmente.

### Arquivamento externo e particionamento

Não foi implementado export para S3/Object Storage: não existe requisito concreto nesta
etapa para consultar a evidence detalhada depois do prazo, e criar export, manifest,
checksum, IAM, retry e restore aumentaria o escopo sem necessidade demonstrada.

Também não foi implementado particionamento. Se o volume real tornar DELETE em batches
insuficiente, particionamento temporal de `OpportunityObservation` é a evolução
natural para permitir descarte por partição. Se auditoria futura exigir cold storage,
JSONL compactado ou Parquet com manifest/checksum são preferíveis a CSV gigante; payloads
devem continuar passando pela mesma disciplina de não persistir secrets/tokens.

### Logs e métricas do cleanup

Não foi criada `RetentionRun`: logs operacionais são suficientes no estágio atual.
A execução registra início/fim, cutoff, elegíveis, batch, linhas removidas, total
removido, CollectionRuns marcadas parciais, safety-cap e erro do lote. Esses logs podem
ser coletados pela plataforma já usada para stdout.

### Testes e critérios de regressão

A suíte Stage 14 cobre:

- validação da configuração;
- borda do cutoff e dry-run sem mutação;
- cleanup em múltiplos batches e idempotência;
- preservação de fingerprint, first/last seen, occurrence count, TREATED/REJECTED e
  StatusHistory;
- nova detecção após cleanup reutilizando a mesma Opportunity;
- comparação expirada sem falso `NO_LONGER_DETECTED`;
- HTTP 410 para listagem de CollectionRun sem detalhe;
- proteção das coletas usadas pela Home/summary;
- isolamento por provider, incluindo fixture OCI;
- migration/backfill e compatibilidade de schema através da suíte de migrations;
- build/testes frontend para os estados de histórico parcial.

O teste integrado desta etapa usa banco/test fixtures sintéticos. Não acessa contas cloud
reais, não executa DELETE em produção e não mede storage físico de produção.

**Validação final:** PR #19, CI run #153 aprovado: 258 testes backend em PostgreSQL 17
(47,30 s), `ruff check` e `ruff format --check` aprovados; 34 testes frontend
aprovados e build Next.js concluído; job de segurança aprovado. Auto Deploy Tests
run #146 também aprovado. O teste integrado automatizado usa banco PostgreSQL e
fixtures sintéticos, sem execução de DELETE em produção ou acesso a contas cloud reais.

### Limitações conhecidas

- contagem de ocorrências anterior à materialização introduzida na Etapa 2 não pode ser
  reconstruída se nunca existiu como observation;
- não existe vínculo explícito decisão → observation histórica;
- não há archive externo, particionamento nem scheduler interno;
- o impacto de storage e bloat precisa ser medido no banco de produção antes de qualquer
  ajuste agressivo de janela/batch;
- a política por provider/conta pode ser adicionada futuramente sem alterar o serviço,
  mas não é configurada por escopo nesta etapa.

A Etapa 14 não altera regras FinOps, lifecycle, providers ou features de negócio e **não
avança para a Etapa 15**.


## Etapa 15 — refinamento final de UX e consistência integrada

**Status:** implementação concluída e validada no PR #21. CI run #161 e Auto Deploy Tests run #154 aprovados no head funcional; a publicação na `main` é realizada após a revisão final do diff.

### Auditoria integrada

A revisão foi feita sobre Home, Oportunidades, detalhe, Coletas, comparação, configurações e navegação principal, preservando a arquitetura e as regras de negócio das Etapas 1–14. Foram confirmados diretamente no código: CollectionRun, fingerprint/deduplicação/OpportunityObservation, lifecycle OPEN/TREATED/REJECTED, API paginada, explicabilidade, comparação temporal, Home operacional, abstração multi-cloud, cache frontend, otimizações de backend, summaries persistidos e retenção histórica.

Inconsistências encontradas e tratadas:

- badges recebiam enums em formatos diferentes; valores como `SUCCESS` podiam aparecer crus em componentes que esperavam lowercase;
- a navegação principal ainda expunha a tela legada de `Execuções`, duplicando o fluxo operacional já consolidado em `Coletas`;
- formatadores de conta e número estavam duplicados em componentes;
- a tela de Coletas sempre mostrava “Limpar filtros”, mesmo sem filtro aplicado;
- filtros ativos eram persistidos na URL, mas não havia resumo visual imediato do contexto aplicado;
- erros HTTP desconhecidos podiam expor texto técnico do backend diretamente;
- identificadores técnicos importantes no detalhe não possuíam ação de cópia consistente;
- foco por teclado não possuía um tratamento global suficientemente explícito;
- comparação ainda exibia status técnico cru em opções de baseline.

### Padronização realizada

- `StatusBadge` agora normaliza enums case-insensitive e mantém labels PT-BR consistentes para lifecycle, severidade e estados de coleta;
- `formatAccountLabel` e `formatNumber` foram centralizados junto aos formatadores de provider/moeda;
- Home, Oportunidades, detalhe e comparação continuam usando os formatadores/provider helpers compartilhados sem introduzir dependência estrutural de AWS nas telas genéricas;
- filtros ativos em Oportunidades e Coletas passam a ser apresentados como chips de contexto; “Limpar filtros” aparece somente quando necessário;
- navegação principal deixa de duplicar “Execuções”; a rota legada continua disponível para compatibilidade, sem ser promovida como workspace principal;
- mensagens 403/404/410/422/429/5xx possuem fallback amigável, preservando o detalhe técnico apenas em `ApiError.detail` para diagnóstico;
- detalhe técnico da oportunidade ganhou copy action para ID e fingerprint, mantendo metadata provider-specific na seção técnica;
- foco `:focus-visible` foi padronizado e estados continuam transmitidos por texto/badge, não somente por cor;
- comparação usa labels amigáveis para status e apresentação de conta;
- retenção continua distinguindo histórico expirado de “nunca existiu”; nenhuma semântica de `NO_LONGER_DETECTED` foi alterada.

### Performance, navegação e segurança

As mudanças não introduzem novo fetching, polling, animação pesada ou refetch global. O cache e as query keys da Etapa 11 foram preservados. Filtros continuam URL-driven e deep links permanecem independentes de state em memória. Não foram alterados fingerprint, deduplicação, lifecycle, comparação, retenção ou summaries. Nenhum secret, token, dump, screenshot ou artefato de profiling foi adicionado.

### Código legado e escopo

A entrada `/scans` foi removida apenas da navegação principal por duplicar a experiência consolidada de Coletas; a rota e API continuam preservadas para compatibilidade. “Contas AWS” e políticas AWS continuam explícitas porque o onboarding real disponível hoje ainda é AWS; providers não configurados não foram apresentados como conexões disponíveis.

### Testes e validação

Foram adicionadas asserções frontend para os formatadores compartilhados, preservação de identificadores provider-native, remoção da navegação duplicada e normalização de status. O CI oficial do repositório executa:

- backend PostgreSQL 17: `ruff check`, `ruff format --check` e `pytest -q`;
- frontend Node 22: `npm test` e `npm run build`;
- validações de segurança e CloudFormation;
- Auto Deploy Tests.

Validação do head funcional no PR #21:
- CI run #161 aprovado;
- backend: 258 testes aprovados em PostgreSQL 17, `ruff check` e `ruff format --check` aprovados;
- frontend: 36 testes aprovados; `next build` compilou, verificou tipos/lint e gerou 21 páginas com sucesso;
- segurança: readiness checker, validação estática de exposição via Compose e template CloudFormation aprovados;
- Auto Deploy Tests run #154 aprovado.

O CI não sobe o stack completo `web/api/worker/db/proxy` via Docker Compose e o ambiente desta execução não possui acesso de rede para clonar o repositório localmente. Portanto não foi registrado como executado um smoke test completo de containers nem uma sessão browser E2E real. O PostgreSQL 17 de teste foi iniciado como service container e encerrou limpo. A cobertura integrada disponível permanece nas suítes backend/frontend e nos contratos de rotas, cache, lifecycle, comparação e retenção.

Warnings não bloqueadores observados: uma depreciação Starlette/TestClient no backend; dependências npm reportaram 1 vulnerabilidade moderada e 1 alta durante `npm ci`; GitHub Actions reportou avisos de runtime Node deprecado em actions oficiais. Nenhum desses warnings foi introduzido pelas alterações da Etapa 15 e nenhum foi mascarado.

### Débitos técnicos restantes

- a rota `/scans` e o tipo `Scan` continuam necessários para compatibilidade com o fluxo AWS atual; remoção definitiva exige migração explícita do fluxo de disparo e não pertence a esta etapa;
- onboarding/configuração de contas ainda é AWS-specific; a UI operacional comum já é provider-neutral, mas novos providers precisam de seus próprios conectores/configuração;
- não existe suíte browser E2E real; os fluxos são cobertos por testes de contrato/unitários e validação integrada em CI, mas automação de navegador seria um roadmap separado;
- métricas de Web Vitals/Lighthouse não possuem harness persistente no repositório, portanto nenhum número foi inventado.
- a suíte atual não contém browser E2E nem smoke test do stack Compose completo; isso limita a validação automatizada de foco real, navegação modal e startup conjunto de web/api/worker/proxy.
- o `npm ci` atual reporta 1 vulnerabilidade moderada e 1 alta nas dependências; deve ser tratado como manutenção de dependências separada, com análise de impacto antes de upgrades.
- o backend emite um warning de depreciação Starlette/TestClient; deve ser absorvido em atualização futura da stack de testes.

A Etapa 15 encerra este roadmap sem introduzir novas funcionalidades de negócio.


## Etapa 16 — Contas e Políticas dentro de Configurações

**Status:** implementação concluída, validada no PR #22 e incorporada à `main` no commit `3c8b187`. A implantação do ambiente continua sendo um passo operacional separado do merge.

### Objetivo e alterações

A navegação foi reorganizada para tratar Contas e Políticas como configurações da
plataforma, sem alterar contratos de API, persistência, coletores ou regras FinOps.

- rotas canônicas: `/settings/accounts` e `/settings/policies`;
- `Contas AWS` deixa de ser o nome da área geral e passa a `Contas`;
- referências AWS tecnicamente necessárias permanecem explícitas no formulário:
  AWS Account ID, STS AssumeRole, Role ARN e External ID;
- cadastro continua identificado como `Cadastrar conta AWS`; nenhuma opção OCI é
  apresentada nesta etapa;
- Contas e Políticas saem do menu principal e aparecem na navegação interna de
  Configurações;
- Configurações permanece ativa nas duas páginas e a aba interna considera também
  futuras subrotas por prefixo;
- segurança pessoal, sessões, usuários, auditoria e HTTPS mantêm a disponibilidade
  anterior conforme o perfil.

### Compatibilidade de rotas

O frontend mantém redirects temporários, sem segunda implementação das páginas:

- `/accounts/:path*` → `/settings/accounts/:path*`;
- `/policies/:path*` → `/settings/policies/:path*`.

O mecanismo de redirect do Next.js preserva query string não consumida pelo destino.
As implementações antigas em `app/accounts/page.tsx` e
`app/policies/page.tsx` são removidas. As APIs não foram renomeadas.

### Permissões preservadas

A matriz foi confirmada diretamente nas dependências do backend e mantida na interface:

| Operação | admin | operator | viewer |
| --- | --- | --- | --- |
| Ler Contas | Sim | Sim | Sim |
| Cadastrar/alterar/excluir conta AWS | Sim | Não | Não |
| Gerar External ID e testar conexão | Sim | Não | Não |
| Disparar análise manual | Sim | Sim | Não |
| Ler Políticas | Sim | Sim | Sim |
| Salvar/restaurar Políticas | Sim | Não | Não |

A interface agora oculta/desabilita ações de acordo com essa autorização efetiva; o
backend continua sendo a camada autoritativa. Nenhuma nova permissão foi concedida.

### Fluxos preservados e limites

Continuam usando os mesmos endpoints e contratos: listagem de contas AWS, geração de
External ID, cadastro STS AssumeRole, teste de conexão, disparo de análise,
configuração de agendamento no cadastro e leitura/atualização de políticas.

Não foram implementados OCI, chave privada OCI, `CloudAccount`, migração de banco,
edição nova de contas, coletores OCI, alterações de worker/fingerprint/lifecycle ou
reformulação ampla do sistema de permissões.

### Principais arquivos

- `frontend/components/app-shell.tsx`;
- `frontend/app/settings/layout.tsx`;
- `frontend/app/settings/accounts/page.tsx`;
- `frontend/app/settings/policies/page.tsx`;
- `frontend/lib/settings-navigation.mjs` e tipos;
- `frontend/next.config.mjs`;
- `frontend/tests/settings-navigation.test.mjs`;
- `docs/settings.md` e este roadmap.

### Validação e limitações

Foi executado um teste direcionado local do novo helper/roteamento com 5 casos
aprovados antes da publicação da branch.

Validação oficial do head funcional `6e742a3` no PR #22:

- CI run #164 aprovado;
- frontend: 41 testes aprovados, `next build` compilado com sucesso, lint/type-check
  concluído e 21 páginas estáticas geradas; o build publicou
  `/settings/accounts` e `/settings/policies`;
- backend: 258 testes aprovados em PostgreSQL 17, `ruff check .` e
  `ruff format --check .` aprovados;
- job de segurança aprovado;
- Auto deploy tests run #157 aprovado.

A documentação oficial do Next.js confirma que parâmetros `:path*` aceitam zero ou
mais segmentos, portanto os redirects cobrem tanto `/accounts`/`/policies` quanto
subrotas, e que query strings da requisição são repassadas ao destino do redirect.

A matriz backend permanece coberta por `backend/app/tests/test_security.py` e
`backend/app/tests/test_settings.py`. Não há navegador E2E disponível neste ambiente,
portanto nenhuma validação visual desktop/mobile é declarada como executada. O CI também
mantém os warnings já conhecidos: uma depreciação Starlette/TestClient e o `npm ci`
reporta 1 vulnerabilidade moderada e 1 alta nas dependências; nenhum foi introduzido
pela Etapa 16.

### Pendências para etapas seguintes

- implementar cadastro/autenticação OCI;
- definir a generalização de conta/cloud quando o domínio exigir;
- implementar edição de contas como funcionalidade explícita;
- ampliar coletores/regras para OCI sem reaproveitar indevidamente contratos AWS.


## Etapa 17 — generalização do cadastro de contas

**Status:** implementação concluída e validada no PR #23; incorporada à `main` no merge commit `f93dc5157e506cf33a6c53d4909c130a701600d2`. Deploy de produção é uma etapa operacional separada.

### Modelo comum e fonte de verdade

A administração de contas passa a usar `CloudAccount` como entidade comum, com ID interno estável, `provider`, `native_account_id`, nome, habilitação, estado da conexão, último teste/erro e timestamps. O banco garante unicidade de `provider + native_account_id`.

`provider` e `native_account_id` são imutáveis no contrato de atualização. A validação é específica por provider: AWS exige 12 dígitos; OCI aceita estruturalmente OCID longo e preserva o casing recebido. Esse suporte estrutural não habilita cadastro nem autenticação OCI nesta etapa.

`cloud_accounts` é a fonte de verdade para identidade e atributos comuns. `aws_accounts` permanece como configuração especializada e conserva Role ARN, External ID, regiões, management/payer, agendamento, intervalo e `next_scan_at`. As colunas comuns legadas em `aws_accounts` permanecem somente como espelhos de compatibilidade, sincronizados de `CloudAccount`; os contratos comum e legado delegam ao mesmo serviço transacional.

### Semântica dos IDs e histórico

- `CloudAccount.id`: PK do cadastro administrativo comum.
- `AwsAccount.id`: PK legado da configuração AWS, ainda usado por `scans.account_id` e `policies.account_id`.
- `provider + account_id` em `Finding`, `CollectionRun` e summaries: identidade histórica provider-native.

O frontend usa `CloudAccount.id` para gestão/teste e passa `aws_configuration.id` explicitamente a scans/policies. Não existe resolução por tentativa entre PKs diferentes.

O histórico não recebe FK obrigatória para `CloudAccount`. Findings e CollectionRuns continuam consultáveis sem cadastro administrativo correspondente. O enriquecimento de nome usa LEFT JOIN exato por `provider + native_account_id`; fingerprints, observations e decisões não são recalculados ou recriados.

### Migration `0014_cloud_accounts`

A migration valida as identidades AWS existentes, cria `cloud_accounts`, cria exatamente um registro comum `provider=aws` para cada cadastro AWS, preserva o ID no backfill e adiciona `aws_accounts.cloud_account_id` como FK única. Scans, policies, findings, observations, status history, CollectionRuns e summaries não são regravados.

Inconsistências de identidade fazem a migration abortar. O downgrade é recusado: após a 0014, uma imagem antiga não sabe preencher o vínculo obrigatório ao criar contas. Rollback seguro exige backup pré-0014 + imagens anteriores.

### API e compatibilidade

O contrato canônico passa a ser `GET/POST /api/v1/cloud-accounts`, `GET/PATCH/DELETE /api/v1/cloud-accounts/{cloud_account_id}`, `GET /api/v1/cloud-accounts/aws/external-id` e `POST /api/v1/cloud-accounts/{cloud_account_id}/test-connection`.

O payload comum contém provider, identidade nativa, atributos comuns e configuração provider-specific aninhada. AWS continua exigindo configuração e validação Role ARN ↔ Account ID. Providers reconhecidos sem integração operacional são recusados explicitamente e não geram coletas.

`/api/v1/accounts` permanece como compatibilidade AWS e usa o mesmo serviço/fonte de dados. `/api/v1/scans` e políticas por conta continuam recebendo `AwsAccount.id` nesta etapa. Permissões existentes são preservadas.

### Worker, consultas e rollout

O scheduler seleciona apenas configurações AWS ligadas a `CloudAccount(provider=aws, enabled=true)`. Claim/execução validam o provider, CollectionRun continua recebendo a identidade AWS nativa e STS valida contra essa mesma identidade. Estado de conexão é persistido na conta comum.

Home, Oportunidades e Coletas usam `CloudAccount` apenas para enriquecimento de nome, sem joins obrigatórios que eliminem histórico órfão.

Ordem recomendada: pausar o worker e mutações de cadastro; gerar/validar backup; publicar a API nova para aplicar 0014; validar health e paridade `aws_accounts ↔ cloud_accounts`; publicar worker e web da mesma versão; reabilitar operações. Não misturar writes da API antiga depois da 0014. Falha durante migration é transacional; rollback de versão depois da migration exige restaurar o backup pré-0014.

### Etapa 18 e validação

A Etapa 18 poderá adicionar configuração/autenticação OCI vinculada ao mesmo `CloudAccount`, sem nova generalização do cadastro. Continuam fora desta etapa: API Key/private key OCI, formulário OCI, teste real OCI, collectors/regras OCI e generalização total da fila.

Os testes adicionados cobrem contrato comum/legado, provider e identidade imutáveis, constraint de unicidade, fixture OCI estrutural, permissões, bloqueio de provider sem integração, sincronização dos espelhos, fluxos AWS e migration com scan, CollectionRun, fingerprint, observation e decisão humana preservados. Fixtures OCI não são integração cloud real.


## Etapa 18 — integração OCI por API Signing Key

**Status:** implementação backend concluída na branch `stage18-oci-api-key`. A validação automatizada oficial deve ser conferida no CI do PR. Nenhuma conexão real com uma tenancy OCI é declarada sem credenciais disponibilizadas por mecanismo seguro.

### Modelo, migration e API

A integração reutiliza `CloudAccount` da Etapa 17. `CloudAccount.native_account_id` permanece como única fonte editável do Tenancy OCID e a unicidade `provider + native_account_id` continua no banco. `OciAccountConfiguration` guarda User OCID, fingerprint, região de conexão, regiões/compartments de escopo, flags de root/subcompartments, revisões e credencial criptografada.

A migration `0015_oci_api_keys` cria `oci_account_configurations` e `cloud_account_audit_events` sem reescrever AWS, CollectionRuns, oportunidades, observations ou decisões humanas. Downgrade destrutivo é recusado; rollback após uso de OCI exige backup verificado pré-0015.

Contratos:
- `POST /api/v1/cloud-accounts`: cria conta OCI, configuração e credencial atomicamente;
- `GET /api/v1/cloud-accounts` e `GET /api/v1/cloud-accounts/{id}`: retornam metadados sem PEM, passphrase ou ciphertext;
- `PATCH /api/v1/cloud-accounts/{id}`: atualiza configuração; segredo omitido mantém o atual;
- `{"configuration":{"remove_credentials":true}}`: única remoção explícita; vazio/null não apagam credenciais;
- um novo PEM/fingerprint é validado e testado remotamente antes do swap; falha preserva a credencial anterior;
- `POST /api/v1/cloud-accounts/{id}/test-connection`: testa a configuração OCI;
- `GET /api/v1/cloud-accounts/{id}/audit`: expõe auditoria sanitizada somente para admin.

Provider e identidade nativa continuam imutáveis. Configuração OCI em provider diferente e configuração AWS em OCI são recusadas.

### Escopo explícito

`scope_regions=[]` não significa todas as regiões. `compartment_ocids=[]` com `include_root_compartment=false` significa nenhum compartment configurado, nunca toda a tenancy. A tenancy root só é incluída por `include_root_compartment=true`. `include_subcompartments` exige root ou pelo menos um compartment-base.

Regiões e compartments são configuração pretendida; seu cadastro não representa coleta executada.

### API Signing Key e criptografia

O backend usa o SDK oficial `oci`, instancia `Signer`/`IdentityClient` com `private_key_content` em memória, constrói endpoints pela região e não usa `~/.oci/config` ou credenciais locais como fallback. O PEM é validado como RSA >= 2048 bits, suporta passphrase e o marcador `OCI_API_KEY`; o fingerprint OCI é recalculado da chave pública e comparado antes da persistência.

PEM e passphrase são protegidos com Fernet usando exclusivamente `NUVEMIQ_OCI_CREDENTIALS_KEY`, separada do banco/código e de `NUVEMIQ_SECRET_KEY`. `NUVEMIQ_OCI_CREDENTIALS_KEY_VERSION` acompanha o ciphertext para futura rotação. Chave ausente, inválida ou versão indisponível falha fechado apenas nas operações OCI dependentes dela; AWS permanece operacional.

O worker AWS-only não recebe a chave OCI no Compose. Backup do PostgreSQL sem a chave Fernet correspondente não recupera as credenciais OCI; a chave deve ser protegida e respaldada separadamente.

### Teste de conexão e limites

O teste executa chamadas reais do SDK em runtime:
- `GetTenancy`;
- `GetUser`;
- `ListRegionSubscriptions` usando paginação oficial;
- `GetCompartment` para compartments explícitos;
- `ListCompartments` quando a intenção inclui subcompartments.

O serviço usa timeout curto e zero retry automático para duração previsível. Os resultados distinguem configuração local inválida, autenticação, autorização/recurso oculto, rede/timeout, throttling, indisponibilidade, erro remoto e configuração concorrente obsoleta. Mensagens são sanitizadas e não persistem resposta bruta do SDK.

O teste captura `configuration_revision`, encerra a transação antes das chamadas remotas e só grava o resultado se a revisão ainda for atual. Assim, um teste antigo não marca uma configuração nova como validada.

Sucesso comprova somente `verified_checks`; não comprova acesso a Compute, Database, Object Storage ou futuros coletores. Permissões mínimas desta etapa: `TENANCY_INSPECT`, `USER_INSPECT` e `COMPARTMENT_INSPECT`.

### Auditoria, AWS e interface

Eventos OCI registram autor, conta, ação, horário e resultado sanitizado. Troca/remoção registra a ocorrência sem guardar valores antigos ou novos.

STS AssumeRole, cadastro/edição AWS, scans, scheduler, worker, políticas, fingerprints, lifecycle e histórico permanecem inalterados operacionalmente. Scheduler/fila continuam baseados em `AwsAccount` e provider AWS. Uma conta OCI não possui `AwsAccount.id`, portanto não entra no coletor AWS e um teste OCI não cria `CollectionRun` ou oportunidades.

A tela existente apenas apresenta conta OCI cadastrada pela API e permite teste; análise continua disponível somente para AWS. O formulário unificado/editável completo pertence à Etapa 19.

### Testes e onboarding

A suíte cobre cadastro válido/duplicado, provider incompatível, OCIDs, PEM/fingerprint, passphrase correta/incorreta, criptografia e ausência de segredos, chave Fernet ausente/inválida, update sem reenvio, remoção explícita, troca validada com rollback, invalidação de estado, teste concorrente obsoleto, erros do SDK, RBAC, auditoria, bloqueio de coleta OCI, regressão AWS e migration em base nova/existente.

Onboarding, policies mínimas, rotação e recuperação estão em `docs/oci-onboarding.md`.

Sem credenciais OCI disponibilizadas por canal seguro nesta execução, a validação real em tenancy permanece pendente. Mocks automatizados não são declarados como conexão real.


## Etapa 19 — formulário unificado de cadastro e edição de contas AWS e OCI

**Status:** implementação concluída, validada no CI #192 e incorporada à `main` pelo merge commit `09d3580f1ad583ab529d81abc324730d437f1ead` (PR #25). Deploy permanece etapa operacional separada.

### Experiência final de Contas

`Configurações → Contas` passa a usar uma única experiência para AWS e OCI, mantendo a rota canônica `/settings/accounts` e os redirects estabelecidos na Etapa 16.

A listagem apresenta as duas clouds no mesmo conjunto e oferece filtro por provider e busca sobre nome ou identificador nativo. Como o contrato atual de `GET /api/v1/cloud-accounts` retorna a coleção completa sem paginação, a busca é aplicada sobre todo o resultado carregado e não simula uma busca global sobre apenas uma página. Estados de carregamento, falha de carregamento, cadastro vazio e filtros sem resultado são distintos. Identificadores longos usam truncamento visual, tooltip e ação de cópia.

As ações são isoladas por conta: um teste de conexão não bloqueia as demais contas. Administradores podem adicionar, editar e testar; operadores preservam a análise manual AWS; viewers permanecem somente leitura.

### Cadastro por provider

O botão **Adicionar conta** abre o formulário sem provider pré-selecionado. Somente AWS e OCI são oferecidos, porque são os providers com contrato de cadastro implementado.

Campos comuns:
- nome;
- provider no cadastro;
- identificador nativo no cadastro;
- habilitação.

AWS:
- AWS Account ID;
- Role ARN;
- External ID com geração explícita apenas depois da seleção de AWS;
- regiões;
- conta management/payer;
- agendamento e intervalo.

OCI:
- Tenancy OCID;
- User OCID;
- fingerprint;
- região de conexão;
- regiões de escopo;
- compartments;
- inclusão explícita da tenancy root e de subcompartments;
- chave privada PEM por arquivo ou colagem;
- passphrase opcional.

A região OCI inicia vazia e nunca herda `sa-east-1` ou outra região AWS. Regiões e compartments OCI são entradas manuais validadas, pois a API atual não expõe descoberta para preencher o formulário. Escopo vazio permanece escopo vazio; a interface não o amplia silenciosamente.

Trocar de provider recria o estado provider-specific e remove os campos/segredos incompatíveis. Selecionar OCI não chama o endpoint de External ID AWS.

### Edição e atualização parcial

A edição carrega `GET /api/v1/cloud-accounts/{id}` somente quando necessária. Provider e identificador nativo ficam somente leitura; a interface orienta cadastrar outra conta para trocar AWS Account ID ou OCI Tenancy OCID.

O frontend compara o formulário com a resposta autoritativa carregada e envia por `PATCH` apenas os campos alterados. Valores explícitos como `false` e listas vazias são preservados. Abrir ou salvar uma conta AWS não gera um novo External ID. Habilitar uma conta não habilita seu agendamento.

Foi corrigida uma lacuna do contrato da Etapa 17: alteração efetiva de `role_arn` ou `external_id` AWS agora invalida o teste de conexão anterior, retornando a conta para `untested`. Alterações administrativas, como nome, não invalidam o teste STS. Em OCI, a invalidação por alterações relevantes de autenticação/escopo continua sob o comportamento implementado na Etapa 18.

### Credenciais OCI

As respostas de leitura continuam retornando apenas `credentials_configured` e metadados; PEM, passphrase e ciphertext não são solicitados nem reconstruídos na interface.

Na edição OCI, **Substituir credencial** é uma ação explícita. Sem essa ação, `private_key_pem`, `private_key_password` e `fingerprint` de substituição são omitidos do payload. Cancelar a substituição limpa os novos valores sensíveis e mantém a credencial armazenada.

Quando uma nova chave é enviada, o frontend usa o contrato da Etapa 18: o backend valida a candidata remotamente antes do swap atômico. Falha de validação mantém a credencial anterior. Sucesso retorna a conta já validada. O formulário nunca envia asteriscos como segredo e não usa URL, query string, localStorage, sessionStorage ou rascunho persistente para PEM/passphrase.

O arquivo PEM é lido localmente pelo navegador e limitado a 64 KiB, coerente com o backend. Os valores sensíveis são removidos do estado ao concluir, cancelar, trocar provider ou trocar de conta; não há promessa de eliminação física imediata da memória do processo do navegador.

### Teste de conexão e capacidade de coleta

`POST /api/v1/cloud-accounts/{id}/test-connection` permanece o contrato único para AWS e OCI. A interface exibe progresso por conta, impede envio duplicado da mesma ação, preserva códigos/mensagens sanitizados e só marca sucesso depois da resposta da API. Alterações não salvas bloqueiam o teste da conta em edição, deixando explícito que o teste opera sobre a configuração persistida.

AWS preserva análise manual e agendamento pelo `AwsAccount.id` legado. OCI exibe **“Coleta OCI ainda não implementada”** e não oferece análise nem agendamento; o bloqueio backend da Etapa 18 continua sendo a camada autoritativa. Testar OCI não cria `CollectionRun`, oportunidade ou agendamento.

### Permissões e usabilidade

A matriz de RBAC das Etapas 16–18 foi preservada:
- leitura de contas: perfis autenticados já autorizados;
- cadastro, edição e teste: admin;
- análise manual AWS: admin e operator;
- viewer: leitura.

O formulário usa labels, controles navegáveis por teclado, mensagens em região `aria-live`, validação próxima aos campos e resumo de erro. Cancelamento com alterações pendentes pede confirmação. O layout reaproveita o sistema responsivo existente e recebeu estilos específicos para seleção de provider, credenciais, tabela e mobile.

### Contratos e arquivos principais

Contratos utilizados sem renomeação:
- `GET/POST /api/v1/cloud-accounts`;
- `GET/PATCH /api/v1/cloud-accounts/{id}`;
- `POST /api/v1/cloud-accounts/{id}/test-connection`;
- `GET /api/v1/cloud-accounts/aws/external-id`;
- `POST /api/v1/scans` somente para AWS.

Principais arquivos:
- `frontend/app/settings/accounts/page.tsx`;
- `frontend/lib/account-form.mjs` e `account-form.d.mts`;
- `frontend/lib/api.ts`;
- `frontend/app/globals.css`;
- `frontend/tests/account-form.test.mjs`;
- `backend/app/services/cloud_accounts.py`;
- `backend/app/tests/test_cloud_accounts.py`.

### Testes e limitações

Foram adicionados testes de frontend para isolamento de payload entre providers, limpeza de segredos ao trocar provider, atualização parcial, preservação de `false`/listas vazias, edição OCI sem reenvio de chave, substituição explícita/cancelada, filtros mistos e validações relevantes. O backend ganhou teste para invalidação do estado de conexão AWS após mudança de autenticação sem tornar provider/identidade mutáveis.

Validação automatizada do PR #25, CI #192:
- backend: `ruff check .` aprovado;
- backend: `ruff format --check .` aprovado;
- backend: `pytest -q` com **293 testes aprovados** e 6 warnings de depreciação já existentes;
- frontend: `npm test` com **51 testes aprovados**;
- frontend: `npm run build` aprovado, incluindo compilação TypeScript/Next.js e geração das 21 páginas estáticas;
- security: checks de readiness, exposição pública do Compose e template de Security Group aprovados;
- workflow separado `Auto deploy tests`: testes do instalador de auto-deploy aprovados; esse workflow não representa deploy desta branch.

Não há navegador E2E nem credenciais OCI reais disponíveis nesta execução, portanto nenhuma validação visual desktop/mobile ou conexão real com cloud é declarada.

### Pendências para Etapas 20 e 21

- Etapa 20: redesenho de políticas por provider, sem antecipação nesta etapa.
- Etapa 21: expansão operacional posterior prevista no roadmap; esta etapa não cria collectors, regras ou agendamento OCI.
- Descoberta assistida de regiões/compartments OCI pode ser considerada futuramente se houver contrato backend específico; hoje as entradas são manuais e explícitas.


## Etapa 20 — integração de contas, políticas e capacidades por cloud

**Status:** implementação concluída em `stage20-provider-capabilities`, PR #26, validada no CI #199. O PR permanece aberto; não houve merge nem deploy nesta etapa. Esta etapa não implementa collectors, analisadores ou regras FinOps OCI.

### Fonte de verdade de capacidades

O backend passa a expor `GET /api/v1/cloud-accounts/capabilities` como contrato autoritativo das funcionalidades implementadas por provider. O frontend não decide disponibilidade operacional pela existência de configuração AWS/OCI nem mantém uma segunda matriz de suporte.

Matriz efetivamente implementada:

| Capacidade | AWS | OCI | Azure | GCP |
| --- | --- | --- | --- | --- |
| Cadastro | Sim | Sim | Não | Não |
| Edição | Sim | Sim | Não | Não |
| Teste de conexão | Sim | Sim | Não | Não |
| Coleta manual | Sim | Não | Não | Não |
| Agendamento | Sim | Não | Não | Não |
| Políticas FinOps | Sim | Não | Não | Não |

Os conceitos permanecem independentes: suporte do provider, RBAC do usuário, `CloudAccount.enabled`, estado do teste de conexão e pré-condições da operação. Uma conta conectada não recebe capacidade de coleta automaticamente.

### Disparo de coleta e bloqueios operacionais

Foi adicionado o contrato canônico `POST /api/v1/cloud-accounts/{cloud_account_id}/scans`. Ele recebe o ID administrativo comum, resolve a configuração operacional correta e recusa a operação antes de criar `Scan` quando o provider não possui coleta implementada ou a conta está desabilitada.

`POST /api/v1/scans` permanece disponível como contrato legado AWS e delega ao mesmo serviço de fila/precondições. Assim, o endpoint legado não possui uma regra paralela de elegibilidade.

O scheduler consulta a matriz de capacidades antes de selecionar providers com agendamento. O worker também revalida a capacidade antes de criar `CollectionRun` e novamente antes de executar o coletor e carregar políticas. Trabalho antigo/incompatível já presente na fila é marcado como falha pelo mecanismo existente, sem criar um `CollectionRun` falso, sem cair no coletor AWS e sem permanecer indefinidamente em `RUNNING`.

Falhas de pré-condição administrativa ou provider sem coletor não alteram `connection_status` para erro de autenticação. Falhas reais durante a coleta AWS preservam a classificação anterior.

### Políticas e aplicabilidade

As políticas existentes continuam com a semântica anterior:

- regras globais AWS;
- sobrescritas opcionais por `AwsAccount.id`;
- herança e precedência preservadas;
- valores existentes não são substituídos por defaults;
- endpoints legados `/policies/global` e `/policies/accounts/{aws_account_id}` continuam compatíveis.

O contrato `PolicyRead` agora declara `provider=aws`. A associação por conta continua protegida pelo FK existente para `aws_accounts`, portanto **não foi necessária migration** e nenhuma política legada foi regravada.

Em `Configurações → Políticas`, o frontend consulta a matriz de capacidades. AWS apresenta as regras atuais. OCI apresenta estado explicativo de indisponibilidade e não chama endpoints de regras AWS. Cadastro e teste de conexão OCI não implicam existência de regras ou analisador OCI.

### Identidade, histórico e caches

A resolução visual de contas continua sendo feita por `provider + native_account_id` em Home, Oportunidades e Coletas, com `LEFT JOIN` para preservar dados históricos sem cadastro administrativo correspondente. O nome amigável atual é enriquecimento visual; a identidade histórica, fingerprints, observations e decisões humanas não são reescritas quando o cadastro muda.

Os filtros operacionais continuam derivados das fontes operacionais de cada endpoint. Contas apenas cadastradas não são injetadas em options/agregações como se tivessem sido analisadas. URLs e parâmetros `provider + account_id` permanecem compatíveis.

Após criação/edição administrativa pela interface, os caches de Dashboard, Oportunidades e Coletas são invalidados para que alterações de nome/configuração não permaneçam visivelmente obsoletas.

### Saúde de coleta e ausência de dados

`GET /api/v1/dashboard/collection-health` passa a separar:

- cobertura cadastral;
- contas habilitadas/desabilitadas;
- contas cujo provider possui coletor;
- contas elegíveis para coleta;
- contas elegíveis ainda sem execução;
- providers cadastrados sem coletor implementado;
- saúde das execuções que realmente existem.

`total_scopes`, falhas, `RUNNING`, `SUCCESS`, freshness e warnings continuam baseados em `CollectionRun` real. Conta OCI sem coletor não é classificada como falha ou atrasada e não recebe coleta sintética. A Home também não converte ausência de análise em economia zero.

Na tela de Contas, uma OCI conectada sem coletor é apresentada como **“Conexão validada. Coleta OCI ainda não disponível.”**. Agendamento e análise são renderizados conforme o contrato do backend, e não apenas pela presença de uma configuração provider-specific.

### Contratos preservados e alterados

Preservados:

- `GET/POST /api/v1/cloud-accounts`;
- `GET/PATCH/DELETE /api/v1/cloud-accounts/{id}`;
- `POST /api/v1/cloud-accounts/{id}/test-connection`;
- `GET /api/v1/cloud-accounts/aws/external-id`;
- `/api/v1/accounts` como compatibilidade AWS;
- `POST /api/v1/scans` como compatibilidade de coleta manual AWS;
- endpoints de políticas AWS;
- identidade histórica, lifecycle, comparação, retenção e agregações financeiras por moeda.

Adicionados/estendidos:

- `GET /api/v1/cloud-accounts/capabilities`;
- `POST /api/v1/cloud-accounts/{id}/scans`;
- `PolicyRead.provider`;
- `DashboardCollectionHealth.coverage`.

Nenhuma migration foi necessária nesta etapa.

### Testes adicionados e validação

Foram adicionados testes estruturais para:

- matriz distinta de capacidades AWS/OCI e provider desconhecido;
- recusa de coleta OCI sem criação de `Scan` ou `CollectionRun`;
- recusa de AWS desabilitada sem criação de scan;
- worker recebendo trabalho incompatível sem criar `CollectionRun` e sem marcar a conexão como falha de autenticação;
- cobertura da Home distinguindo conta OCI cadastrada sem coletor de escopos realmente executados;
- frontend consumindo `/cloud-accounts/capabilities` em Contas e Políticas;
- frontend usando o disparo canônico por `CloudAccount.id` e não o ID legado de scan;
- OCI sem políticas FinOps e preservação do contrato AWS.

Fixtures OCI desta etapa são estruturais/simuladas. Elas não constituem evidência de coleta ou acesso real a recursos OCI.

Validação automatizada final do PR #26, CI #199:

- backend: `ruff check .` aprovado;
- backend: `ruff format --check .` aprovado;
- backend: `pytest -q` com **297 testes aprovados** e 6 warnings de depreciação;
- frontend: `npm test` com **51 testes aprovados**;
- frontend: `npm run build` aprovado, incluindo geração das 21 páginas estáticas;
- security: readiness checker, exposição pública do Compose e template de Security Group aprovados;
- workflow separado **Auto deploy tests #192** aprovado; esse workflow testa o instalador e não representa deploy do PR.

As rodadas preliminares CI #195 e #197 identificaram apenas organização/formatação de arquivos Python; os apontamentos foram corrigidos antes do CI #199. O `npm ci` continua reportando 1 vulnerabilidade moderada e 1 alta já presentes na árvore de dependências; a Etapa 20 não declara correção dessas dependências. Não há navegador E2E nem credenciais OCI reais nesta execução, portanto não é declarada validação visual completa nem coleta OCI real.

### Pendências para a Etapa 21

- revisão integrada e smoke tests de implantação;
- validação do rollout real com os serviços `web/api/worker/db/proxy`;
- confirmação operacional pós-deploy dos fluxos AWS existentes;
- validação visual final dos estados AWS/OCI em desktop/mobile, se houver navegador E2E disponível;
- conexão OCI real apenas quando credenciais puderem ser fornecidas por canal seguro, sem confundi-la com existência de collector;
- tratamento de qualquer regressão encontrada na revisão integrada.

Continuam explicitamente fora da Etapa 20: collector/analisador OCI, regras FinOps OCI, novos métodos de autenticação, Azure/GCP operacionais, conversão cambial, mudança de fingerprint/identidade de oportunidade, nova retenção e framework de plugins.


## Etapa 21 — Validação integrada e fechamento da gestão multi-cloud de contas

**Status:** concluída e validada no PR #28; CI, Auto deploy tests e smoke Compose aprovados.

### Objetivo

Consolidar as Etapas 16 a 20 sem ampliar o escopo funcional: validar navegação, identidade comum de contas, cadastro/edição AWS e OCI, proteção de credenciais OCI, matriz de capacidades por provider, migrations e implantação integrada.

### Estado confirmado antes das alterações

- Base de validação: `main` em `18695f3697cd4019517e0eb2a9e71a79dbf0bfbd`, merge do PR #26.
- A área administrativa usa `/settings/accounts` e `/settings/policies`, com redirects dos caminhos antigos.
- AWS permanece o único provider com coleta manual, agendamento e políticas FinOps.
- OCI suporta cadastro, edição e teste de conexão por API Signing Key; isso não representa coleta FinOps OCI.
- A cadeia de migrations termina em `0015_oci_api_keys`.
- O CI da revisão-base e os Auto deploy tests estavam aprovados.
- Não foi identificado defeito funcional que justificasse refatoração ampla antes do fechamento; o gap concreto era ausência de smoke integrado do stack Compose no CI.

### Entregas da Etapa 21

- Adicionado `.github/workflows/stage21-compose-smoke.yml` para validar em projeto Compose isolado:
  - configuração do Compose;
  - build de backend e frontend;
  - PostgreSQL 17, API, worker, web e proxy;
  - migrations no startup;
  - healthcheck via proxy;
  - entrega do frontend;
  - revisão `0015_oci_api_keys`;
  - persistência/prontidão após restart;
  - coleta de logs e teardown do volume isolado.
- Adicionado `docs/stage21-validation.md` com matriz de validação, capacidades por provider, proteção de credenciais, permissões OCI, implantação e recuperação.
- O smoke não usa credenciais cloud reais e não toca recursos ou volumes de produção.

### Validação final automatizada

Head validado antes da consolidação documental: `a0f483007823d0c8dc77c8669976cb05c059635f`.

- CI run `36734050516`: aprovado.
- Auto deploy tests run `36734050432`: aprovado.
- Stage 21 Compose smoke run `36734050381`: aprovado.

Foram executados os seguintes gates:

- backend: `ruff check .`, `ruff format --check .`, `pytest -q`;
- migrations em SQLite e PostgreSQL 17;
- frontend: `npm test` e `npm run build`;
- segurança estática existente;
- smoke Compose da Etapa 21.

Validações AWS/OCI reais, browser E2E e produção permanecem explicitamente separadas. Sem execução em ambiente autorizado, elas não devem ser declaradas como aprovadas por equivalência.

### Documentação operacional

Consulte `docs/stage21-validation.md` para:

- cadastro/edição AWS e OCI;
- chave Fernet de credenciais OCI;
- permissões mínimas do teste OCI atual;
- ordem de implantação;
- backup e recuperação;
- matriz de evidências e pendências.


## Atividade 22.1 — Reorganização da navegação de status em Oportunidades


---

## Atividade 22.2 — Generalização estrutural de Scan para CloudAccount

**Status:** implementada na branch `stage22-2-provider-neutral-scan`; validação final pelo CI do PR.

### Persistência e compatibilidade

`Scan` passa a possuir `cloud_account_id -> cloud_accounts.id` como identidade
administrativa provider-neutral, indexada e obrigatória. O campo legado
`Scan.account_id -> aws_accounts.id` é preservado sem renomeação nem mudança de
significado para manter compatibilidade com o scheduler, worker e contratos AWS
existentes durante a transição.

A migration `0016_provider_neutral_scan_queue` adiciona primeiro o novo campo como
nullable, valida que todo scan histórico resolve `Scan.account_id -> AwsAccount ->
CloudAccount(provider=aws)`, faz o backfill a partir de
`AwsAccount.cloud_account_id`, verifica a invariável entre os dois vínculos e somente
então aplica `NOT NULL`, FK e índice. Associação ausente ou cruzada com outro
provider aborta a migration; IDs, status, triggers, timestamps, contagens, erros,
`CollectionRun.scan_id`, oportunidades, observations, fingerprints e decisões humanas
não são recriados nem reescritos.

Novos scans AWS passam a persistir os dois identificadores em todos os pontos de
criação existentes: fila manual compartilhada pelos endpoints canônico e legado,
scheduler AWS e dados de demonstração. O backend deriva `cloud_account_id` da
configuração resolvida; o cliente não informa os dois IDs e não pode criar uma
combinação arbitrária.

### Limite operacional desta atividade

A execução permanece AWS-only. O scheduler continua usando os campos de agendamento
de `AwsAccount`; claim, execução, políticas, STS e collectors continuam no caminho
AWS existente. A matriz de capabilities não é ampliada: OCI continua com
`manual_collection=false`, `scheduling=false` e sem políticas FinOps. Uma tentativa
canônica de coleta OCI continua sendo recusada antes da criação de `Scan` ou
`CollectionRun`.

`CollectionRun` permanece provider-neutral no histórico, com `provider`,
`account_id` nativo e `scan_id`; nenhuma FK nova é criada para sua identidade de
conta. A deleção de `CloudAccount` preserva a semântica anterior: configurações AWS
e scans associados são removidos em cascata, enquanto `CollectionRun.scan_id`
continua `ON DELETE SET NULL`.

**Persistência preparada para identidade provider-neutral; execução permanece AWS-only.**

A generalização de claim/dispatch/execução/failure handling por provider pertence à
Atividade 22.3. A disponibilização segura de credenciais OCI ao worker pertence à
Atividade 22.4. Agendamento provider-neutral e migração dos campos de schedule ficam
para a atividade posterior prevista para esse domínio; nenhum desses itens é
antecipado aqui.
