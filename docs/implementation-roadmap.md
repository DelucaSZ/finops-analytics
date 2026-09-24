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
