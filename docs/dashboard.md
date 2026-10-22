# Dashboard executivo

O Dashboard (`/`) é a visão executiva do estado FinOps atual do DeepOps. Ele responde principalmente onde existe backlog acionável e de onde vem o potencial de economia, sem funcionar como monitor operacional permanente de coletas.

## Responsabilidade do Dashboard

A home apresenta o estado corrente do backlog:

- oportunidades `OPEN` atuais e não arquivadas;
- economia potencial mensal acionável, sempre separada por moeda;
- oportunidades tratadas e rejeitadas com escopo explicitado como estado atual;
- novas oportunidades versus a coleta anterior, enquanto o fluxo definitivo de navegação é tratado pela Task 24.12;
- distribuição de oportunidades abertas por severidade e provider;
- ranking de contas, serviços e regras;
- maiores oportunidades atuais por impacto financeiro;
- data de referência discreta (`data_updated_at`).

As agregações executivas usam a mesma base de observações correntes derivada da coleta `SUCCESS` mais recente de cada provider/conta. Findings arquivados são excluídos dessa base. Savings acionável considera apenas oportunidades `OPEN`; `REJECTED`, `TREATED` e arquivadas não entram no total financeiro.

Valores de moedas diferentes nunca são somados. Por exemplo, USD 100 e BRL 200 são retornados e exibidos como dois totais independentes.

Os filtros de provider e conta definem um único escopo compartilhado pelos KPIs, rankings, maiores oportunidades e pelo insight operacional condicional. Deep links de negócio apontam para `/opportunities` preservando o escopo quando aplicável.

## Insight operacional condicional

A Task 24.11 usa o slot de insights deixado pela 24.10 exclusivamente para falhas vigentes de coleta. O componente não ocupa espaço quando o escopo está saudável e não reintroduz health table, freshness, KPI permanente de falhas ou histórico operacional na home.

A regra canônica é calculada no backend por `provider + account_id`:

- a execução terminal mais recente (`SUCCESS` ou `FAILED`) é determinada por `started_at DESC, id DESC`;
- o insight aparece somente quando essa execução terminal mais recente é `FAILED`;
- uma `SUCCESS` posterior resolve o alerta automaticamente;
- uma `RUNNING` posterior não resolve a falha enquanto não terminar com sucesso; nesse caso o insight informa que existe nova coleta em andamento;
- falhas históricas anteriores a uma `SUCCESS` não reaparecem;
- contas desabilitadas ou removidas do escopo operacional não mantêm alerta na home;
- AWS e OCI são agrupadas separadamente pela identidade estável do provider/conta.

O endpoint `GET /dashboard/operational-insights` lê somente `CollectionRun` persistida e o cadastro de conta; abrir o Dashboard não consulta AWS/OCI nem dispara coleta. Ele aceita os mesmos filtros `provider` e `account_id` da home, limita os itens retornados e informa `count` total/`truncated` quando necessário.

Erros exibidos usam o sanitizador allowlist de Collections. Tracebacks, headers, tokens, passwords, access keys e material privado não são ecoados no Dashboard. O detalhe completo permitido continua na investigação da CollectionRun.

O frontend usa cache separado e revalidação leve do insight. O summary executivo não é colocado em polling mais frequente. Se o endpoint do insight falhar, o restante do Dashboard continua funcionando e nenhuma falha de coleta falsa é exibida.

Cada item possui deep link direto para `/collections/{collection_run_id}`. Para múltiplas contas, o bloco permanece compacto e expansível, com link geral para Collections filtrado por `FAILED`.

## Responsabilidade de Collections

A área `/collections` permanece responsável pela investigação operacional de CollectionRuns, incluindo:

- status de execução;
- erros e warnings;
- coverage e baseline;
- detalhes por scope;
- comparação entre runs;
- oportunidades observadas em uma coleta específica;
- freshness e contexto operacional de execução.

O endpoint `/dashboard/collection-health` continua disponível para consumidores operacionais existentes, mas a home não o consulta nem depende dele para renderizar o Dashboard.

## Histórico

Histórico fechado, ciclos e snapshots não fazem parte do estado corrente exibido pela home. Esses dados continuam no domínio de histórico/ciclos e não são combinados com o backlog executivo atual. Falhas históricas de coleta continuam disponíveis em Collections mesmo quando já foram resolvidas por uma execução `SUCCESS` posterior.

## Evoluções reservadas

A Task 24.12 permanece responsável pelo refinamento do fluxo de navegação de “Novas vs coleta anterior”. Alertas por e-mail/Slack/Teams, retry, stale collection, credenciais expirando, acknowledgement, snooze e lifecycle de incidentes não fazem parte do insight da 24.11.
