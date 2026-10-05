# OCI onboarding — API Signing Key e coleta manual

O DeepOps suporta cadastro, armazenamento seguro, teste de conexão e **coleta manual read-only OCI**. O agendamento OCI ainda não está disponível.

Estado operacional atual:

- `manual_collection=true` para OCI;
- `scheduling=false` para OCI;
- `finops_policies=false` para OCI;
- a coleta usa o endpoint provider-neutral `POST /api/v1/cloud-accounts/{id}/scans`;
- não existe endpoint OCI específico de coleta;
- nenhuma ação de escrita ou auto-remediation é executada na OCI.

## Identidade e API Signing Key

Crie ou selecione um usuário OCI dedicado à integração e associe-o a um grupo de menor privilégio. Cadastre no usuário somente a chave pública correspondente à chave privada usada pelo DeepOps.

São necessários: Tenancy OCID, User OCID, fingerprint da API Signing Key, região de conexão, regiões pretendidas, compartments pretendidos, chave privada RSA PEM e, quando aplicável, a passphrase.

A Oracle exige chave RSA de pelo menos 2048 bits para API Signing Key. O DeepOps valida o PEM em memória, aceita o marcador adicional `OCI_API_KEY`, deriva a chave pública e compara o fingerprint antes de persistir a credencial.

O Tenancy OCID existe somente em `CloudAccount.native_account_id`; ele é também o identificador nativo gravado em `CollectionRun.account_id` e nas Opportunities OCI. O UUID/PK interno da conta e o User OCID não substituem essa identidade.

## Chave de criptografia do DeepOps

Configure API e worker com a mesma chave estável:

```env
NUVEMIQ_OCI_CREDENTIALS_KEY=<stable-fernet-key>
NUVEMIQ_OCI_CREDENTIALS_KEY_VERSION=v1
```

A chave Fernet deve ser gerada e armazenada fora do repositório e respaldada separadamente do PostgreSQL. O DeepOps não deriva essa chave de dados públicos, não a regenera no startup e não usa `NUVEMIQ_SECRET_KEY` como fallback.

Um backup do banco contém somente ciphertext. Private key e passphrase são descriptografadas apenas em memória durante a resolução de credenciais e não fazem parte de `Scan`, `CollectionRun`, Finding/Opportunity, `OpportunityObservation`, evidence ou logs operacionais.

## Semântica de escopo

- `region`: região base usada pelo SDK;
- `scope_regions`: regiões incluídas na coleta;
- `compartment_ocids`: compartments explícitos;
- `include_root_compartment=true`: inclui explicitamente a tenancy root;
- `include_subcompartments=true`: expande os roots configurados para descendants visíveis.

`scope_regions=[]` não significa todas as regiões. `compartment_ocids=[]` com `include_root_compartment=false` significa nenhum compartment configurado, nunca toda a tenancy por inferência.

O `CollectionRun.scope` persiste apenas metadados não sensíveis de auditoria: regiões, compartments configurados e flags de root/subcompartments. Credenciais, signer e material criptográfico não são incluídos.

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

## Atualização, rotação e teste de conexão

`PATCH /api/v1/cloud-accounts/{id}` mantém as regras de segurança existentes:

- segredo omitido mantém a credencial atual;
- chave vazia ou `null` é rejeitada;
- remoção explícita usa `{"configuration":{"remove_credentials":true}}`;
- fingerprint ou passphrase só mudam junto com um novo PEM;
- a nova chave é validada localmente e testada contra OCI antes do swap;
- falha local, falha OCI ou atualização concorrente preserva integralmente a credencial anterior.

Para rotação, adicione primeiro a nova public key na OCI, envie a nova private key/fingerprint ao DeepOps, valide a conexão e só então remova a public key antiga na OCI. O DeepOps não revoga chaves OCI automaticamente.

`POST /api/v1/cloud-accounts/{id}/test-connection` exige admin e valida Identity/escopo usando as credenciais configuradas. Sucesso no teste básico não implica, por si só, autorização para Cloud Advisor, Usage API ou Monitoring; essas fontes possuem permissões próprias e falhas específicas são representadas como cobertura parcial na coleta.

## Coleta manual OCI

A coleta é acionada pelo mesmo endpoint usado por outros providers:

```text
POST /api/v1/cloud-accounts/{cloud_account_id}/scans
```

O backend deriva o provider exclusivamente de `CloudAccount`. O request não envia provider, credenciais, OciAccountConfiguration ID ou AwsAccount ID.

Para OCI, o `Scan` contém:

- `cloud_account_id` obrigatório;
- `account_id=NULL` no vínculo legado AWS;
- trigger `manual`.

O worker cria um `CollectionRun` com `provider=oci` e `account_id=<tenancy OCID>`, resolve o `OciCollectionExecutor` e executa, em modo read-only:

```text
Discovery
  -> Cloud Advisor
  -> Usage API
  -> Monitoring
  -> Correlation Engine
  -> OCI Analyzers
  -> Findings normalizados
  -> pipeline comum de fingerprint / Opportunity / Observation
```

