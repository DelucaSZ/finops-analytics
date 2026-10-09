## Etapa 23.3 — Histórico auditável do lifecycle técnico das oportunidades

**Status:** implementada no PR #57; validação final condicionada ao CI da branch dedicada antes de qualquer merge na `main`.

### Motivação e separação de domínios

As Etapas 23.1 e 23.2 introduziram o estado corrente de presença (`active`, `missing`, `resolved_externally`) e a reconciliação conservadora por ausência em escopos de coleta comprovadamente `SUCCESS`. A Etapa 23.3 adiciona a trilha persistente necessária para explicar quando, por qual coleta e com qual evidência técnica cada mudança ocorreu.

O lifecycle humano continua exclusivamente em `OpportunityStatusHistory` e representa decisões `open`, `treated` e `rejected`. O histórico técnico novo não altera nem reutiliza a semântica desse modelo. Portanto uma oportunidade pode, por exemplo, estar `treated + active`, `rejected + missing` ou `open + resolved_externally` sem contradição de domínio.

> o histórico técnico registra fatos derivados de observação e reconciliação da cloud; ele não representa decisões humanas nem contabilização de saving.

### Estrutura persistente

Foi criada `OpportunityPresenceHistory`, tratada como trilha imutável de auditoria. Cada evento guarda a oportunidade, `CollectionRun` quando aplicável, `CollectionScopeExecution` quando a decisão depende de coverage por ausência, estados anterior/novo, motivo estruturado, `missing_count`, threshold quando relevante, `occurred_at` e contexto técnico provider-neutral.

`Finding` permanece como snapshot otimizado do estado atual. Os campos `presence_status`, `missing_count`, `missing_since_at`, `resolved_externally_at`, `presence_reconciled_run_id` e `presence_reconciled_at` continuam atendendo listagens e reconciliação sem exigir leitura integral da timeline.

### Eventos e motivos estruturados

Motivos persistidos:

- `NOT_OBSERVED_IN_SUCCESSFUL_SCOPE`: ausência válida em coverage `SUCCESS`;
- `MISSING_THRESHOLD_REACHED`: ausência válida que atingiu o threshold configurado e levou a `resolved_externally`;
- `OBSERVED_AGAIN`: nova `OpportunityObservation` válida após estado `missing` ou `resolved_externally`.

A implementação audita `active -> missing`, `missing -> missing`, `missing -> resolved_externally`, `missing -> active` e `resolved_externally -> active`. A decisão deliberada de registrar também `missing -> missing` preserva a prova de cada coleta válida que contribuiu para o threshold, sem depender de logs transitórios.

### Idempotência, concorrência e transação

A proteção temporal e de retry da Etapa 23.2 permanece autoritativa: o mesmo `CollectionRun` não é reconciliado duas vezes e runs antigos não podem regredir o estado corrente. O histórico só é criado depois dessas guardas.

No banco, `UNIQUE(opportunity_id, collection_run_id, reason)` protege contra duplicação do mesmo fato automático mesmo diante de retry concorrente. Findings continuam bloqueados com `FOR UPDATE` no caminho de reconciliação.

A mudança em `Finding.presence_status` e a inserção de `OpportunityPresenceHistory` compartilham a mesma sessão/transação do worker. Falha antes do commit faz rollback das duas alterações, evitando snapshot técnico sem evento correspondente ou evento sem estado coerente.

### Reaparecimento

Uma observation temporalmente válida reativa a presença e registra `OBSERVED_AGAIN` ligado ao `CollectionRun`. O status humano não é reaberto nem reclassificado. O comportamento preexistente continua válido: oportunidade `treated` que reaparece mantém `treated` e pode receber `needs_review=true`; oportunidade `rejected` permanece `rejected`.

O reaparecimento é provado pela própria `OpportunityObservation`, por isso não exige `CollectionScopeExecution`; já as ausências guardam o scope execution que forneceu a evidência negativa autoritativa.

### API e frontend

Foi adicionado `GET /api/v1/opportunities/{id}/presence-history`, paginado, ordenado por eventos mais recentes e carregado sob demanda. A resposta expõe estados, motivo, timestamp, missing count/threshold, run e referências úteis de scope/collection. Não existem endpoints de edição ou exclusão do histórico.

No drawer já existente de detalhe da oportunidade foi adicionada a seção simples **Presença técnica**, separada de **Histórico de detecção** e **Histórico de decisões**. Não foi criada nova navegação global nem redesign.

### Migration e política de dados legados

A migration `0021_opportunity_presence_audit` cria `opportunity_presence_history` após `0020_opportunity_reconciliation`. Não existe backfill de eventos: findings existentes preservam o estado corrente e o histórico começa a registrar somente fatos observados após a implantação. Nenhuma data, `CollectionRun` ou transição retroativa é fabricada.

O downgrade é bloqueado para não descartar silenciosamente a trilha auditável. As FKs para run e scope usam `SET NULL` para preservar o evento quando a evidência operacional associada for removida; o vínculo com `Finding` segue a política histórica existente do domínio.

### Índices

A tabela possui índices para `collection_run_id`, `collection_scope_execution_id`, `occurred_at`, `(opportunity_id, occurred_at)` e `(to_status, occurred_at)`. O índice composto por oportunidade atende a consulta paginada da timeline sem carregar histórico nas listagens; os demais suportam rastreamento por coleta/coverage e análise de eventos recentes/estado técnico sem criar índices redundantes sobre cada campo textual.

### Logs e observabilidade

Cada evento técnico emite log operacional `opportunity_presence_transition` contendo opportunity, provider, account, from/to status, collection run, missing count e reason. Evidências completas e secrets não são duplicados nos logs.

### Testes

A cobertura adicionada inclui:

- sequência `active -> missing -> missing -> resolved_externally` com contadores, threshold, run e scope;
- reaparecimento a partir de `missing` e `resolved_externally`;
- preservação dos status humanos `treated` e `rejected`;
- retry, `CollectionRun FAILED`, scope `SKIPPED` e run fora de ordem sem evento falso;
- observation presente impedindo ausência;
- atomicidade por rollback;
- constraint de idempotência do banco;
- API paginada e ordenada;
- ausência de histórico fabricado para dados legados;
- comportamento provider-neutral para AWS e OCI;
- migrations em SQLite/PostgreSQL e compatibilidade cumulativa do frontend.

### Limitações deliberadas e próxima etapa

A Etapa 23.3 não implementa `archived`, `archived_at`, política de retenção de oportunidades, ocultação automática de tratadas/rejeitadas, contabilização financeira, Billing/Cost Explorer, pricing AWS/OCI ou redesign global. Arquivamento e retenção pertencem à Etapa 23.4.

`resolved_externally` continua sendo exclusivamente uma conclusão técnica por ausência confirmada. Nenhum saving é gerado por essa transição.
