# Auditoria administrativa

O DeepOps mantém duas trilhas com responsabilidades diferentes:

- `SecurityEvent`: autenticação, identidade, MFA, sessões e eventos de segurança;
- `AuditEvent`: alterações administrativas e operacionais persistentes do produto.

Históricos específicos de domínio, como `PricingAuditEvent` e `CloudAccountAuditEvent`, continuam existindo quando carregam semântica própria. A trilha genérica é complementar e não migra nem reescreve esses registros.

## Estrutura de `AuditEvent`

Cada evento administrativo registra:

- `id` e `created_at`;
- `actor_id`, quando existe usuário, e snapshots de nome/e-mail do ator;
- `action` e `module`;
- `entity_type`, `entity_id` e `entity_label`;
- `source`: `UI`, `API` ou `SYSTEM`;
- `before`, `after` e `changes`;
- `metadata`;
- `correlation_id` opcional para agrupar eventos da mesma operação.

Os snapshots do ator são deliberados: a leitura histórica não depende do nome/e-mail atual do usuário. A pesquisa textual por ator consulta também `actor_name_snapshot` e `actor_email_snapshot`.

Eventos internos usam `actor_id = null`, `actor_name_snapshot = "SYSTEM"` e `source = "SYSTEM"`.

## Ator x usuário afetado

São conceitos diferentes:

- **Ator / Executado por**: quem executou a operação (`actor_id` + snapshot histórico);
- **Usuário afetado**: quando `entity_type = "user"`, o usuário que sofreu a alteração (`entity_id` + `entity_label`).

Exemplo: João altera Maria de `viewer` para `operator`. João é o ator; Maria é a entidade afetada.

A UI oferece autocompletes separados. `GET /api/v1/audit/users?q=<texto>&limit=20` pesquisa usuários atuais por nome/e-mail, case-insensitive, e retorna somente `id`, `name` e `email`. A consulta histórica aceita também `actor_search` e `subject_user_search`, permitindo localizar snapshots antigos mesmo depois de renome ou troca de e-mail em `AuditEvent`.

## `before`, `after` e `changes`

`before` e `after` são representações explícitas e sanitizadas. Não use `model.__dict__`.

`changes` é calculado em primeiro nível e contém apenas campos alterados:

```json
{
  "enabled": {"from": true, "to": false},
  "scan_interval_hours": {"from": 24, "to": 12}
}
```

Nem toda ação precisa de diff. Operações como `account.connection_test`, `tls.apply` ou emissão de reset podem ser semanticamente auditáveis e usar `metadata` segura mesmo com `changes = {}`.

## Sanitização e limites

Todo payload passa por `sanitize_audit_payload()` antes da persistência. A sanitização recursiva remove `SecretStr`/`SecretBytes` e campos sensíveis, incluindo:

- AWS: access key, secret key e session token;
- OCI: private key e passphrase; fingerprint e tenancy OCID podem permanecer;
- TLS: private keys e PEMs brutos; certificados grandes são reduzidos a tamanho/hash;
- Auth: password, hash, reset/invitation token, MFA secret e recovery code;
- SMTP: password;
- aplicação: `NUVEMIQ_SECRET_KEY` e demais chaves com sufixos reconhecidos como secretos.

Strings grandes e PEMs são resumidos; payloads acima do limite recebem marcador de truncamento com tamanho e SHA-256. Não armazene planilhas, respostas completas de providers, headers HTTP ou payload HTTP bruto em `metadata`.

## Transação

`AuditService.record()` apenas adiciona o evento à `Session`; não executa commit.

A mutação e o evento devem compartilhar a transação:

```python
before = audit_snapshot({"enabled": account.enabled})
account.enabled = False
AuditService.record(
    db,
    actor=current_user,
    module="accounts",
    action="account.disable",
    entity_type="cloud_account",
    entity_id=account.id,
    entity_label=account.name,
    before=before,
    after=audit_snapshot({"enabled": account.enabled}),
    source="API",
)
db.commit()
```

Se houver rollback, a alteração e o `AuditEvent` devem desaparecer juntos. Services administrativos novos não devem fazer commit antes da auditoria. Efeitos externos, como TLS ou testes de conexão, não são ACID com banco/filesystem/provider; nesses fluxos o evento é persistido junto com o estado local confirmado.

## Origem

- `UI`: mutação cuja origem de frontend seja comprovada por contexto interno confiável;
- `API`: chamada autenticada quando não é seguro afirmar origem de UI; é o default conservador;
- `SYSTEM`: worker, scheduler, retenção ou processo interno sem usuário.

Nunca aceite `source` arbitrário do cliente. A origem é definida no servidor.

## Bulk e correlation ID

