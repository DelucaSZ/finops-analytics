# Task 24.12 — Novas desde a coleta anterior

## Definição canônica

`new_vs_previous` representa oportunidades presentes na CollectionRun SUCCESS comparável usada como `target` e ausentes na CollectionRun SUCCESS comparável imediatamente anterior usada como `baseline`, por `(provider, account_id)`.

A comparação global é a união dos conjuntos por conta. Contas sem baseline não contribuem para o KPI. Runs `FAILED` ou `RUNNING` não são usados como target definitivo; o Dashboard usa a última SUCCESS comparável.

## First seen e reappeared

Dentro de `new_vs_previous`:

- `first_seen`: a oportunidade foi identificada pela primeira vez no target;
- `reappeared`: a oportunidade já existia historicamente, não estava presente no baseline e voltou no target.

O KPI operacional exclui oportunidades `REJECTED` e oportunidades arquivadas. O comportamento de `TREATED` segue o lifecycle/query operacional existente; não há regra exclusiva do Dashboard.

## Contexto determinístico

O Dashboard devolve `comparison_context` junto do count. O contexto é stateless, compacto e assinado com HMAC, e contém os pares exatos de target/baseline usados no cálculo. Assim, uma nova coleta concluída depois que o Dashboard foi carregado não altera silenciosamente um link já emitido.

O deep link usa:

`/opportunities?discovery_type=new_vs_previous&comparison_context=...`

com `provider`/`account_id` quando o Dashboard estiver escopado. A URL descreve a consulta; ela não carrega IDs de oportunidades.

Se as observations necessárias ao contexto tiverem expirado pela política de retenção, a API responde com HTTP 410 em vez de retornar um conjunto vazio falso.

## Paginação, stats e filtros

A tela de Opportunities resolve o mesmo `comparison_context` server-side. O conjunto base permanece paginado no backend. Filtros de severity, provider, account, service, rule, status, busca e sort são aplicados sobre esse universo sem trocar target/baseline.

`/opportunities/stats` aceita o mesmo contexto para manter os cards internos coerentes com a lista.

## Descoberta temporal

“Identificadas nas últimas 24h” é independente de `new_vs_previous`. Ela usa `first_seen_at` em janela móvel de 24 horas e pode ser alterada na tela de Opportunities para Hoje, 7 dias, 30 dias ou período personalizado.

## Compatibilidade

O scalar histórico `opportunities.new_since_previous` continua presente no summary durante a migração. Os metadados novos ficam em `opportunities.new_since_previous_details`, incluindo breakdown, cobertura e `comparison_context`.
