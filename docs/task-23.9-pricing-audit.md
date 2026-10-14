# Etapa 23.9 — Versionamento e auditoria completa do Pricing Catalog

## Objetivo

A Etapa 23.9 adiciona rastreabilidade financeira completa ao Pricing Catalog persistente introduzido na 23.7 e administrado pela 23.8. A implementação preserva as vigências temporais existentes e acrescenta um audit trail administrativo imutável, além de provenance dos preços utilizados pelos novos cálculos OCI.

> Pricing OCI atualmente utilizado pelo projeto está em BRL.

> Pricing AWS permanece em USD e nenhuma conversão ou soma entre moedas diferentes é realizada nesta etapa.

> Alterações de pricing não recalculam retroativamente oportunidades ou `OpportunityObservation` históricas.

> A partir desta etapa, novos cálculos OCI podem indicar exatamente quais versões do catálogo foram utilizadas.

## Versões e eventos de auditoria

Versão de preço e evento de auditoria são conceitos distintos:

- uma versão em `pricing_catalog_items` representa o preço, moeda, unidade e intervalo de vigência que existiu;
- um registro em `pricing_audit_events` representa a ação administrativa que criou ou alterou o estado do catálogo.

Alterações de preço continuam não destrutivas: a vigência anterior é encerrada e uma nova linha do catálogo é criada. Alterações puramente descritivas podem ocorrer na versão aplicável sem fabricar uma nova versão financeira, mas ainda são auditadas.

## Modelo de auditoria

A migration `0025_pricing_audit` cria `pricing_audit_events` com:

- `pricing_item_id`;
- identidade lógica `provider + service + sku + unit`;
- ação semântica;
- `actor_type`, `actor_id`, `actor_name` e `actor_email` snapshot;
- `reason`;
- `before_data` e `after_data`;
- `occurred_at`.

A tabela é append-only na API normal. Não existem endpoints de update ou delete de eventos de auditoria. A FK para pricing usa `ON DELETE RESTRICT`; a FK opcional para usuário usa `ON DELETE SET NULL`, preservando o snapshot histórico do ator.

As ações suportadas pelo modelo são `CREATED`, `PRICE_CHANGED`, `METADATA_CHANGED`, `DEACTIVATED`, `REACTIVATED`, `FUTURE_VERSION_CREATED`, `VALIDITY_CHANGED` e `IMPORTED`. A superfície administrativa atual produz as ações compatíveis com as operações expostas; reativação destrutiva de versão antiga continua não sendo oferecida.

## Ator e SYSTEM

O ator de operações administrativas vem exclusivamente do usuário autenticado no backend (`require_recent_admin`). Campos extras de ator enviados pelo cliente são rejeitados pelo schema. O evento preserva identificador estável e snapshots mínimos de nome/e-mail para continuar interpretável caso a conta mude ou seja removida.

`actor_type=SYSTEM` e `actor_id=NULL` são representáveis para automações confiáveis sem fingir um usuário humano. A UI apresenta esse ator como `Sistema`.

Os preços seedados pela 23.7 não recebem autoria humana inventada. A migration não fabrica eventos retroativos; essas linhas continuam identificadas por `source=IMPORTED_OCI_CALCULATOR` e a auditoria detalhada começa nas alterações efetuadas após a implantação da 23.9.

## Motivo da alteração

Motivo tem mínimo de 3 e máximo de 500 caracteres. É obrigatório para alterações financeiras de preço/vigência e para desativação. Na criação ele é opcional; em alteração apenas de metadata também pode ser omitido. O backend é a fonte da validação; a UI replica a regra para feedback imediato.

## Before / after e precisão

Os snapshots de auditoria usam uma whitelist de campos do Pricing Catalog: `id`, `provider`, `service`, `sku`, `description`, `unit`, `price`, `currency`, `effective_from`, `effective_until`, `enabled` e `source`.

`Decimal` é serializado como string decimal exata, nunca como `float`. Currency permanece explícita em cada snapshot. Credenciais, tokens, sessões e secrets não participam da serialização.

## Atomicidade, concorrência e cache

A mutation de pricing e a criação do `PricingAuditEvent` usam a mesma `Session` e a mesma transação; o route handler executa um único commit. Falha ao criar o audit event permite rollback da mudança de pricing, e falha na mudança não deixa evento órfão.

A implementação preserva os row locks e advisory transaction locks PostgreSQL da 23.8. O snapshot `before` é obtido após o lock, evitando registrar uma imagem já obsoleta em alterações concorrentes.

Não existe cache global persistente de pricing a invalidar. Cada nova execução constrói resolver/snapshot a partir do catálogo atual, preservando o comportamento da 23.8 sem reintroduzir stale pricing.

