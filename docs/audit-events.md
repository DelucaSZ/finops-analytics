# Auditoria administrativa

O DeepOps mantém dois conceitos de auditoria com responsabilidades diferentes:

- `SecurityEvent`: autenticação, identidade, MFA e sessões;
- `AuditEvent`: alterações administrativas e operacionais persistentes do produto.

Históricos especializados, como `CloudAccountAuditEvent` e `PricingAuditEvent`, continuam existindo quando possuem semântica própria. A trilha genérica é adicional: não migra, apaga ou substitui esses registros.

## Estrutura de `AuditEvent`

Cada evento administrativo registra:

- `id` e `created_at`;
- `actor_id`, quando existe usuário, e snapshots históricos de nome/e-mail do ator;
- `module` e `action`;
- `entity_type`, `entity_id` e `entity_label`;
- `source`: `UI`, `API` ou `SYSTEM`;
- `before`, `after` e `changes`;
- `metadata` segura;
- `correlation_id` opcional.

Os snapshots do responsável são deliberados. A auditoria continua mostrando quem executou a ação com o nome/e-mail do momento do evento mesmo se o cadastro for renomeado, alterado ou desativado depois.

Eventos internos usam `actor_id = null`, `actor_name_snapshot = "SYSTEM"` e `source = "SYSTEM"`.

## Ator x usuário afetado

São conceitos diferentes:

- **Ator / Executado por**: usuário que executou a operação. Vem de `actor_id` e dos snapshots `actor_name_snapshot` / `actor_email_snapshot`.
- **Usuário afetado**: quando o objeto do evento é um usuário, ele é representado por `entity_type = "user"`, `entity_id` e `entity_label`.

Exemplo: João altera o perfil de Maria de `viewer` para `operator`.

- ator: João;
- entidade afetada: Maria;
- alteração: `role: viewer -> operator`.

A UI possui filtros separados para esses dois conceitos.

## Pesquisa por usuário

`GET /api/v1/audit/users?q=<texto>&limit=20` é admin-only e fornece autocomplete server-side por nome ou e-mail, com comparação case-insensitive e limite baixo. A resposta contém apenas `id`, `name` e `email`.

Na consulta de auditoria:

- `actor_id`: filtra pelo ID estável do responsável;
- `actor_search`: pesquisa nome/e-mail atual e também `actor_name_snapshot` / `actor_email_snapshot` históricos. Um e-mail antigo continua localizando os eventos administrativos gravados quando aquele e-mail era válido;
- `subject_user_id`: filtra o usuário afetado pelo ID estável;
- `subject_user_search`: pesquisa nome/e-mail do usuário afetado, usando o cadastro atual e o `entity_label` histórico do evento.

`SecurityEvent` não possui snapshots históricos próprios na estrutura atual; nesses eventos, filtros textuais de ator/usuário usam a tabela de usuários atual. Os `AuditEvent` administrativos não dependem desse join para preservar a identidade histórica do ator.

## Convenção de actions

Actions administrativas usam o formato canônico `<module>.<verb>` (ou `<module>.<objeto>_<verb>` quando necessário para clareza). O catálogo humano fica centralizado em `app.services.audit_catalog` e é exposto por `GET /api/v1/audit/options` para o frontend.

