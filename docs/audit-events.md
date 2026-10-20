# Auditoria administrativa

O DeepOps mantém dois conceitos de auditoria com responsabilidades diferentes:

- `SecurityEvent`: eventos de autenticação, identidade, MFA e sessões. O histórico existente continua nessa tabela.
- `AuditEvent`: alterações administrativas em módulos do produto. É append-only pela aplicação e não possui endpoints de edição ou exclusão.

`PricingAuditEvent` e outros históricos específicos de domínio continuam existindo quando têm semântica própria. A fundação genérica não migra nem reescreve esses registros.

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

Os snapshots do ator são deliberados: a leitura histórica não depende do nome/e-mail atual do usuário e continua compreensível se o cadastro for alterado ou desativado.

Eventos internos usam `actor_id = null`, `actor_name_snapshot = "SYSTEM"` e `source = "SYSTEM"`.

## `before`, `after` e `changes`

`before` e `after` são representações explícitas e sanitizadas do objeto administrativo antes e depois da mutação. Não use `model.__dict__`.

`changes` é calculado pelo serviço em primeiro nível e contém somente campos cujo valor mudou:

```json
{
  "enabled": {"from": true, "to": false},
  "scan_interval_hours": {"from": 24, "to": 12}
}
```

O diff é determinístico. Objetos aninhados são comparados como um valor de primeiro nível para manter a implementação previsível.

## Sanitização e limites

Todo payload passa por `sanitize_audit_payload()` antes da persistência. A sanitização é recursiva e remove valores de `SecretStr`/`SecretBytes` e campos sensíveis, incluindo senhas, hashes, tokens, credenciais, access keys, secret keys, private keys, MFA secrets, recovery codes, invitation/reset tokens e passphrases.

PEMs de certificado e strings muito grandes são substituídos por resumo com tamanho e SHA-256. Payloads que ainda excedem o limite são substituídos por um marcador de truncamento com tamanho e hash. O objetivo é impedir que certificados completos, policy documents, responses de cloud ou dumps sejam persistidos acidentalmente.

A auditoria nunca deve receber material de private key para "redigir depois"; os serializers das rotas devem montar snapshots seguros e explícitos.

## Transação

`AuditService.record()` apenas adiciona o `AuditEvent` à `Session` SQLAlchemy. Ele não executa `commit`.

Para mutações persistidas no banco, registre o evento na mesma sessão e faça um único commit da operação:

```python
before = audit_snapshot(
    {
        "name": account.name,
        "enabled": account.enabled,
    }
)

account.enabled = False

after = audit_snapshot(
    {
        "name": account.name,
        "enabled": account.enabled,
    }
)

AuditService.record(
    db,
    actor=current_user,
    module="accounts",
    action="account.update",
    entity_type="cloud_account",
    entity_id=account.id,
    entity_label=account.name,
    before=before,
    after=after,
    source="API",
)

db.commit()
```

Se a transação sofrer rollback, o `AuditEvent` também sofre rollback. Não envolva `record()` em `try/except` que silencie falhas.

Operações com efeitos externos, como aplicação de TLS no proxy, registram o evento somente após o gerenciador confirmar a aplicação; falha na persistência da auditoria deve continuar propagando erro ao chamador. Não existe transação ACID única entre banco e filesystem/proxy, portanto novos efeitos externos devem considerar compensação quando isso for tecnicamente possível.

## Origem

- `UI`: mutação comprovadamente iniciada pelo frontend por contexto interno confiável.
- `API`: chamada autenticada cuja origem de UI não pode ser comprovada. É o default seguro.
- `SYSTEM`: worker, scheduler, retenção ou outro processo interno sem usuário.

Não aceite `source` enviado livremente por cliente externo. A origem é definida pelo código servidor.

## Correlation ID

Use `new_correlation_id()` quando uma única operação puder produzir múltiplos eventos. Todos os eventos da operação podem compartilhar o mesmo UUID, permitindo reconstrução posterior sem acoplar o modelo a um fluxo específico de bulk operation.

## Consulta

`GET /api/v1/audit` continua admin-only e entrega uma visão unificada de `SecurityEvent` e `AuditEvent`.

Filtros disponíveis na fundação:

- `event_type=all|security|administrative`;
- `module`;
- `action`;
- `actor_id`;
- `entity_type`;
- `entity_id`;
- `from`;
- `to`;
- `limit`;
- `offset`.

Os parâmetros legados `category` e `user_id` continuam aceitos para compatibilidade. A ordenação é `created_at DESC, id DESC`.

## Como instrumentar um novo módulo

1. Escolha uma ação estável no formato `dominio.acao`, sem enum rígido no banco.
2. Monte snapshots explícitos somente com atributos auditáveis.
3. Nunca inclua segredos nos snapshots ou em `metadata`.
4. Faça a mutação.
5. Monte o snapshot posterior.
6. Chame `AuditService.record()` na mesma `Session`.
7. Faça o commit da mutação e do evento em conjunto.
8. Adicione testes de diff, sanitização e rollback relevantes ao fluxo.

Nesta fundação, os fluxos inicialmente instrumentados são criação/alteração administrativa de usuário e `tls.apply`. A instrumentação abrangente de contas, schedules, policies, pricing, Billing, oportunidades, arquivamento e retenção pertence às tasks posteriores.
