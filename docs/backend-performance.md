# Etapa 12 — diagnóstico e benchmark de leituras

Base: `db654436627e3956bcf72f7ee3e971a32a3d33f8` (Etapa 11).

## Método e limites

Benchmark HTTP FastAPI/TestClient + serializers reais, SQLite local descartável,
20 contas distribuídas entre AWS/OCI/Azure/GCP, 10.000 oportunidades, 2.000 runs,
98.000 observations; evidência sintética de aproximadamente 2 KB por snapshot.
Mediana de cinco requests sequenciais por endpoint, sem cache do frontend/backend;
cache de páginas do SO/banco não foi limpo. Autenticação foi substituída somente no
harness para isolar consultas; os testes funcionais mantêm cobertura de autorização.
Os dois códigos foram executados separadamente com o mesmo gerador/dataset. Os 11
hashes SHA-256 dos payloads são idênticos antes/depois. Nenhum dado de produção foi usado.

Não são números de PostgreSQL nem SLA de produção. Variações de poucos milissegundos
nos endpoints pequenos não representam melhoria; são exibidas, inclusive aumentos.
`ORM` mede eventos `loaded_as_persistent`, **não** total de linhas examinadas/retornadas
pelo banco. Projeções de comparação ainda leem a interseção, em lotes de 200 linhas.

| Endpoint | Mediana ms antes → depois | Queries antes → depois | Objetos ORM antes → depois | Payload bytes |
|---|---:|---:|---:|---:|
| `/dashboard/summary` | 161.31 → 129.58 | 9 → 8 | 0 → 0 | 3541 |
| `/dashboard/collection-health` | 29.30 → 31.10 | 3 → 3 | 0 → 0 | 3552 |
| `/opportunities?page=1&page_size=50` | 37.25 → 26.38 | 2 → 2 | 51 → 51 | 32330 |
| `/opportunities?current=true&status=open&page_size=50` | 25.23 → 25.11 | 2 → 2 | 51 → 51 | 32249 |
| `/opportunities?provider=aws&account_id=000000000000&status=open&severity=high&page_size=50` | 8.57 → 10.14 | 2 → 2 | 51 → 51 | 32237 |
| `/opportunities/opp-0-000000` | 1.96 → 2.54 | 2 → 2 | 4 → 4 | 2970 |
| `/opportunities/opp-0-000000/history?page_size=50` | 2.63 → 3.38 | 3 → 3 | 21 → 21 | 12162 |
| `/collections?page=1&page_size=50` | 3.36 → 4.80 | 2 → 2 | 50 → 50 | 22537 |
| `/collections/run-0-99` | 1.95 → 2.08 | 2 → 2 | 1 → 1 | 518 |
| `/collections/run-0-99/compare?baseline_id=run-0-98&category=NEW&page_size=50` | 45.90 → 30.05 | 4 → 5 | 1402 → 2 | 35472 |
| `/collections/run-0-99/compare?baseline_id=run-0-98&category=CHANGED&page_size=50` | 47.16 → 22.50 | 4 → 4 | 1402 → 2 | 56705 |

A comparação NEW aumenta um round-trip para aplicar anti-join, ordenação e LIMIT/OFFSET
no banco, mas elimina hidratação e retenção de todos os snapshots. CHANGED/PERSISTENT
precisam percorrer a interseção para classificar evidence semanticamente; conservam
apenas a página de saída, e não listas de todos os IDs/diffs.

## Comparação com mais snapshots por conta

Uma segunda execução isolou 5.000 oportunidades em uma conta, 49.000 observations
históricas, 4.500 observations em cada run comparado e interseção de 4.000.
Mediana de três requests, mesmo método SQLite; 11 payloads novamente idênticos:

| Categoria (página de 50) | Antes ms | Depois ms | Objetos ORM antes → depois |
|---|---:|---:|---:|
| NEW | 708,65 | 181,90 | 14.002 → 2 |
| CHANGED | 672,17 | 139,85 | 14.002 → 2 |

Isso verifica o ganho com milhares de snapshots numa conta; não estabelece SLA nem
limite máximo. Reproduzir com `--accounts 1 --per-account 5000 --repeat 3`.

## Validação integrada

