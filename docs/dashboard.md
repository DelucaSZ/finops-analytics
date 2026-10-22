# Dashboard executivo

O Dashboard (`/`) é a visão executiva do estado FinOps atual do DeepOps. Ele responde principalmente onde existe backlog acionável e de onde vem o potencial de economia, sem funcionar como monitor operacional permanente de coletas.

## Responsabilidade do Dashboard

A home apresenta o estado corrente do backlog:

- oportunidades `OPEN` atuais e não arquivadas;
- economia potencial mensal acionável, sempre separada por moeda;
- oportunidades tratadas e rejeitadas com escopo explicitado como estado atual;
- oportunidades novas em relação à coleta comparável anterior, com deep link exato para Opportunities;
- distribuição de oportunidades abertas por severidade e provider;
- ranking de contas, serviços e regras;
- maiores oportunidades atuais por impacto financeiro;
- data de referência discreta (`data_updated_at`).

As agregações executivas usam a mesma base de observações correntes derivada da coleta `SUCCESS` mais recente de cada provider/conta. Findings arquivados são excluídos dessa base. Savings acionável considera apenas oportunidades `OPEN`; `REJECTED`, `TREATED` e arquivadas não entram no total financeiro.

Valores de moedas diferentes nunca são somados. Por exemplo, USD 100 e BRL 200 são retornados e exibidos como dois totais independentes.

Os filtros de provider e conta definem um único escopo compartilhado pelos KPIs, rankings, maiores oportunidades e pelo insight operacional condicional. Deep links de negócio apontam para `/opportunities` preservando o escopo quando aplicável.

## Novas desde a coleta anterior

`Novas desde a coleta anterior` possui uma única definição canônica. Para cada `provider + account_id` no escopo do Dashboard, o backend seleciona a última `CollectionRun SUCCESS` comparável como target e a `SUCCESS` comparável imediatamente anterior como baseline. O conjunto técnico é:

`new_vs_previous = PRESENT(target) - PRESENT(baseline)`

A comparação reutiliza a semântica central de `OpportunityRunComparisonService`/`opportunity_run_comparison` criada para investigação de runs. `FAILED` e `RUNNING` nunca são escolhidas como target final. Uma conta sem baseline não contribui com todas as findings da primeira coleta; ela contribui com zero para esse KPI e é contabilizada separadamente em `accounts_without_baseline`.

Em escopo multi-account o Dashboard resolve um par target/baseline por conta e consolida os conjuntos. Não existe uma `CollectionRun` global. O mesmo vale para filtros de provider ou conta: o `comparison_context` é criado já no escopo solicitado.

Quando existem snapshots de coverage por scope, `new_vs_previous` considera somente coverage autoritativamente comparável. Uma finding de um scope que não foi executado com sucesso na baseline não é promovida a falsa novidade. Runs legadas sem snapshots de scope mantêm a regra de compatibilidade já suportada pelo comparison service.

### First seen e reappeared

O conjunto pode ser decomposto em:

- `first_seen`: oportunidade cuja primeira `CollectionRun` é a target;
- `reappeared`: oportunidade histórica ausente na baseline e novamente presente na target;
- portanto, dentro da comparação classificável, `new_vs_previous = first_seen + reappeared`.

O Dashboard pode exibir esse breakdown sem transformar os dois subconjuntos em KPIs principais.

### Semântica operacional

O KPI executivo não é uma auditoria técnica de todas as observations. Depois de determinar o conjunto de comparação, aplica a semântica operacional do backlog:

- `archived_at IS NULL`;
- `status != rejected`;
- a finding precisa estar observada na target congelada pelo contexto;
- `TREATED` segue a semântica central do backlog e não recebe exceção própria no Dashboard.

Uma oportunidade rejeitada pode ser tecnicamente `reappeared` na investigação da CollectionRun, mas não volta ao KPI operacional. Da mesma forma, uma oportunidade arquivada continua investigável em Collections, porém não volta ao backlog apenas por estar presente no conjunto técnico da comparação.

## Paridade entre KPI e Opportunities

O count do Dashboard e a lista aberta pelo clique são derivados do mesmo membership de comparação. O Dashboard não converte `new_vs_previous` em `first_seen_from=24h` nem reconstrói uma aproximação no frontend.

O summary retorna um `comparison_context` stateless e assinado. O token contém somente o scope e os pares `target_run_id/baseline_run_id` por conta; ele não carrega listas de IDs de oportunidades. O deep link público permanece em `/opportunities` e envia esse contexto, de modo que paginação, stats, filtros adicionais, busca e ordenação sejam executados server-side dentro do mesmo universo base.

O contexto é congelado. Se uma nova coleta `SUCCESS` terminar depois de o Dashboard ter sido carregado, uma nova resposta de summary produz novo count e novo token conjuntamente. Um link antigo continua apontando para os pares antigos enquanto as observations detalhadas existirem. Se a retenção remover os detalhes necessários, a API devolve `410 COMPARISON_CONTEXT_EXPIRED`; ela não transforma expiração em um conjunto vazio ou falso zero.

O token é assinado com HMAC para impedir que IDs arbitrários de CollectionRuns sejam injetados no deep link. O backend também revalida provider, conta, status das runs, ordem temporal e disponibilidade das observations.

## Descoberta temporal recente

`Novas desde a coleta anterior` não significa `identificadas nas últimas 24h`.

O Dashboard oferece um atalho discreto para `Identificadas nas últimas 24h`, que abre `/opportunities` com o preset móvel `first_seen_at >= now - 24h`. Esse preset é dinâmico por definição. Na tela de Opportunities o usuário pode mudar para `Hoje`, `7 dias`, `30 dias` ou `Personalizado`; filtros personalizados preservam `first_seen_from` e `first_seen_to` na URL.

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

Cada item de falha possui deep link direto para `/collections/{collection_run_id}`. Esse link pertence ao insight operacional de coleta e é independente do KPI de novas oportunidades. O KPI `Novas desde a coleta anterior` sempre começa pela lista de `/opportunities`.

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

## Fora do escopo

A Task 24.12 não altera lifecycle, retenção, ciclos históricos, alertas por e-mail/Slack/Teams nem cria novo health detalhado na home. Seu foco é a paridade exata entre o KPI de comparação e o destino em Opportunities, além do acesso à descoberta temporal recente.
