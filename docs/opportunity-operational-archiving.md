# Arquivamento operacional de oportunidades

## Conceitos

O DeepOps mantém três dimensões independentes sobre uma oportunidade (`Finding`):

- **lifecycle humano**: `open`, `treated` ou `rejected`;
- **presença técnica**: `active`, `missing` ou `resolved_externally`;
- **archive operacional**: presença ou ausência de `archived_at`.

Arquivar significa retirar a oportunidade do backlog operacional atual. Arquivar **não** altera automaticamente o lifecycle humano, a presença técnica, datas de tratamento/rejeição, motivo da rejeição, `first_seen_at` ou `last_seen_at`.

O archive operacional também não é um snapshot histórico. Os snapshots de `OpportunityHistoryCycle` são registros imutáveis capturados ao fechar um ciclo; o archive continua sendo uma mutação do backlog vivo. No fechamento operacional combinado, o snapshot é produzido primeiro e o archive é aplicado depois, dentro da mesma transação lógica.

## Operações disponíveis

### Individual

`POST /opportunities/{id}/archive`

Exige operador. A operação usa row lock, é idempotente, preserva lifecycle/presença, registra `OpportunityArchiveHistory` com motivo `MANUAL`, atualiza os summaries operacionais afetados e emite `AuditEvent`.

### Bulk por IDs

`POST /opportunities/bulk/archive`

Payload:

```json
{
  "opportunity_ids": ["id-1", "id-2"]
}
```

O limite é de 500 IDs por request. IDs duplicados são deduplicados; uma oportunidade já arquivada é contabilizada como `already_archived` sem novo histórico. ID inexistente faz a operação falhar antes da mutação. O lock é adquirido em ordem determinística e toda a operação usa um único timestamp lógico e um único `correlation_id`.

Para volumes maiores, use archive por filtro.

### Preview e archive por filtro

`POST /opportunities/archive-preview`

`POST /opportunities/archive-by-filter`

Os dois usam a mesma semântica de `OpportunityFilters` usada pela listagem operacional: provider, conta, região, serviço, tipo de recurso, status, presença, severidade, regra, CollectionRun, resource ID, busca e escopo `current`.

O backend sempre força o alvo para `archived_at IS NULL`; itens já presentes no Histórico operacional nunca são arquivados novamente. O preview informa quantidade correspondente, itens a alterar, já arquivados, distribuição por status/provider/conta e savings agregados por moeda.

Um filtro vazio é perigoso porque representa todo o backlog. Nesse caso a API exige explicitamente:

```json
{
  "filters": {},
  "archive_all": true
}
```

Sem `archive_all=true`, a resposta é `422` e nada é alterado.

A interface consulta o preview antes da confirmação e informa que o conjunto pode mudar entre preview e execução. A execução sempre retorna a contagem efetivamente alterada.

## Fechamento operacional

`POST /opportunities/period-close`

O fechamento operacional é uma orquestração explícita, não uma consequência do archive comum. Ele exige administrador e combina:

1. validação do ciclo histórico aberto;
2. validação de `CollectionRun` em andamento;
3. geração dos snapshots imutáveis da Task 24.5;
4. fechamento do ciclo;
5. archive do escopo operacional escolhido;
6. refresh dos summaries operacionais;
7. auditoria agregada.

A operação usa a mesma transação de banco. Se snapshot/fechamento falhar, o backlog não é arquivado. Se o archive falhar, o ciclo não permanece fechado parcialmente.

`CollectionRun` com status `RUNNING` bloqueia o fechamento. Coletas `FAILED` já finalizadas não bloqueiam, mas devem aparecer como aviso para o operador.

Archive individual, archive de selecionadas e archive por filtro não fecham ciclo. Apenas a ação explícita **Fechar período** orquestra snapshot + archive.

## Rastreabilidade

Cada Finding realmente arquivada recebe uma linha em `OpportunityArchiveHistory` com:

- `reason = MANUAL`;
- `operation = individual | bulk | filter | period_close` no contexto;
- `correlation_id` em operações bulk;
- `cycle_id` quando o archive faz parte de um fechamento.

Operações grandes geram um único `AuditEvent` agregado (`opportunity.bulk_archive`, `opportunity.archive_by_filter` ou `opportunity.period_close`). IDs são somente amostrados; a resposta e a auditoria não carregam listas enormes.

O mesmo timestamp lógico é usado para todos os itens de uma mesma operação bulk.

## Rediscovery após fechamento

As regras de lifecycle permanecem prevalecentes:

- **OPEN arquivada**: pode voltar ao backlog quando for observada novamente, conforme a regra existente de rediscovery, pois não existe decisão humana de supressão;
- **TREATED arquivada**: mantém a regra existente de rediscovery/`needs_review` e eventual auto-unarchive;
- **REJECTED arquivada**: permanece suprimida. Coleta não pode convertê-la para `open` nem desarquivá-la automaticamente; somente `reopen` explícito devolve a oportunidade ao backlog;
- **fingerprint nova**: cria nova Finding normalmente.

Novas coletas manuais ou agendadas continuam permitidas após um fechamento.

## Exemplo mensal

No fechamento de Outubro/2026, o administrador abre **Fechar período**, revisa o ciclo e o preview do backlog, confirma o escopo e executa a operação. O sistema captura snapshots de todas as oportunidades observadas no ciclo antes de aplicar o archive operacional. O backlog fica preparado para novas coletas de Novembro, enquanto o snapshot de Outubro permanece imutável e as linhas arquivadas continuam acessíveis no Histórico operacional.

## Volume e consistência

O archive por filtro resolve o conjunto no servidor e processa Findings em batches de 500 com locks determinísticos. Objetos completos são carregados apenas por batch; refresh de dashboard é agrupado por provider/conta, evitando refresh por item.

A implementação permanece síncrona porque o volume operacional esperado é de poucos milhares de Findings. Não foi introduzida infraestrutura de job assíncrono nesta task. Se o volume real evoluir para dezenas/centenas de milhares de registros por fechamento, a operação deve migrar para um job persistente com estado explícito, preservando a mesma semântica transacional/compensatória.

## Fora do escopo da 24.6

Continuam para 24.7+ políticas configuráveis de retenção/arquivamento por status, scheduler configurável, filtros temporais adicionais, atalhos de últimas horas, redesign de Dashboard e insights de falhas.