Operações bulk de oportunidades produzem um evento agregado, por exemplo `opportunity.bulk_reject`, com:

```json
{
  "requested": 1200,
  "updated": 1200,
  "sample_ids": ["... até 20 IDs ..."],
  "ids_truncated": true,
  "reason": "RESOURCE_REQUIRED"
}
```

O evento recebe `correlation_id` UUID. Não são persistidos milhares de IDs. O filtro `correlation_id` permite reconstruir operações relacionadas quando houver mais de um evento no futuro.

## Consulta unificada

`GET /api/v1/audit` é admin-only e retorna `SecurityEvent` + `AuditEvent` em ordenação global estável: `created_at DESC, id DESC`.

A paginação é unificada no backend: cada stream é limitado a `offset + limit`, os registros são mesclados/ordenados e só então o recorte global é aplicado. O frontend não concatena páginas independentes.

Filtros:

- `event_kind=all|security|administrative` (`event_type` continua como alias legado);
- `module`;
- `action`;
- `actor_id`;
- `actor_search`;
- `subject_user_id`;
- `subject_user_search`;
- `entity_type`;
- `entity_id`;
- `source=UI|API|SYSTEM`;
- `correlation_id`;
- `from` (`created_at >= from`);
- `to` (`created_at <= to`);
- `limit`;
- `offset`.

`category` e `user_id` continuam aceitos por compatibilidade com a API antiga de eventos de segurança. Filtros sem significado para `SecurityEvent` tornam esse stream inelegível; por exemplo `module=accounts`, `source=SYSTEM` ou `correlation_id` retornam somente eventos administrativos compatíveis.

## Actions atualmente instrumentadas

| Module | Action | Descrição |
| --- | --- | --- |
| users | `user.create` | criação administrativa de usuário |
| users | `user.update` | alteração cadastral/perfil |
| users | `user.enable` / `user.disable` | ativação/desativação |
| users | `user.invite` | convite de usuário |
| users | `user.invitation_renew` | renovação de convite |
| users | `user.password_reset_issue` | emissão de reset administrativo |
| users | `user.sessions_revoke` | revogação administrativa de sessões |
| users | `user.mfa_reset` | reset administrativo de MFA |
| accounts | `account.create` | criação de conta cloud |
| accounts | `account.update` | alteração de configuração segura |
| accounts | `account.enable` / `account.disable` | ativação/desativação |
| accounts | `account.schedule_update` | alteração de agendamento/coleta |
| accounts | `account.delete` | exclusão |
| accounts | `account.connection_test` | teste de conexão e estado local resultante |
| policies | `policy.update` | alteração de policy/threshold/config |
| policies | `policy.reset` | retorno ao default/herança |
| opportunities | `opportunity.treat` | tratamento |
| opportunities | `opportunity.reject` | rejeição |
| opportunities | `opportunity.reopen` | reabertura |
| opportunities | `opportunity.archive` | arquivamento manual ou SYSTEM |
| opportunities | `opportunity.unarchive` | desarquivamento manual ou SYSTEM |
| opportunities | `opportunity.bulk_treat` | tratamento em massa |
| opportunities | `opportunity.bulk_reject` | rejeição em massa |
| opportunities | `opportunity.bulk_reopen` | reabertura em massa |
| pricing | `pricing.create` | criação manual de preço |
| pricing | `pricing.update` | alteração de preço/metadados |
| pricing | `pricing.override` | criação de versão futura/override |
| pricing | `pricing.deactivate` | desativação |
| billing | `billing.profile_create` | criação de perfil persistente |
| billing | `billing.profile_update` | edição/default/desativação de perfil |
| tls | `tls.apply` | aplicação de HTTPS/TLS |

`SecurityEvent` mantém suas actions próprias (`auth.*`, `user.*`, `mfa.*`) sem substituição pela trilha administrativa.

## Eventos deliberadamente não auditados

Não são gerados `AuditEvent` para:

- GETs, abertura de página, paginação, navegação, refresh ou filtros;
- seleção de contas usada somente para consultar Billing/Cost Explorer;
- consultas de Billing e Cost Explorer;
- leitura de detalhes e históricos;
- updates idempotentes sem alteração persistente, salvo ações semânticas explícitas como teste de conexão;
- logs técnicos, telemetria e observabilidade.

## Como instrumentar um novo módulo

1. Use action canônica `<module>.<verb>`;
2. monte snapshot explícito apenas com campos auditáveis;
3. capture `before` antes da mutação;
4. faça a mutação sem commit intermediário;
5. monte `after`;
6. não registre update se não houve mudança real, salvo ação semântica;
7. chame `AuditService.record()` na mesma `Session`;
8. faça um único commit;
9. adicione testes de rollback, diff e sanitização relevantes.