233 testes backend aprovados localmente (12 PostgreSQL sem serviço local), ruff e
formatação aprovados; 34 testes frontend e build Next aprovados. Chromium conectado à
API/Next locais passou por login, Home, filtros, detalhe/histórico, coletas e detalhe,
comparação, tratamento, rejeição, ação em lote e auditoria, sem erros JavaScript.
Worker executou duas coletas por `process_once` com collectors/STS sintéticos;
resultaram 25 oportunidades lógicas e 40 observations, preservando a deduplicação.
Banco local, API, worker e frontend foram iniciados; chamadas AWS reais e deploy EC2
não foram executados. CI do PR #17, run `36467922841`, aprovou **245 testes backend**
em 45,96 s incluindo PostgreSQL 17; frontend/build/segurança também aprovados.
Código validado: `7ee31586975ab425f512de2ce4e6fc028616df8e`. Auto deploy tests
run `36467923015` aprovado.

## Reproduzir

Na pasta `backend`, com `requirements-dev.txt` instalado:

```bash
PYTHONPATH=. python benchmarks/backend_reads.py --repeat 5 --explain
```

O harness cria e remove SQLite temporário. Para PostgreSQL de testes, forneça
`TEST_POSTGRES_URL` e acrescente `--postgres`; cria um schema aleatório exclusivo e
remove **somente esse schema** ao terminar. Nunca usa o `DATABASE_URL` da aplicação.
`--explain` executa apenas SELECTs capturados, fora das medições: `EXPLAIN QUERY PLAN`
no SQLite ou `EXPLAIN (ANALYZE, BUFFERS)` no PostgreSQL. Não roda DML explicativa.

Para comparar a base anterior, execute o mesmo script apontando `PYTHONPATH` para o
`backend` do checkout base. Não comparar seeds, hardwares ou tamanhos diferentes.
Use `--accounts` e `--per-account` para outros volumes. Comparação padrão é de duas
coletas de uma conta, com 450 snapshots por coleta e 400 na interseção. O benchmark
não mede memória RSS nem estima um volume-limite que não foi testado.

## Diagnóstico e decisões

- Home já usava window functions por provider/conta e agregações SQL. Não existia
  carregamento de todas as oportunidades em Python. Severidade foi incorporada à
  agregação de lifecycle/moeda, retirando uma leitura repetida do conjunto atual.
- Listagem já era LIMIT/OFFSET, máximo 200, com filtros/ordenação no banco e dois
  SELECTs. Porém hidratava `Finding.evidence`, notas de decisões e a configuração
  completa de AwsAccount. Agora esses campos ficam fora do SELECT; `raiseload`
  protege contra acesso acidental. Campos públicos de listagem permanecem iguais.
- COUNT e stats não fazem mais LEFT JOIN de conta incondicional; compatibilidade
  com PK legado de AWS usa EXISTS parametrizado somente quando necessário.
- Comparison carregava dois conjuntos completos de Finding/Observation e montava
  dicionários, somas, IDs e diffs em Python. Totais financeiros/counts passam a
  GROUP BY run/moeda, diferenças usam NOT EXISTS, interseção usa JOIN por identidade.
  Apenas a evidência da interseção e da página é lida; Finding.evidence e metadata
  de provider não são duplicados. JSON idêntico evita normalização duplicada; JSON
  diferente segue a comparação semântica original, incluindo evolução natural.
- Detalhe de coleta aproveita o JOIN de Scan para warning/trigger: com scan vinculado,
  reduz 3 → 2 consultas. O dataset da tabela não tem scan vinculado, logo mostra 2 → 2.
- Não havia N+1 de relacionamentos ORM na listagem: modelos não declaram lazy
  relationships. Foi removido o SELECT redundante de Scan, não um N+1 imaginário.
- Não há CloudAccount genérico persistido; AwsAccount enriquece nomes AWS, enquanto
  Finding/CollectionRun guardam provider e identidade nativa independentes.
- Duas experiências foram descartadas por regressão medida em SQLite: consolidar
  os três SELECTs de recent changes (~1.110 ms na Home) e substituir o filtro current
  por semijoin global ranqueado (~51 ms contra ~25 ms). Menos SQL não garante menos tempo.
- Payload e contratos preservados para o cache da Etapa 11; não removidos campos
  públicos para obter números artificialmente melhores. JSON evidence é `JSON`,
  não JSONB, e não é filtrado por conteúdo nestas consultas. Sem GIN/pg_trgm.
- Busca continua ILIKE parametrizado. Sem evidência para alterar extensão, cursor,
  limites de página ou criar índices para cada ordenação.

## Transações, pool e escrita

