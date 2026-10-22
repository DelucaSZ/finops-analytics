# Dashboard executivo

O Dashboard (`/`) é a visão executiva do estado FinOps atual do DeepOps. Ele responde principalmente onde existe backlog acionável e de onde vem o potencial de economia, sem funcionar como monitor operacional de coletas.

## Responsabilidade do Dashboard

A home apresenta somente o estado corrente do backlog:

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

Os filtros de provider e conta definem um único escopo compartilhado por todos os KPIs, rankings e maiores oportunidades. Deep links de negócio apontam para `/opportunities` preservando o escopo quando aplicável.

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

Histórico fechado, ciclos e snapshots não fazem parte do estado corrente exibido pela home. Esses dados continuam no domínio de histórico/ciclos e não são combinados com o backlog executivo atual.

## Evoluções reservadas

A Task 24.10 mantém um slot de insights operacionais que renderiza `null` quando vazio. A Task 24.11 poderá usá-lo para um insight condicional de falhas de coleta, sem reintroduzir uma health table permanente. A Task 24.12 ficará responsável pelo refinamento do fluxo de navegação de “Novas vs coleta anterior”.
