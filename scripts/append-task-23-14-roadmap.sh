#!/usr/bin/env bash
set -euo pipefail

if grep -Fq '## Etapa 23.14 — Backend de AWS Billing com Cost Explorer' docs/implementation-roadmap.md; then
  echo 'Task 23.14 already documented.'
  exit 0
fi

cat >> docs/implementation-roadmap.md <<'EOF'

## Etapa 23.14 — Backend de AWS Billing com Cost Explorer

**Status:** implementada na branch `feat/23-14-aws-billing-backend` e publicada no PR #68. O merge na `main` depende de solicitação explícita.

### Objetivo e separação de domínios

A 23.14 introduz o backend de Billing AWS usando o AWS Cost Explorer (`GetCostAndUsage`) como fonte de verdade para custos cobrados/estimados. Billing permanece independente de Fluxo: nenhuma resposta de Cost Explorer cria savings, eventos de reutilização ou movimentações no ledger FinOps.

> A configuração operacional desejada atualmente é equivalente a granularidade diária, `AmortizedCost` e exclusão de `Credit`, mas esses parâmetros não são hardcoded como única possibilidade.

> Billing e Fluxo são domínios distintos. Dados do Cost Explorer não criam automaticamente savings ou movimentações no ledger.

> O DeepOps preserva a unidade/moeda retornada pelo Cost Explorer e não realiza conversão cambial nesta etapa.

### Arquitetura AWS encontrada

O cadastro existente usa `CloudAccount` como identidade interna e `AwsAccount` para role, External ID, regiões e `is_management_account`. A autenticação AWS continua passando por `assume_account_session`, que reutiliza STS e o `BOTO_CONFIG` existente com retries adaptativos e limite finito. Não foi criada uma segunda infraestrutura de credenciais.

O modelo atual sabe se uma conta é management, mas não persiste uma relação confiável entre payer/management e member accounts. Também não existe Redis no stack atual e a API roda em processo único no Compose, portanto a primeira estratégia de cache é process-local e não exige infraestrutura distribuída adicional.

A autorização atual do produto é por usuário autenticado sobre o conjunto de contas cadastradas no DeepOps; ainda não existe ACL persistida por usuário/conta. A API de Billing aceita somente IDs internos de `CloudAccount`, resolve AWS Account IDs no servidor e não expõe um seletor arbitrário de `LINKED_ACCOUNT` ao cliente.

### Documentação AWS e decisões

A implementação foi validada contra a documentação atual do `GetCostAndUsage`, `DateInterval`, dimensões/charge types do Cost Explorer, permissões IAM, acesso de management/member accounts e pricing da API.

`TimePeriod.Start` é inclusivo e `End` é exclusivo. O domínio DeepOps expõe somente `DAILY` e `MONTHLY` nesta etapa, embora a API AWS também possua `HOURLY`. As métricas suportadas são `AmortizedCost`, `NetAmortizedCost` e `UnblendedCost`. A exclusão de crédito usa a dimensão `RECORD_TYPE` com o valor exato `Credit`. Os agrupamentos expostos pelo produto são `SERVICE` e `ACCOUNT`, sendo `ACCOUNT` traduzido internamente para `LINKED_ACCOUNT`.

O client do Cost Explorer é criado em `us-east-1`, conforme o endpoint global de billing da AWS. Todas as páginas de `NextPageToken` são consumidas e existe proteção contra repetição de token. `Amount` é convertido diretamente de string para `Decimal`; `Unit` e `Estimated` são preservados.

A API do Cost Explorer tem custo operacional por requisição paginada. A referência atual da AWS informa US$ 0,01 por request paginado, portanto o backend evita chamadas repetidas por meio de cache.

### Management, member, standalone e billing scopes

Como não existe no banco uma associação payer/member confiável, cada role cadastrada é tratada como um billing scope derivado independente nesta primeira versão. Member/standalone accounts são consultadas com a própria role e retornam seu próprio escopo de Cost Explorer, sujeito às preferências de acesso configuradas pela management account.

Para uma conta marcada como management, o DeepOps assume a role cadastrada, mas adiciona filtro `LINKED_ACCOUNT` para o próprio AWS Account ID daquela conta. Isso impede que uma consulta limitada a uma conta DeepOps vaze custos de members visíveis ao payer.

Uma requisição com múltiplas contas consulta cada billing scope registrado separadamente e agrega somente quando todas as consultas terminam com sucesso. Se qualquer scope falhar, a resposta agregada falha explicitamente; não existe total silenciosamente parcial. A otimização de usar uma management account para consultar vários members em uma única chamada fica condicionada a uma futura relação payer/member persistida e confiável.

### API e domínio

Foram adicionadas as operações `POST /api/v1/billing/aws/summary`, `POST /api/v1/billing/aws/timeseries` e `POST /api/v1/billing/aws/breakdown`.