## API

O histórico factual de versões continua em:

- `GET /api/v1/pricing/oci/{id}/history`.

O audit trail administrativo é exposto separadamente em:

- `GET /api/v1/pricing/oci/{id}/audit?page=1&page_size=20`.

O audit endpoint é paginado, limitado e ordenado por `occurred_at DESC` com desempate estável por ID. As rotas continuam protegidas pela autorização administrativa da área de Configurações.

## UI

`Configurações → Pricing OCI` diferencia `Vigências` de `Auditoria`. A área de auditoria possui loading, erro, empty state e paginação e exibe:

- data/hora;
- ação traduzida;
- ator;
- motivo;
- diff legível;
- referência da versão.

Preço é mostrado como transição monetária, por exemplo `R$ 10,00 → R$ 12,00`; desativação, vigência e metadata também possuem representação humana. JSON bruto não é a experiência principal.

As operações relevantes pedem `Motivo da alteração` antes do envio. O backend continua validando a mesma regra independentemente do frontend.

## Rastreabilidade de cálculo e snapshots monetários

`ResolvedPrice` já possuía o ID exato da linha do catálogo. A 23.9 passa a preservar essa identidade nos resultados de pricing OCI por meio de componentes estruturados. Cada componente registra:

- `pricing_item_id`;
- `service`;
- `sku`;
- `unit`;
- `unit_price`;
- `currency`;
- `source`;
- `effective_from`;
- `effective_until`;
- `quantity`.

Assim o cálculo mantém simultaneamente referência para rastreabilidade e snapshot monetário suficiente para interpretação/reprodução futura, sem depender do preço atual do catálogo.

## Múltiplos componentes

A implementação não assume `1 cálculo = 1 preço`. Compute Flex persiste componentes independentes de OCPU e RAM; Windows adiciona o componente de licença quando aplicável. Block Volume preserva os componentes de capacidade e VPU. Cada componente mantém sua própria versão, preço unitário e moeda.

## OpportunityObservation e dados históricos

A provenance é incluída na evidence estruturada produzida pelo analyzer e atravessa `normalize_persisted_evidence`. Como `OpportunityObservation` já é o snapshot por `CollectionRun` e já persiste evidence JSON estruturada, não foi criada uma segunda tabela ou coluna redundante exclusivamente para pricing provenance.

Novas observations OCI com cálculo precificado preservam `pricing_components` no snapshot da coleta. Observations antigas que não possuem provenance continuam válidas e permanecem sem referência inventada. Não há backfill arbitrário e nenhuma oportunidade histórica é recalculada quando o catálogo muda.

## OCI / AWS e multi-currency

OCI continua utilizando BRL nos preços fornecidos ao projeto. AWS continua utilizando USD no mecanismo existente. A entidade de auditoria é provider-neutral e não hardcode BRL no schema, mas a API administrativa OCI força BRL server-side.

Não existe FX/conversão cambial nesta etapa. BRL e USD não são somados implicitamente. A mudança não migra o pricing AWS para o novo catálogo nem cria administração AWS.

## Migration e índices

`0025_pricing_audit` depende de `0024_pricing_catalog`, preserva integralmente o catálogo existente e cria apenas a estrutura necessária de audit trail. Não cria eventos retroativos falsos para o seed da calculadora OCI.

Índices suportam as consultas reais:

- `(provider, service, sku, unit, occurred_at)` para timeline da pricing key;
- `(pricing_item_id, occurred_at)` para rastreabilidade por versão;
- `actor_id` e `action` para filtros/auditoria futura.

A listagem normal de pricing não eager-load o audit trail. Eventos são consultados somente sob demanda no detalhe/auditoria, evitando N+1 na listagem.

## Testes e validação

A suíte específica cobre criação, ator autenticado, anti-spoofing, motivo obrigatório, alteração futura, before/after, Decimal exato, currency, metadata, desativação idempotente, paginação, rollback quando audit falha, ausência de evento órfão, Compute multi-componente, Windows, Block Volume, mudança posterior de catálogo, preservação do snapshot antigo, persistence de provenance na evidence e compatibilidade com observations antigas sem referência.

A suíte cumulativa valida também migrations, pricing catalog/admin/resolver, analyzers OCI, AWS, frontend e segurança. O smoke Compose espera a revisão `0025_pricing_audit`.

## Limitações deliberadas

Ficam fora da 23.9:

- conversão cambial/FX;
- administração completa do pricing AWS;
- repricing ou backfill financeiro de histórico;
- botão de recalcular cálculo antigo;
- ledger/Fluxo;
- Billing/Cost Explorer;
- redesign global;
- delete físico de pricing;
- reativação simples de uma versão histórica potencialmente conflitante.
