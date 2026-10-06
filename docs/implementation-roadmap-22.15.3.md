# Atividade 22.15 — Interface provider-neutral de scheduling AWS/OCI

**Status:** implementação concluída na branch `stage22-15-oci-scheduling-ui`; validação final realizada na Task 22.15.4 e PR aberto contra `main`, sem merge.

> Registro consolidado da Atividade 22.15. O roadmap cumulativo principal permanece como histórico das etapas anteriores; este addendum documenta as Tasks 22.15.1 a 22.15.4 e serve como registro da entrega enquanto a branch aguarda revisão.

## Arquitetura e fonte de verdade

- `CloudAccount` é a única fonte autoritativa para `schedule_enabled`, `scan_interval_hours` e `next_scan_at`.
- Create/update usam os campos de scheduling no contrato comum de `CloudAccount`.
- `next_scan_at` permanece backend-controlled e read-only; não é aceito em payload de escrita e não é calculado pelo frontend.
- A disponibilidade de scheduling é determinada por `ProviderCapabilities.scheduling`.
- AWS mantém seus campos legados de scheduling somente como mirrors de compatibilidade; eles não são fonte independente de verdade.
- `OciAccountConfiguration` contém somente configuração específica OCI e não recebeu `schedule_enabled`, `scan_interval_hours` ou `next_scan_at`.
- A Atividade 22.15 não cria migration, endpoint específico de scheduling, scheduler paralelo, fila paralela ou worker específico de OCI.

## Tasks 22.15.1 a 22.15.3

### 22.15.1 — contrato backend provider-neutral

- Scheduling passou a ser gravável pelo contrato comum de `CloudAccount` para providers com capability `scheduling=true`.
- O backend continua responsável pelo cálculo e pela limpeza de `next_scan_at` ao habilitar, alterar intervalo ou desabilitar a recorrência.
- Update OCI somente de scheduling não toca configuração específica, credenciais, scope, revisions ou estado de conexão.
- O adapter legado AWS continua sincronizado com os valores autoritativos de `CloudAccount`.

### 22.15.2 — estado e payload frontend provider-neutral

- `AccountFormState` representa `schedule_enabled` e `scan_interval_hours` no nível comum.
- `accountToForm()` lê os valores de `CloudAccount`.
- Builders de create/update enviam scheduling no nível comum para AWS e OCI.
- `next_scan_at` não participa de payload de escrita.
- PATCH OCI somente de scheduling não serializa `configuration`, não reenvia private key/passphrase/fingerprint e não altera scope inalterado.

### 22.15.3 — interface compartilhada

- AWS e OCI usam o mesmo componente visual de scheduling em **Configurações > Contas**.
- O toggle **Ativar coleta automática** altera somente `CloudAccount.schedule_enabled`.
- O select compartilhado oferece somente 12h, 24h e 168h: `A cada 12 horas`, `Diariamente` e `Semanalmente`.
- Providers sem `scheduling` exibem a feature como `Não implementado` e não recebem controles operacionais.
- Em edição, `next_scan_at` é exibido somente como leitura por meio do helper de data/hora já existente.
- O resumo da tabela é provider-neutral e não depende de `aws_configuration`.
- O componente compartilhado recebe somente capability e campos comuns de scheduling; não recebe credenciais OCI.

## Task 22.15.4 — validação integrada final

A revisão final confirmou o diff completo da branch contra a `main` de origem e preservou o escopo da 22.15:

- zero migrations novas na Atividade 22.15;
- zero endpoints novos para scheduling;
- zero scheduler/fila/worker paralelos por provider;
- zero alteração de collectors, analyzers ou regras FinOps;
- coleta manual AWS e OCI permanece independente do schedule;
- scheduled AWS e OCI continuam entrando na mesma fila e no mesmo worker provider-aware;
- a proteção comum contra scans concorrentes permanece baseada em `Scan.cloud_account_id`;
- lifecycle de Opportunity/Observation não foi alterado;
- RBAC existente continua sendo a autoridade para edição e coleta;
- nenhum secret OCI foi adicionado a responses, payloads de scheduling, documentação ou logs da entrega.

## Segurança OCI

- Private key e passphrase armazenadas nunca são carregadas de volta pelo formulário de edição.
- O fluxo de replacement inicia com campos sensíveis vazios e permanece uma ação explícita e separada.
- Schedule-only OCI não aciona replacement de credencial e não envia `private_key_pem`, `private_key_password`, fingerprint, região, User OCID ou scope inalterado.
- A encryption key permanece restrita ao backend/worker e não faz parte do contrato frontend.

## Operação final da 22.15

```text
AWS manual -> fila comum -> worker comum -> executor AWS
AWS scheduled -> scheduler comum -> fila comum -> worker comum -> executor AWS
OCI manual -> fila comum -> worker comum -> executor OCI
OCI scheduled -> scheduler comum -> fila comum -> worker comum -> executor OCI
```

O trigger manual/scheduled é metadata da execução e não cria um pipeline alternativo. `CloudAccount` continua sendo a fonte de verdade do scheduling e `CollectionRun`/Opportunity/OpportunityObservation continuam usando o pipeline provider-neutral já existente.

## UX e limites

- Schedule é opcional e o default permanece `false`.
- Habilitar uma conta não habilita recorrência automaticamente.
- Desabilitar scheduling não remove a coleta manual.
- Não foram implementados CRON, horário fixo, timezone por conta, múltiplos schedules, bulk scheduling, retries configuráveis, dashboards de scheduler, auto-disable, health score ou observabilidade da futura 22.16.

## Próxima atividade

A próxima evolução prevista é **22.16**, dedicada à trilha operacional/observabilidade do scheduling. Ela não é antecipada pela Atividade 22.15.
