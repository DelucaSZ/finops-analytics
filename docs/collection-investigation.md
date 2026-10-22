# Investigação de oportunidades por CollectionRun

A tela de Coletas usa os dados históricos de `OpportunityObservation` para investigar o resultado de uma execução sem confundir histórico técnico com o backlog atual.

## Semântica

- **Observadas**: existe `OpportunityObservation` para a oportunidade na CollectionRun alvo.
- **Identificadas pela primeira vez**: a oportunidade foi observada no alvo e `first_seen_collection_run_id` aponta para essa CollectionRun.
- **Novas vs coleta anterior**: observada no alvo e ausente na baseline comparável. Pode conter `first_seen` e `reappeared`.
- **Reapareceram**: observada no alvo, ausente na baseline e já conhecida antes do alvo.
- **Continuaram presentes**: observada tanto no alvo quanto na baseline.
- **Não detectadas nesta execução**: observada na baseline, ausente no alvo e pertencente a um scope com cobertura `SUCCESS` no alvo.

A classificação é calculada no backend pelo `OpportunityRunComparisonService`. O frontend apenas consome contagens e deep links; não reimplementa set difference.

## Baseline e confiança

A baseline é a CollectionRun comparável anterior da mesma cloud/conta. Quando não existe baseline, métricas relativas não são tratadas como zero operacional: a UI mostra explicitamente que é a primeira coleta comparável.

`RUNNING` e `FAILED` não produzem uma comparação relativa definitiva. Uma CollectionRun `SUCCESS` pode ter cobertura parcial quando algum `CollectionScopeExecution` ficou `FAILED` ou `SKIPPED`; nesses casos `no_longer_detected` considera somente scopes `SUCCESS`.

Mudanças de `analyzer_version` entre target e baseline são exibidas como aviso porque alterações de regra podem explicar parte do delta.

## Retenção

Quando as observations de uma run são removidas pela política de retenção, a investigação detalhada deixa de estar disponível. O total agregado persistido em `CollectionRun.opportunities_found` continua conhecido e não é substituído silenciosamente por zero.

## Navegação

Os helpers em `frontend/lib/collection-query.mjs` constroem todos os deep links. Cada classificação abre `/opportunities/collection/<run_id>` e consulta `GET /collections/{run_id}/opportunities` com o mesmo `discovery_type` usado pelo backend.

A investigação técnica solicita `include_archived=true` e não força `status=open`; portanto uma oportunidade REJECTED ou arquivada continua visível historicamente sem retornar ao backlog e sem alterar seu estado.

## Exemplo com três runs

Considere três coletas sucessivas A, B e C da mesma conta. Uma oportunidade observada em A, ausente em B e novamente observada em C é `reappeared` em C. Uma oportunidade cuja primeira observação ocorreu em C é `first_seen` em C. Uma oportunidade presente em B e C é `continued`. Uma oportunidade presente em B e ausente em C só é `no_longer_detected` quando o scope correspondente em C terminou com cobertura autoritativa.

O modelo atual de `CollectionRun` é single-account (`provider` + `account_id` por run). Por isso não há breakdown multi-account dentro de uma única run; caso o modelo passe a suportar runs agregadas no futuro, a comparação deverá escolher baseline por conta, nunca uma baseline global.