| Module | Action | Descrição |
| --- | --- | --- |
| users | `user.create` | Usuário criado |
| users | `user.update` | Usuário alterado |
| users | `user.enable` / `user.disable` | Ativação/desativação |
| users | `user.invite` | Convite emitido |
| users | `user.invitation_renew` | Convite renovado |
| users | `user.password_reset_issue` | Recuperação administrativa emitida |
| users | `user.sessions_revoke` | Sessões revogadas |
| users | `user.mfa_reset` | MFA redefinido administrativamente |
| accounts | `account.create` | Conta cloud criada |
| accounts | `account.update` | Configuração segura alterada |
| accounts | `account.enable` / `account.disable` | Habilitação/desabilitação |
| accounts | `account.schedule_update` | Agenda/intervalo de coleta alterados |
| accounts | `account.delete` | Conta removida |
| accounts | `account.connection_test` | Teste de conexão executado |
| policies | `policy.update` | Override/configuração alterados |
| policies | `policy.enable` / `policy.disable` | Policy habilitada/desabilitada |
| policies | `policy.reset` | Override removido/resetado |
| opportunities | `opportunity.treat` | Oportunidade tratada |
| opportunities | `opportunity.reject` | Oportunidade rejeitada |
| opportunities | `opportunity.reopen` | Oportunidade reaberta |
| opportunities | `opportunity.archive` / `opportunity.unarchive` | Arquivamento manual alterado |
| opportunities | `opportunity.bulk_treat` | Tratamento em massa |
| opportunities | `opportunity.bulk_reject` | Rejeição em massa |
| opportunities | `opportunity.bulk_reopen` | Reabertura em massa |
| pricing | `pricing.create` | Item de pricing criado |
| pricing | `pricing.update` | Item de pricing alterado |
| pricing | `pricing.deactivate` | Item de pricing desativado |
| billing | `billing.profile_create` | Perfil persistente criado |
| billing | `billing.profile_update` | Perfil persistente alterado |
| billing | `billing.profile_set_default` | Perfil padrão alterado |
| billing | `billing.profile_deactivate` | Perfil desativado |
| tls | `tls.apply` | Configuração HTTPS/TLS aplicada |

O catálogo também mantém labels amigáveis para os `SecurityEvent` existentes. Actions desconhecidas continuam visíveis por fallback legível no frontend.

## `before`, `after` e `changes`

`before` e `after` são snapshots explícitos e sanitizados. Não use `model.__dict__`.

`changes` é calculado pelo serviço em primeiro nível e contém somente campos cujo valor mudou:

```json
{
  "enabled": {"from": true, "to": false},
  "scan_interval_hours": {"from": 24, "to": 12}
}
```

A UI prioriza `changes`, mostra um resumo na tabela e expande o detalhe em uma tabela Campo / Antes / Depois. Snapshots completos ficam recolhidos e são apresentados de forma estruturada, nunca como dump de JSON bruto.

Ações sem diff são válidas quando possuem semântica própria, por exemplo `account.connection_test` e `tls.apply`. Nesses casos o contexto útil fica em `metadata` segura.

## Sanitização e limites

Todo payload passa por `sanitize_audit_payload()` imediatamente antes da persistência. A sanitização recursiva é a barreira defensiva final e remove `SecretStr`/`SecretBytes` e chaves sensíveis.

Cobertura explícita:

- AWS: access key, secret key e session token;
- OCI: private key e passphrase. `fingerprint` e tenancy OCID podem ser auditados;
- TLS: private key e PEMs brutos. Certificados grandes são resumidos;
- Auth: password, password hash, reset token, invitation token, MFA secret e recovery code;
- SMTP: password;
- aplicação: `NUVEMIQ_SECRET_KEY` e chaves equivalentes normalizadas como secret key.

PEMs de certificado e strings grandes são substituídos por resumo com tamanho/SHA-256 quando aplicável. Payloads que ainda ultrapassam o limite global são substituídos por um marcador resumido.

Os snapshots específicos de conta cloud são ainda mais restritivos:

- AWS: provider, account ID, nome, regiões, enabled, schedule, intervalo, role ARN e flag de management account;
- OCI: tenancy, user OCID, fingerprint, região/escopo, compartments, flags de escopo e apenas o booleano de credencial configurada.

`external_id`, private-key ciphertext, passphrase e material de credencial não entram no snapshot genérico.

## Transação

`AuditService.record()` somente adiciona o `AuditEvent` à `Session`; nunca executa `commit`.

Para mutações administrativas síncronas:

1. obter snapshot anterior;
2. alterar o estado;
3. obter snapshot posterior;
4. adicionar `AuditEvent`;
5. executar um único `commit` do estado e da auditoria.

Se a operação sofre rollback, o `AuditEvent` também sofre rollback.

Services antigos que possuíam commit interno e precisavam ser auditados (`Policies` e perfis de `Billing`) agora aceitam `commit=False` para permitir que a rota auditada seja dona da transação. O comportamento anterior continua disponível por default para outros chamadores.

A validação remota de credencial OCI possui uma exceção arquitetural já existente: a transação de leitura é encerrada antes do I/O de rede para não manter lock aberto. A alteração persistente final e seu AuditEvent continuam sendo gravados juntos após a validação.

## Origem