O request recebe `account_ids`, `start_date`, `end_date`, `granularity`, `metric`, `group_by` e `exclude_record_types`. Os defaults técnicos são `DAILY`, `AMORTIZED_COST` e exclusão de `Credit`, sem persistir qualquer perfil de usuário. Os enums de domínio traduzem métricas e grouping para nomes provider-specific somente na camada Cost Explorer.

O service valida período e contas antes da chamada AWS, resolve credenciais existentes, monta a query, consome paginação, normaliza o resultado, agrega múltiplas contas quando seguro, aplica cache e retorna DTOs estáveis. Consultas inteiramente futuras são rejeitadas; `end_date` pode chegar até amanhã somente para representar corretamente o `End` exclusivo do bucket de hoje. Forecast não faz parte desta etapa.

### Normalização financeira

Custos usam `Decimal` sem arredondamento prematuro. A unidade/moeda retornada no campo `Unit` é preservada; não há hardcode de USD nem conversão cambial. Totais de moedas diferentes permanecem separados e nunca são somados silenciosamente.

`Estimated` é propagado para os DTOs e para agregados por OR: se qualquer componente do total estiver estimado, o total é marcado como estimado. Timeseries preenche buckets ausentes com zero somente quando ao menos uma unidade/moeda já foi observada na resposta, evitando inventar uma currency para ausência completa de dados.

Breakdown por `SERVICE` preserva a chave retornada pela AWS. Breakdown por `ACCOUNT` mapeia o AWS Account ID para `deepops_account_id`, `aws_account_id` e `display_name` quando corresponde à conta registrada; IDs desconhecidos nunca são associados a outra conta.

### Cache, retries, paginação e observabilidade

O cache é process-local e thread-safe, coerente com o deployment single-process atual. `AWS_BILLING_CACHE_TTL_CURRENT_SECONDS` tem default de 3600 segundos e `AWS_BILLING_CACHE_TTL_HISTORICAL_SECONDS` default de 86400 segundos; ambos são configuráveis. Períodos fechados anteriores ao mês corrente usam o TTL histórico; demais períodos usam o TTL corrente. Como o DeepOps não muta dados de Cost Explorer, TTL é suficiente e não foi criado mecanismo de invalidation complexo.

A cache key inclui billing scope, ID interno da conta autorizada, intervalo, granularidade, métrica, grouping e record types excluídos. O client reutiliza os retries adaptativos já definidos em `BOTO_CONFIG` (`max_attempts=6`) e não implementa loop de retry próprio.

Erros AWS são normalizados para códigos de domínio como `ACCESS_DENIED`, `COST_EXPLORER_UNAVAILABLE`, `THROTTLED`, `PAGINATION_ERROR`, `INVALID_BILLING_SCOPE`, `INVALID_REQUEST` e `UPSTREAM_ERROR`. Ausência de acesso nunca é convertida em `0` de custo.

Logs estruturados registram billing scope, quantidade de contas, datas, granularidade, métrica, grouping, cache hit/miss, quantidade de requests AWS e duração. Credenciais e valores financeiros por bucket não são registrados.

### IAM, custo e persistência

A nova implementação chama somente `ce:GetCostAndUsage`; essa é a permissão mínima adicionada à documentação operacional da 23.14. O template `NuvemIQReadOnly` existente já concede essa ação, além de permissões mais amplas usadas por outras capacidades do projeto. Não foram alteradas policies externas automaticamente.

Não há migration, tabela de Billing bruto nem data warehouse. O Cost Explorer permanece a fonte de verdade; cache é transitório e não é ledger. A estratégia evita adicionar Redis ou banco de cache enquanto o deployment continuar single-process.

### Testes e validação

Foram adicionados testes focados de query builder, DAILY/MONTHLY, três métricas, exclusão de `Credit`, grouping por service/account, sem grouping, datas, `Decimal`, currency/unit, `Estimated`, missing bucket, paginação completa, proteção contra loop de token, AccessDenied, multi-account, mixed currency, cache hit/miss, management-account scoping, rejeição de conta interna desconhecida, rejeição de período futuro, account display name e falha explícita de agregado parcial.

No PR #68, `ruff check .` e `ruff format --check .` passam; a suíte backend executou 811 testes com sucesso em PostgreSQL 17. O frontend passa `npm test` e `npm run build`, e o job de security permanece verde.

### Limitações deliberadas

A 23.14 não implementa profiles/presets persistentes de Billing — responsabilidade da 23.15 — nem a UI completa de Billing, que pertence à 23.16. Também permanecem fora do escopo Forecast, AWS Budgets, CUR/Athena, OCI Billing, FX, reconciliação com Pricing Catalog, materialização contábil de Billing, geração automática de savings/ledger e redesign global.

Se o deployment da API passar a usar múltiplos workers ou múltiplas réplicas, o cache process-local deixa de ser compartilhado e deve ser reavaliado para uma solução distribuída já disponível na arquitetura futura.
EOF
