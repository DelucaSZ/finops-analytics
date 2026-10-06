# OCI onboarding — API Signing Key e coleta read-only

O DeepOps suporta cadastro, armazenamento seguro, teste de conexão e coleta OCI read-only **manual e agendada**.

Estado operacional atual:

- `manual_collection=true` para OCI;
- `scheduling=true` para OCI;
- `finops_policies=false` para OCI;
- a coleta manual usa o endpoint provider-neutral `POST /api/v1/cloud-accounts/{id}/scans`;
- a coleta agendada usa o scheduler comum, a fila comum e o worker comum;
- contas OCI podem configurar a coleta automática em **Configurações > Contas**, usando a mesma interface provider-neutral de AWS;
- não existe endpoint, fila, worker ou scheduler OCI específico;
- nenhuma ação de escrita ou auto-remediation é executada na OCI.

O contrato de scheduling é provider-neutral em `CloudAccount`: `schedule_enabled` e `scan_interval_hours` são campos comuns de create/update e `next_scan_at` permanece controlado exclusivamente pelo backend. A interface compartilhada de AWS/OCI é controlada pela capability `scheduling`; `next_scan_at` é exibido somente como leitura e nunca é calculado pelo frontend. Configuração AWS/OCI contém apenas dados específicos do provider.

## Identidade e API Signing Key

Crie ou selecione um usuário OCI dedicado à integração e associe-o a um grupo de menor privilégio. Cadastre no usuário somente a chave pública correspondente à chave privada usada pelo DeepOps.

São necessários: Tenancy OCID, User OCID, fingerprint da API Signing Key, região de conexão, regiões pretendidas, compartments pretendidos, chave privada RSA PEM e, quando aplicável, a passphrase.

O Tenancy OCID existe em `CloudAccount.native_account_id`; ele é também o identificador nativo gravado em `CollectionRun.account_id` e nas Opportunities OCI. O UUID/PK interno da conta e o User OCID não substituem essa identidade.

## Chave de criptografia do DeepOps

Configure API e worker com a mesma chave estável:

```env
NUVEMIQ_OCI_CREDENTIALS_KEY=<stable-fernet-key>
NUVEMIQ_OCI_CREDENTIALS_KEY_VERSION=v1
```

A chave Fernet deve ser gerada e armazenada fora do repositório e respaldada separadamente do PostgreSQL. Private key e passphrase são descriptografadas apenas em memória durante a resolução de credenciais e não fazem parte de `Scan`, `CollectionRun`, Finding/Opportunity, `OpportunityObservation`, evidence ou logs operacionais.

## Semântica de escopo

- `region`: região base usada pelo SDK;
- `scope_regions`: regiões incluídas na coleta;
- `compartment_ocids`: compartments explícitos;
- `include_root_compartment=true`: inclui explicitamente a tenancy root;
- `include_subcompartments=true`: expande os roots configurados para descendants visíveis.

`scope_regions=[]` não significa todas as regiões. `compartment_ocids=[]` com `include_root_compartment=false` significa nenhum compartment configurado, nunca toda a tenancy por inferência.

`CollectionRun.scope` persiste apenas metadados não sensíveis de auditoria. Credenciais, signer e material criptográfico não são incluídos.

## Coleta manual OCI

A coleta manual é acionada pelo endpoint provider-neutral:

```text
POST /api/v1/cloud-accounts/{cloud_account_id}/scans
```

Para OCI, o `Scan` contém `cloud_account_id` obrigatório, `account_id=NULL` no vínculo legado AWS e trigger `manual`.

## Coleta agendada OCI

O schedule é armazenado somente em `CloudAccount`:

- `schedule_enabled`;
- `scan_interval_hours`;
- `next_scan_at`.

O contrato de escrita é o mesmo para AWS e OCI. Um update de scheduling usa o endpoint comum de conta, por exemplo:

```json
{
  "schedule_enabled": true,
  "scan_interval_hours": 24
}
```

Em **Configurações > Contas**, AWS e OCI usam o mesmo bloco visual de scheduling quando `capability.scheduling=true`. O usuário pode ativar/desativar a coleta automática, escolher um dos intervalos suportados e, em edição, visualizar `next_scan_at` como valor read-only retornado pelo backend. Providers com `scheduling=false` permanecem com a feature indisponível e não recebem controles operacionais.

No frontend, create/update enviam os campos de scheduling no nível comum. Um PATCH OCI somente de scheduling não serializa `configuration`, portanto não reenvia `private_key_pem`, `private_key_password`, `fingerprint`, `scope_regions`, `compartment_ocids`, `region` ou `user_ocid`. Alterações combinadas continuam parciais: scheduling permanece no nível comum e somente os campos OCI efetivamente alterados entram em `configuration`.

