# Lifecycle de oportunidades

Este documento descreve o lifecycle humano das oportunidades e sua relação com a presença técnica observada pelas coletas.

## Identidade

A identidade lógica de uma oportunidade é o `fingerprint` da `Finding`. Novas coletas que encontrem o mesmo fingerprint reutilizam a Finding existente e registram uma nova `OpportunityObservation`; uma nova observação não cria, por si só, uma nova oportunidade.

`first_seen_at` representa a primeira detecção da oportunidade lógica e não é reiniciado por redescobertas. `last_seen_at` e `total_occurrence_count` podem avançar com novas observações.

## Status humano

### OPEN

Achado aguardando decisão humana. Oportunidades `open` não arquivadas compõem o backlog operacional e podem contribuir para economia potencial.

### TREATED

O usuário informou que tratou a oportunidade. Se o mesmo fingerprint reaparecer, o produto pode reativar a presença técnica, desarquivar automaticamente a oportunidade quando aplicável e marcar `needs_review=true`, conforme a regra existente de revisão de tratamento.

### REJECTED

O usuário decidiu deliberadamente não seguir a recomendação. `rejected` é uma decisão humana persistente e a fonte de verdade da supressão; não existe blacklist, tabela paralela nem flag redundante de suppression.

Novas coletas continuam podendo:

- registrar `OpportunityObservation`;
- atualizar `last_seen_at`, `total_occurrence_count` e atributos técnicos da observação;
- atualizar a presença técnica, inclusive para `active`;
- registrar transições em `OpportunityPresenceHistory`.

Novas coletas não podem:

- transformar `rejected` em `open`;
- limpar `rejected_at`, `rejected_by`, `rejection_reason` ou `rejection_note`;
- definir `needs_review=true` apenas porque a oportunidade reapareceu;
- desarquivar automaticamente uma rejeitada;
- criar uma segunda Finding para o mesmo fingerprint;
- classificar a redescoberta como nova oportunidade operacional.

`status=rejected` com `presence_status=active` é um estado válido: o recurso continua sendo detectado tecnicamente, mas a recomendação permanece suprimida pela decisão humana.

## Presença técnica

`presence_status` é independente do status humano. Os estados técnicos `active`, `missing` e `resolved_externally` descrevem somente a presença do recurso nas coletas. Uma transição técnica nunca deve sobrescrever o lifecycle humano.

Exemplo válido:

```text
status=rejected
presence_status=missing
    -> nova observação
status=rejected
presence_status=active
```

A transição acima deve aparecer em `OpportunityPresenceHistory`, sem gerar uma transição `rejected -> rejected` em `OpportunityStatusHistory`.

## Arquivamento

Arquivamento controla a visibilidade operacional e não substitui o status humano.

Uma oportunidade `rejected` pode ser arquivada manualmente ou pela política de retenção. Se for observada novamente, permanece `rejected` e arquivada. A observação pode atualizar a presença técnica para `active`, mas não gera `UNARCHIVE/REAPPEARED` em `OpportunityArchiveHistory`.

O endpoint de unarchive direto rejeita uma oportunidade arquivada com `status=rejected` usando HTTP 409. Para devolvê-la ao backlog, o usuário deve executar `reopen`.

## Reopen

`reopen` é a ação humana explícita que encerra a supressão de uma oportunidade rejeitada e faz `rejected -> open`.

Quando a rejeitada também está arquivada, `reopen` executa a reabertura e o desarquivamento na mesma transação. O lifecycle registra `rejected -> open` e o archive lifecycle registra um `UNARCHIVE` manual associado à reabertura. Não é necessário executar primeiro “Desarquivar” e depois “Reabrir”.

Os campos materializados da última rejeição são preservados para auditoria; o histórico de status continua sendo a fonte cronológica das transições humanas.

## Auditoria

Ações humanas usam a auditoria administrativa existente, incluindo `opportunity.reject`, `opportunity.bulk_reject` e `opportunity.reopen`. Uma coleta que apenas observa novamente uma rejeitada não gera evento administrativo de reopen/unarchive; a evidência técnica permanece em `OpportunityObservation` e nos históricos de presença.

## Dashboard e semântica de “nova”

Uma nova oportunidade operacional é uma Finding que não existia anteriormente para aquele fingerprint e que pertence ao backlog operacional atual. Uma Finding previamente rejeitada não volta a ser “nova” porque deixou de aparecer em um CollectionRun intermediário e reapareceu depois.

A métrica de novas oportunidades exclui `status=rejected` e itens arquivados. Oportunidades rejeitadas também não entram em abertas nem na economia potencial de `open`.

## Compatibilidade

A regra é derivada do `status=rejected` existente e, portanto, protege também registros persistidos antes desta mudança sem exigir migration de dados. Registros que tenham sido auto-desarquivados no passado não são rearquivados retroativamente sem evidência inequívoca; a nova regra vale para as próximas observações e ações.
