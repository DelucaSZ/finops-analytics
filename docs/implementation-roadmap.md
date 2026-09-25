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

**Status:** implementada na `main`; validação de CI pendente no momento deste registro.

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

**Status:** implementada na branch de trabalho; validação final de CI registrada na entrega da etapa.

### Contrato de evidência

A explicabilidade passa a ser produzida pelo backend no momento da coleta e persistida
em cada `OpportunityObservation.evidence`. Não foi criada nova tabela nem migration:
o JSON já versionado temporalmente pela Etapa 2 é a fonte correta para representar
como o problema estava em cada `CollectionRun`.

O contrato `schema_version = 1` possui:

- `summary`: conclusão humana curta e determinística;
- `metrics`: valores estruturados com `key`, `label`, valor, unidade, moeda e natureza
  observada/estimada;
- `details`: evidência técnica curada, sem payloads completos da cloud;
- `rule`: identificador técnico, nome amigável, descrição e critérios efetivamente
  aplicados;
- `decision_parameters`: somente parâmetros necessários para reproduzir/explicar a
  decisão daquela coleta;
- `source`: provider, sistema de origem e instante de avaliação;
- `limitations`: limitações factuais da evidência, quando existirem.

A configuração global atual não é consultada para explicar observações históricas.
Thresholds relevantes são fotografados na própria observation. O modelo continua
flexível por analyzer sem exigir tabela específica para cada regra.

### Analyzers adaptados

Todos os analyzers implementados nesta versão foram convertidos para o contrato:

- `ebs_unattached`;
- `eip_unassociated`;
- `snapshot_retention`;
- `ec2_stopped_with_ebs`;
- `ec2_nonprod_outside_hours`;
- `load_balancer_no_traffic`;
- `rds_nonprod_idle`;
- `missing_required_tags`;
- `cost_growth_anomaly`.

A implementação não fabrica dados ausentes. Exemplos deliberados:

- EBS sem anexação registra idade desde a criação, mas não afirma há quanto tempo foi
  desanexado;
- Elastic IP sem associação não inventa duração da desassociação;
- EC2 com horário de parada desconhecido mantém duração nula;
- Load Balancer com zero datapoints não trata ausência de amostras como prova de
  tráfego zero;
- RDS ocioso documenta que a regra atual usa CPU e conexões; I/O ainda não é coletado;
- EC2 fora do expediente comprova o estado no instante da coleta, não uma quantidade
  histórica de ocorrências;
- custo de snapshots é marcado como estimativa/limite superior por causa da natureza
  incremental dos snapshots EBS;
- crescimento de custo separa aumento observado de economia potencial, que não é
  inferida por essa regra.

### Dados sensíveis e tamanho do JSON

O contrato não persiste respostas completas da AWS. Tags arbitrárias deixam de ser
copiadas para a nova evidência estruturada. Quando tags participam da decisão, somente
as chaves relevantes à regra são preservadas, como tags obrigatórias ou de ambiente.
Não são incluídos user data, tokens, passwords, connection strings ou credenciais.

### API e performance

A listagem `GET /api/v1/opportunities` deixa de retornar o JSON completo de
`evidence`, reduzindo o payload da workspace. O detalhe
`GET /api/v1/opportunities/{id}` passa a retornar `latest_observation`, já resolvida
no backend, incluindo sua evidência e contexto do `CollectionRun`. O frontend não
precisa carregar todo o histórico, ordenar localmente e descobrir a última coleta.

O histórico `GET /api/v1/opportunities/{id}/history` permanece paginado e retorna a
evidência própria de cada observation. A listagem continua em uma contagem + uma query
paginada; a consulta adicional da última observation só existe no endpoint de detalhe.
Não foi introduzido N+1 na listagem.

Schemas explícitos foram adicionados para métrica, critério, regra, origem e evidência.
Observações legadas continuam aceitas como JSON não estruturado para migração
incremental.

### Frontend

A seção **“Por que o DeepOps chegou nessa conclusão?”** passa a priorizar o contrato
estruturado do backend. Ela apresenta, nessa ordem:

1. conclusão;
2. regra amigável;
3. principais métricas;
4. critério/threshold aplicado naquela coleta;
5. contribuidores de custo, quando existirem;
6. limitações;
7. evidência técnica em seção avançada.

O identificador interno da regra permanece disponível somente nas informações
técnicas. JSON cru não é exibido por padrão.

O histórico de detecção tornou-se selecionável: escolher uma observation troca a
evidência mostrada no detalhe para os dados daquela coleta específica. Histórico
técnico e histórico de decisões humanas permanecem separados.

Observações anteriores ao contrato estruturado continuam renderizadas por um fallback
legado. Evidência ausente mostra mensagem explícita e não é substituída por dados
inventados.

### Moedas e unidades

Métricas financeiras preservam moeda separadamente do valor numérico e da unidade
temporal. A implementação atual registra USD onde a origem/configuração atual é em
USD, sem exigir que componentes assumam permanentemente uma moeda única. Unidades de
capacidade provenientes do EC2/EBS são preservadas como GiB; percentuais, dias,
requests, conexões e demais unidades permanecem explícitos.

### Arquivos principais

- `backend/app/services/opportunity_explainability.py`;
- `backend/app/services/collectors.py`;
- `backend/app/services/policies.py`;
- `backend/app/services/opportunity_query.py`;
- `backend/app/schemas/opportunity.py`;
- `backend/app/tests/test_opportunity_explainability.py`;
- `backend/app/tests/test_cost_evidence.py`;
- `backend/app/tests/test_opportunities_api.py`;
- `frontend/components/finding-evidence.tsx`;
- `frontend/components/opportunity-detail.tsx`;
- `frontend/lib/opportunity-evidence.mjs`;
- `frontend/lib/opportunity-evidence.d.mts`;
- `frontend/lib/types.ts`;
- `frontend/tests/opportunity-evidence.test.mjs`;
- `frontend/app/opportunities-stage5.css`.

### Testes e pendências conhecidas

A suite adicionada valida o contrato estruturado dos nove analyzers, ausência de
inferência para horário de parada desconhecido e CloudWatch sem datapoints, períodos e
contribuidores de crescimento de custo, snapshot dos thresholds, detalhe com
`latest_observation`, listagem sem evidência pesada e seleção de evidence histórica no
frontend.

A persistência temporal continua coberta pelos testes da Etapa 2, que verificam duas
coletas para a mesma oportunidade com duas `OpportunityObservation` independentes e
sem sobrescrita do histórico.

Limitações de dados permanecem explícitas: RDS ainda não coleta I/O; Elastic IP não
possui histórico de desassociação; a regra de EC2 fora do expediente ainda não possui
contador histórico de ocorrências. Esses itens não impedem explicabilidade correta dos
dados realmente avaliados e não foram preenchidos por inferência.

Não foram implementados nesta etapa tela completa de CollectionRun, comparação
avançada entre coletas, nova Home, dashboard multi-cloud, materialização/cache global,
retenção histórica ou geração por IA. A Etapa 7 não foi iniciada.