Worker libera a transação de leitura/configuração antes de STS/identity/collectors e
recupera estado atual de account/scan/run antes de persistir. Teste verifica ausência
de transação ativa nas três chamadas externas. O claim RUNNING já está commitado;
falhas continuam sendo persistidas pela fronteira do worker. Nenhum commit por item
foi acrescentado. Deduplicação conserva UNIQUE fingerprint, UNIQUE observation/run,
SAVEPOINT e FOR UPDATE; bulk lifecycle mantém uma transação e histórico por item.

Não se alterou quantidade de workers, bulk insert, pool ou timeouts. O engine usa
pool_pre_ping e padrões SQLAlchemy QueuePool no PostgreSQL (size 5, overflow 10,
timeout 30 s, recycle -1), por processo; sessões são fechadas por finally/contexto.
Não há statement_timeout configurado pela aplicação. Frontend mantém timeout de
30 s. Sem evidência de saturação para elevar conexões ou esconder consultas lentas
com timeout/cache. A ingestão ainda usa savepoints por item para segurança concorrente.

## Índices e planos

Nenhum índice criado/removido e nenhuma migration nova. A revisão continua
`0011_multicloud_core`. Não foi realizada manutenção em produção. O runner de migrations
faz upgrade em transação com advisory lock; CREATE INDEX CONCURRENTLY não caberia
nesse fluxo sem mudança explícita de mecanismo, portanto não foi usado.

Planos SQLite observados: comparação busca pelo índice collection_run_id, interseção
usa `(collection_run_id, opportunity_id)` e anti-join usa UNIQUE `(opportunity_id,
collection_run_id)`. Histórico usa esse UNIQUE por opportunity_id e ordenação temporária
para observed_at/id. Há sorts temporários na comparação e em páginas de oportunidades.
Nenhum novo índice foi declarado útil apenas por remover esse sort sem medição em PG.
EXPLAIN SQLite não permite concluir seletividade/loops/buffers PostgreSQL.

| Tabela | Índices existentes (além da PK) | Uso/revisão |
|---|---|---|
| Finding | fingerprint UNIQUE; provider; account_id; rule_key; scan_id; status; last_seen_at; treated_at; rejected_at; (provider, account_id, status, last_seen_at); (status, severity) | Identidade, filtros/lifecycle e ordenação. Índices de decisão não usados pelos SELECTs novos; preservados. |
| OpportunityObservation | UNIQUE(opportunity_id, collection_run_id); collection_run_id; observed_at; (collection_run_id, opportunity_id) | Histórico/deduplicação, lookup por run e interseção/anti-join. Índice simples de run pode parecer redundante, mas o plano local o usa; não removido. |
| CollectionRun | UNIQUE(scan_id); provider; started_at; (account_id, started_at); (provider, account_id, started_at); (status, started_at) | Última execução/válida, filtros/período, baseline; UNIQUE protege vínculo com scan. |
| OpportunityStatusHistory | opportunity_id; changed_by; changed_at | Histórico paginado e ator; não hidratado pela listagem. |
| AwsAccount | aws_account_id UNIQUE | Enriquecimento e compatibilidade de conta; nenhuma credencial na projeção da listagem. |

## Pendências objetivas para Etapa 13

- Medir com EXPLAIN ANALYZE/BUFFERS em dataset PostgreSQL representativo antes de decidir
  índice composto de histórico `(opportunity_id, observed_at, id)`, índice parcial SUCCESS
  ou sort misto de `last_seen_at/id`. Não há plano PG de produção nesta entrega.
- Home ainda repete a seleção do estado atual em diferentes agregados (8 queries;
  ~130 ms no dataset local). Avaliar agregação compartilhada/cache somente com medição
  de concorrência/freshness e invalidação por provider/conta/coleta/lifecycle.
- Comparação semântica ainda custa O(interseção) por página e transfere evidence em
  lotes. Para milhares de snapshots por conta, estudar assinatura semântica versionada
  ou resultados pré-calculados. Não alterar CHANGED para simples igualdade JSON.
- Baseline filtra provider/conta/status/data em SQL, mas escopo JSON semanticamente
  compatível é conferido em streaming Python; muitos escopos incompatíveis ainda exigem
  varredura. Home preserva o escopo vigente por provider/conta da Etapa 9.
- Não medidos: benchmark de escrita concorrente, saturação do pool, RSS, latência
  de rede real, dezenas de milhares de snapshots **numa só comparação**. Não afirmar
  limites/sucesso de produção com base nestas medições.

Sem Redis, materialized views, summary tables, snapshots de dashboard, retenção,
particionamento ou exclusão de histórico. Etapa 13 não foi implementada.