- `UI`: somente quando o servidor possui contexto interno confiável que comprova a origem;
- `API`: chamada autenticada em que a origem de UI não pode ser comprovada. É o default dos endpoints HTTP administrativos atuais;
- `SYSTEM`: worker/scheduler/processo interno sem usuário.

Nunca confie em um valor `source` arbitrário enviado no payload do cliente. A origem é determinada pelo servidor.

A tela suporta filtro pelos três valores mesmo que, no estado atual, a maior parte das mutações HTTP apareça como `API` por decisão conservadora.

## Bulk e correlation ID

Operações bulk de oportunidades geram **um AuditEvent agregado**, evitando milhares de registros repetitivos.

O evento contém:

- action `opportunity.bulk_*`;
- `correlation_id` UUID;
- quantidade solicitada e atualizada;
- contagem de status anterior/posterior;
- no máximo 20 IDs de amostra;
- `ids_truncated=true` quando houver mais IDs;
- motivo de rejeição quando aplicável;
- apenas `note_present`, nunca a nota inteira por default.

O detalhe da UI exibe o `correlation_id` e permite filtrar eventos relacionados.

## Consulta unificada

`GET /api/v1/audit` é admin-only e entrega `SecurityEvent` + `AuditEvent` em uma linha temporal única.

Filtros atuais:

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
- `from`;
- `to`;
- `limit`;
- `offset`.

`from` e `to` devem conter timezone explícito. A semântica é inclusiva: `created_at >= from` e `created_at <= to`.

Filtros que não se aplicam a `SecurityEvent` são previsíveis. Por exemplo, `module=accounts`, `source=SYSTEM` ou `correlation_id=...` não retornam eventos de segurança.

### Paginação e ordenação

A ordenação padrão e estável é:

1. `created_at DESC`;
2. `id DESC`.

Para preservar paginação global sem concatenar duas páginas independentes, o backend busca `offset + limit` do topo de cada stream já filtrado, faz o merge ordenado e aplica o slice global `[offset:offset+limit]`. O `total` é a soma dos counts filtrados dos streams elegíveis.

Isso evita o erro clássico de buscar 50 `SecurityEvent` + 50 `AuditEvent` e concatenar no frontend.

A tabela `audit_events` já possui índices para `created_at`, ator+data, módulo+data, action, entidade+data e `correlation_id`. Pesquisa textual histórica usa `ILIKE`/`icontains` na escala atual; evolução para índice trigram/full-text pode ser feita quando o volume justificar.

## O que é auditado

Auditamos mutações persistentes ou ações operacionais administrativas com semântica própria.

Nesta etapa estão instrumentados:

- Users e administração de MFA/sessões;
- contas AWS/OCI, schedule, delete e connection test;
- Policies/overrides;
- lifecycle e archive/unarchive de oportunidades existentes;
- bulk treat/reject/reopen;
- Pricing administrativo existente, mantendo também `PricingAuditEvent`;
- perfis persistentes de Billing;
- `tls.apply` já entregue pela Task 24.2.

Não foram encontrados, no estado atual do código, endpoints genéricos adicionais de Settings que justificassem inventar actions sem mutação real.

## O que deliberadamente NÃO é auditado

- GETs e simples consultas;
- abertura/navegação de páginas;
- filtros, paginação e refresh;
- seleção temporária de contas no Billing;
- chamadas de consulta ao AWS Cost Explorer (`summary`, `timeseries`, `breakdown`);
- validação TLS sem aplicação;
- leitura de detalhes/históricos;
- exportação, que não foi criada nesta task;
- logs técnicos/observabilidade, que continuam separados da auditoria funcional.

Updates idênticos não geram evento quando não há mudança persistente e a ação não possui semântica própria.

## Como instrumentar um novo módulo

1. Escolha uma action estável no formato canônico.
2. Adicione label humana ao catálogo compartilhado quando fizer sentido.
3. Monte snapshot explícito apenas com atributos auditáveis.
4. Nunca inclua segredos em snapshot ou `metadata`.
5. Faça a mutação sem commit intermediário.
6. Monte o snapshot posterior.
7. Se não houve mudança e a ação não tem semântica própria, não registre evento.
8. Chame `AuditService.record()` na mesma `Session`.
9. Faça commit único da mutação e do evento.
10. Adicione testes de diff, sanitização, rollback, filtros e UI quando aplicável.