Os datasets coletados são reutilizados dentro da execução. Analyzers não fazem nova coleta OCI e não existe query Usage/Monitoring por analyzer.

`CollectionRun.resources_analyzed` conta os recursos normalizados pelo Discovery. `CollectionRun.opportunities_found` mantém a semântica global do worker: quantidade de fingerprints lógicos observados no run, e não somente Opportunities recém-criadas.

Uma mesma condição no mesmo OCID/regra reutiliza a mesma Opportunity e cria nova `OpportunityObservation` em cada coleta. Custos, evidence e timestamps não participam da identidade. Decisões humanas `TREATED`/`REJECTED` seguem o lifecycle provider-neutral e não são reabertas silenciosamente.

## Falhas parciais e estado de conexão

A coleta OCI combina fontes independentes. Falta de permissão específica em Cloud Advisor, Usage API ou Monitoring não é convertida em zero e não invalida automaticamente a credencial OCI.

Exemplos:

- Usage sem permissão: custo fica desconhecido, não `0`;
- Monitoring sem cobertura: utilização fica desconhecida, não `0%`;
- Cloud Advisor sem permissão: recommendations ficam indisponíveis, não uma lista comprovadamente vazia.

Quando Discovery e os dados necessários aos analyzers continuam tecnicamente suficientes, o run pode concluir `SUCCESS` e o Scan sinaliza warnings estruturados. Erros de credencial, signing, private key, fingerprint ou tenancy incompatível são fatais e podem atualizar `CloudAccount.connection_status=error`.

## IAM read-only necessário ao pipeline

As permissões devem ser concedidas somente no escopo necessário à conta. Os exemplos abaixo são ponto de partida e devem ser adaptados para grupo/Identity Domain e compartments reais.

### Identity e escopo

O teste de conexão e expansão de compartments usam operações de leitura/inspect de tenancy, user e compartments. Um grupo clássico pode receber, conforme o escopo necessário:

```text
Allow group DeepOpsIntegration to inspect tenancies in tenancy
Allow group DeepOpsIntegration to inspect users in tenancy
Allow group DeepOpsIntegration to inspect compartments in tenancy
```

### Discovery Wave 1

O Discovery consulta Resource Search como acelerador e usa APIs de serviço como fonte autoritativa para Compute, Block/Boot Volumes, attachments e Public IPs. Conceda apenas `inspect`/leitura das famílias efetivamente coletadas nos compartments desejados. Exemplos típicos:

```text
Allow group DeepOpsIntegration to inspect instance-family in compartment <compartment>
Allow group DeepOpsIntegration to inspect volume-family in compartment <compartment>
Allow group DeepOpsIntegration to inspect virtual-network-family in compartment <compartment>
```

Resource Search respeita a visibilidade que o principal já possui sobre os recursos; não use `manage all-resources` para fazer a busca funcionar.

### Cloud Advisor

O código usa somente listagem de recommendations e resource actions. O resource family oficial é `optimizer-api-family`. Para leitura completa dos metadados necessários sem permitir apply/update, prefira `read` em vez de `use/manage`:

```text
Allow group DeepOpsIntegration to read optimizer-api-family in tenancy
```

O DeepOps não chama `BulkApplyRecommendations`, update, dismiss ou postpone.

### Usage API

Para consultar custos por `request_summarized_usages`, a política read-only recomendada pela OCI para análise de custos é:

```text
Allow group DeepOpsIntegration to read usage-reports in tenancy
```

Essa permissão é tenancy-scoped por natureza do dataset de billing/cost analysis.

### Monitoring

O pipeline usa `SummarizeMetricsData`, que requer leitura de métricas. Restrinja por compartment quando possível e, se desejado, pelo namespace `oci_computeagent`:

```text
Allow group DeepOpsIntegration to read metrics in compartment <compartment>
```

Não é necessária permissão para publicar métricas nem gerenciar alarms.

## Segurança operacional

A coleta OCI é estritamente read-only em relação aos recursos OCI. Ela não:

- termina instâncias;
- remove ou desanexa volumes;
- libera Public IPs;
- altera tags;
- aplica recommendations do Cloud Advisor;
- cria ou atualiza recursos OCI.

Evidence persistida é compacta e normalizada; payloads SDK completos, séries extensas de datapoints, respostas raw de billing e objetos de signer não são persistidos.

## Auditoria

`GET /api/v1/cloud-accounts/{id}/audit` permanece admin-only. Eventos de conta registram ator, conta, ação, resultado e horário, sem bodies, PEM, passphrase ou ciphertext. O `Scan`/`CollectionRun` fornece a trilha operacional da coleta.

## Limites atuais e próximas atividades

OCI suporta **coleta manual read-only**. Ainda permanecem fora do produto operacional:

- scheduling OCI (`scheduling=false`);
- recorrência provider-neutral em `CloudAccount`;
- scheduler OCI;
- botão global `Executar coleta` na tela de Coletas;
- rightsizing avançado e novos analyzers além da Wave entregue;
- auto-remediation.

A Atividade 22.12 adicionará o botão global de execução na tela de Coletas. A generalização de scheduling pertence à 22.13 e o scheduler OCI à 22.14.
