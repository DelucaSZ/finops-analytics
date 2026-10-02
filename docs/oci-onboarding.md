# OCI onboarding — API Signing Key

A Etapa 18 habilita cadastro, armazenamento seguro e teste de conexão OCI pelo backend do DeepOps. Ela não implementa coletores FinOps OCI.

## Identidade e API Signing Key

Crie ou selecione um usuário OCI dedicado à integração e associe-o a um grupo de menor privilégio. Cadastre no usuário somente a chave pública correspondente à chave privada usada pelo DeepOps.

São necessários: Tenancy OCID, User OCID, fingerprint da API Signing Key, região de conexão, regiões pretendidas, compartments pretendidos, chave privada RSA PEM e, quando aplicável, a passphrase.

A Oracle exige chave RSA de pelo menos 2048 bits para API Signing Key. O DeepOps valida o PEM em memória, aceita o marcador adicional `OCI_API_KEY`, deriva a chave pública e compara o fingerprint antes de persistir a credencial.

O Tenancy OCID existe somente em `CloudAccount.native_account_id`; não há segunda fonte editável.

## Permissões mínimas do teste da Etapa 18

O teste chama somente OCI Identity:

| Operação | Verificação | Permissão |
| --- | --- | --- |
| `GetTenancy` | tenancy configurada está visível | `TENANCY_INSPECT` |
| `GetUser` | usuário configurado está visível e pertence à tenancy | `USER_INSPECT` |
| `ListRegionSubscriptions` | regiões configuradas são subscriptions da tenancy | `TENANCY_INSPECT` |
| `GetCompartment` | cada compartment explícito está visível | `COMPARTMENT_INSPECT` |
| `ListCompartments` | é possível enumerar filhos do escopo-base solicitado | `COMPARTMENT_INSPECT` |

Exemplo para um grupo clássico chamado `DeepOpsIntegration`:

```text
Allow group DeepOpsIntegration to inspect tenancies in tenancy
Allow group DeepOpsIntegration to inspect users in tenancy
Allow group DeepOpsIntegration to inspect compartments in tenancy
```

Para Identity Domains, use a sintaxe qualificada de grupo adequada à tenancy. Não use policy administrativa ampla como padrão. Permissões de futuros coletores FinOps serão definidas separadamente por serviço.

## Chave de criptografia do DeepOps

Configure na API:

```env
NUVEMIQ_OCI_CREDENTIALS_KEY=<stable-fernet-key>
NUVEMIQ_OCI_CREDENTIALS_KEY_VERSION=v1
```

A chave Fernet deve ser gerada e armazenada fora do repositório e respaldada separadamente do PostgreSQL. O DeepOps não deriva essa chave de dados públicos, não a regenera no startup e não usa `NUVEMIQ_SECRET_KEY` como fallback.

A partir da Atividade 22.4, API e worker recebem a mesma chave estável quando OCI está configurada. O worker pode resolver credenciais OCI em memória por meio do serviço interno compartilhado, mas o provider OCI ainda não possui executor de coleta operacional, coleta manual ou agendamento.

Um backup do banco contém somente ciphertext. Para recuperar uma credencial OCI é obrigatório possuir a chave Fernet correspondente à versão gravada. Perder a chave de criptografia não quebra AWS, mas impede o uso das credenciais OCI armazenadas até que sejam substituídas.

## Semântica de escopo

- `region`: região usada pelo SDK para o endpoint OCI.
- `scope_regions`: regiões pretendidas para uso futuro.
- `compartment_ocids`: compartments explícitos.
- `include_root_compartment=true`: inclui explicitamente a tenancy root.
- `include_subcompartments=true`: inclui a intenção de escopo descendente a partir dos roots configurados.

`scope_regions=[]` não significa todas as regiões. `compartment_ocids=[]` com `include_root_compartment=false` significa nenhum compartment configurado, nunca toda a tenancy. O cadastro de escopo não representa uma coleta executada.

## Cadastro pela API

`POST /api/v1/cloud-accounts` exige perfil admin.

```json
{
  "provider": "oci",
  "native_account_id": "<tenancy-ocid>",
  "name": "OCI Production",
  "enabled": true,
  "configuration": {
    "user_ocid": "<user-ocid>",
    "fingerprint": "aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99",
    "region": "sa-saopaulo-1",
    "scope_regions": ["sa-saopaulo-1"],
    "compartment_ocids": ["<compartment-ocid>"],
    "include_root_compartment": false,
    "include_subcompartments": false,
    "private_key_pem": "<private-key-pem>",
    "private_key_password": "<optional-passphrase>"
  }
}
```

Os valores são placeholders. Não use credenciais reais em documentação ou fixtures.

`GET /api/v1/cloud-accounts` e `GET /api/v1/cloud-accounts/{id}` nunca retornam PEM, passphrase ou ciphertext. A resposta contém somente metadados e indicadores como `credentials_configured`.

## Atualização e rotação

`PATCH /api/v1/cloud-accounts/{id}` segue estas regras:

- segredo omitido: mantém a credencial atual;
- chave vazia ou `null`: rejeitada;
- remoção explícita: `{"configuration":{"remove_credentials":true}}`;
- fingerprint ou passphrase só mudam junto com um novo PEM;
- a nova chave é validada localmente e testada contra OCI antes do swap;
- falha local, falha OCI ou atualização concorrente preserva integralmente a credencial anterior.

Para rotação, adicione primeiro a nova public key na OCI, envie a nova private key/fingerprint ao DeepOps, valide a conexão e só então remova a public key antiga na OCI. O DeepOps não revoga chaves OCI automaticamente.

## Teste de conexão

`POST /api/v1/cloud-accounts/{id}/test-connection` exige admin.

O serviço usa `private_key_content` em memória, endpoint derivado da região, timeout curto e sem retry automático. Não lê `~/.oci/config` e não aceita URL arbitrária.

As classes de resultado incluem:
- `local_configuration_invalid`;
- `authentication_failed`;
- `authorization_failed`, incluindo casos em que OCI oculta recurso com 404;
- `network_error`;
- `service_throttled`;
- `service_unavailable`;
- `service_error`;
- `stale_configuration`;
- sucesso com `verified_checks`.

Sucesso comprova somente as verificações executadas. Não comprova acesso a Compute, Database, Object Storage ou outros serviços. Uma listagem vazia não é interpretada como acesso amplo.

## Auditoria

`GET /api/v1/cloud-accounts/{id}/audit` é admin-only. Os eventos registram ator, conta, ação, resultado e horário, mas não armazenam bodies, PEM, passphrase ou ciphertext.

## Etapa 19

O formulário unificado deve consumir estes contratos sem criar uma segunda fonte para Tenancy OCID. Análise e agendamento OCI permanecem bloqueados até existir coletor OCI.