`next_scan_at` não é aceito como input: ele é calculado pelo backend. `OciAccountConfiguration` não contém campos de scheduling; consequentemente, um PATCH somente de scheduling não exige nem reenvia private key/passphrase, não altera scope, não incrementa `credential_revision`/`configuration_revision` e não invalida `connection_status`.

Quando uma conta OCI está habilitada, possui schedule explicitamente habilitado e está vencida, o scheduler comum cria um `Scan` com:

- `cloud_account_id=<id da CloudAccount OCI>`;
- `account_id=NULL`;
- `trigger=scheduled`;
- status inicial `pending`.

A prevenção de concorrência usa `Scan.cloud_account_id`. Portanto um scan OCI manual `pending/running` bloqueia a criação de um scheduled concorrente, e um scheduled ativo bloqueia uma nova coleta manual conforme o contrato comum da fila.

Após enqueue bem-sucedido, `next_scan_at` avança usando `scan_interval_hours` com a mesma semântica já utilizada por AWS. A capability `scheduling=true` significa suporte operacional, não opt-in: contas existentes continuam com schedule desativado até configuração explícita.

## Worker e pipeline

Manual e scheduled entram no mesmo fluxo:

```text
Scan
  -> CloudAccount(provider=oci)
  -> Collection Executor Registry
  -> OciCollectionExecutor
  -> Discovery
  -> Cloud Advisor
  -> Usage API
  -> Monitoring
  -> Correlation Engine
  -> OCI Analyzers
  -> Findings normalizados
  -> fingerprint / Opportunity / OpportunityObservation
```

O trigger é metadata da execução e não muda o pipeline. `CollectionRun` é criado normalmente com `provider=oci`, `account_id=<tenancy OCID>` e vínculo ao `scan_id`.

A identidade lógica da Opportunity não inclui o trigger. Assim, a mesma condição observada em uma coleta manual e depois em uma coleta scheduled reutiliza a mesma Opportunity e cria uma nova `OpportunityObservation` para o novo `CollectionRun`.

Decisões humanas `OPEN`, `TREATED` e `REJECTED` seguem o lifecycle provider-neutral e não são reabertas silenciosamente por uma coleta scheduled.

## Falhas parciais e estado de conexão

Falta de permissão específica em Cloud Advisor, Usage API ou Monitoring continua sendo tratada como cobertura parcial quando o restante do pipeline é tecnicamente utilizável. Isso não transforma custo desconhecido em zero nem invalida automaticamente a credencial OCI.

Erros de credencial, signing, private key, fingerprint ou tenancy incompatível são fatais e podem atualizar `CloudAccount.connection_status=error`. Erros persistidos e logs passam pela sanitização comum e não devem conter credenciais.

## IAM read-only

O trigger scheduled não exige nenhuma permissão OCI adicional. O `OciCollectionExecutor` usa as mesmas APIs e o mesmo principal da coleta manual.

Exemplos de permissões read-only que podem ser necessárias conforme o escopo efetivamente coletado:

```text
Allow group DeepOpsIntegration to inspect tenancies in tenancy
Allow group DeepOpsIntegration to inspect users in tenancy
Allow group DeepOpsIntegration to inspect compartments in tenancy
Allow group DeepOpsIntegration to inspect instance-family in compartment <compartment>
Allow group DeepOpsIntegration to inspect volume-family in compartment <compartment>
Allow group DeepOpsIntegration to inspect virtual-network-family in compartment <compartment>
Allow group DeepOpsIntegration to read optimizer-api-family in tenancy
Allow group DeepOpsIntegration to read usage-reports in tenancy
Allow group DeepOpsIntegration to read metrics in compartment <compartment>
```

Adapte as policies ao menor escopo necessário. O DeepOps não chama operações de apply/update/dismiss do Cloud Advisor nem altera recursos OCI.

## Segurança operacional

A coleta OCI é estritamente read-only. Ela não termina instâncias, remove/desanexa volumes, libera Public IPs, altera tags, aplica recommendations ou cria/atualiza recursos OCI.

Evidence persistida é compacta e normalizada; payloads SDK completos, séries extensas, respostas raw de billing, signer, private key, passphrase e chaves de criptografia não são persistidos.

## Estado após a Atividade 22.15

A interface de recorrência OCI está concluída em **Configurações > Contas**. AWS e OCI utilizam o mesmo contrato de `CloudAccount`, a mesma capability de scheduling, o mesmo scheduler, a mesma fila, o mesmo worker e a mesma lógica visual. A recorrência continua opcional e desativada por padrão; alterar somente o scheduling não exige reenvio de credenciais OCI.

A próxima evolução prevista é a **Atividade 22.16**, dedicada à trilha operacional e observabilidade. Ela não é antecipada pela 22.15.
