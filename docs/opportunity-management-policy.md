# Política de retenção e histórico de oportunidades

A Task 24.7 move as decisões operacionais de retenção de oportunidades para uma política
global persistida no banco. Variáveis de ambiente legadas continuam aceitas somente no
bootstrap da primeira linha; depois disso a configuração salva pela aplicação é a fonte
de verdade e não é sobrescrita no restart.

## Conceitos separados

A política diferencia três mecanismos:

1. **Arquivamento operacional**: remove uma Finding do backlog sem alterar o status humano.
2. **Ciclo histórico**: define a janela temporal usada para snapshots imutáveis.
3. **Retenção física**: remove `OpportunityObservation` antigas depois que os snapshots
   necessários já podem existir.

Fechar um ciclo automaticamente não arquiva todo o backlog. A ação operacional manual
de fechamento continua independente.

## Defaults de novas instalações

- ciclo: `CALENDAR_MONTH`;
- timezone: `UTC` para preservar o comportamento anterior;
- fechamento automático: desabilitado;
- tratadas: arquivar após 30 dias;
- rejeitadas: arquivar após 30 dias;
- resolvidas externamente: arquivar após 30 dias;
- abertas: arquivamento automático desabilitado;
- observações detalhadas: 400 dias;
- policy version inicial: 1.

Se os envs legados de retenção estiverem explicitamente definidos no primeiro bootstrap,
seus valores são usados para os campos equivalentes. Ausência do env usa os defaults
acima. Os envs não voltam a sobrescrever a policy persistida.

## Regras de arquivamento

A avaliação é determinística: `REJECTED`, `TREATED`, `RESOLVED_EXTERNALLY` e `OPEN`.
Cada Finding só pode ser arquivada uma vez na execução.

- `TREATED` usa `treated_at` e preserva o guard de reobservação/`needs_review`.
- `REJECTED` usa `rejected_at`; novas detecções não reiniciam o relógio nem removem a
  supressão persistente da Task 24.4.
- `RESOLVED_EXTERNALLY` usa `resolved_externally_at`.
- `OPEN`, quando habilitado, usa inatividade baseada em `last_seen_at`. Uma nova
  observação reinicia essa janela.
- arquivamento nunca converte status humano.

O histórico de archive registra `policy_key`, `policy_version`, `threshold_days` e
`reference_timestamp`. A auditoria automática é agregada por execução para evitar um
evento de auditoria por Finding.

## Ciclos

### CALENDAR_MONTH

As fronteiras são calculadas no timezone IANA configurado e depois persistidas em UTC.
Não é usado `timedelta(days=30)` para representar um mês.

### FIXED_DAYS

Usa `cycle_anchor_date` explícita e duração entre 7 e 365 dias. Ciclos seguintes começam
exatamente no `period_end` do anterior, sem gaps ou overlaps.

Alterar timezone, modo, duração ou âncora não modifica ciclos já criados. A nova policy
vale para o próximo ciclo. Cada ciclo guarda `policy_version` e metadata da policy usada
na criação; esse contexto é preservado quando o ciclo é fechado.

## Fechamento automático

Quando habilitado, o worker verifica periodicamente ciclos `OPEN` cujo `period_end` já
foi atingido.

- `CollectionRun` em `RUNNING` adia o fechamento e gera log `cycle_close_deferred`;
- runs `FAILED` finalizadas não bloqueiam o fechamento e permanecem refletidas na
  coverage do snapshot;
- o snapshot e o fechamento continuam usando o serviço imutável introduzido na Task
  24.5;
- o próximo ciclo é criado de forma determinística;
- a automação é idempotente e usa locks já existentes no fechamento e checkpoint
  persistente de cadence.

## Retenção de observações

O cutoff passa a usar `observation_retention_days` da policy persistida. A configuração
não permite retenção menor que o ciclo: 31 dias para `CALENDAR_MONTH` ou pelo menos a
duração configurada para `FIXED_DAYS`.

O cleanup preserva os snapshots históricos e mantém `CollectionRun.detailed_observations_available`
consistente, reaproveitando o serviço existente.

## API

- `GET /api/v1/settings/opportunity-policy`
- `PUT /api/v1/settings/opportunity-policy`
- `POST /api/v1/settings/opportunity-policy/preview`

Alterações são admin-only e usam `expected_version`. Versão divergente retorna `409`
sem sobrescrever a alteração do outro administrador. Preview é somente leitura e não
arquiva, remove observações nem fecha ciclos.

## UI

A seção **Configurações > Retenção e histórico** permite editar ciclo, timezone,
fechamento automático, regras de archive e retenção de observações. A tela mostra o
ciclo atual, a versão da policy, últimas execuções, warnings de redução e preview do
impacto antes do save.

Salvar apenas persiste a policy. Purge/archive/close são aplicados pelo worker nas
execuções seguintes.
