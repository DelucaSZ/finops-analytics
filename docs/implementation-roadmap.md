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

**Status:** concluída e validada localmente.

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

