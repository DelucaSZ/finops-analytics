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

## Discovery da Atividade 22.5

O worker agora possui a infraestrutura de credenciais e uma camada interna de Discovery/Inventory OCI read-only. Essa camada usa Resource Search para descoberta ampla e APIs `List` de Identity, Compute, Block Storage e Virtual Network para normalizar o inventário inicial de Compute Instances, Block Volumes, Boot Volumes, attachments e Public IPs dentro de `scope_regions` e dos compartments configurados.

O fluxo público de coleta OCI permanece desabilitado até a conclusão das camadas de análise necessárias. Não existe `OciCollectionExecutor` operacional, `manual_collection` e `scheduling` permanecem desabilitados, e a Atividade 22.5 não cria oportunidades, não consulta custo/Usage API, não consulta Monitoring e não usa Cloud Advisor.

A execução interna do Discovery é somente leitura. Além das permissões de Identity já usadas no onboarding/teste de conexão, a identidade OCI destinada às próximas etapas deverá receber permissões de leitura/inspeção estritamente suficientes para Resource Search e para as listagens Wave 1 efetivamente habilitadas. Ausência de permissão é registrada como cobertura incompleta; ela não é interpretada como ausência de recursos.


## Cloud Advisor da Atividade 22.6

Discovery e Cloud Advisor estão implementados como camadas internas de aquisição de dados OCI, mas o fluxo público de coleta OCI permanece desabilitado até a conclusão das etapas de custo, métricas, correlação e analyzers.

A camada de Cloud Advisor usa o client oficial `oci.optimizer.OptimizerClient` em modo exclusivamente read-only. Ela lista recommendations e resource actions, percorre todas as páginas, preserva lifecycle/status nativos e mantém savings estimados como informação fornecida pela Oracle. Nenhuma recommendation é aplicada, descartada, postergada ou convertida automaticamente em Opportunity DeepOps.

Permissões ausentes para Cloud Advisor são tratadas como cobertura incompleta do serviço, não como ausência de recommendations e não como falha geral das credenciais OCI quando outras APIs permanecem acessíveis.

O fluxo público permanece com `manual_collection=false` e `scheduling=false`; não existe `OciCollectionExecutor` registrado e `POST /api/v1/cloud-accounts/{oci_id}/scans` continua indisponível para OCI. Usage API, Monitoring/MQL, correlation engine e analyzers OCI ainda não fazem parte desta etapa.


## Usage API da Atividade 22.7

Discovery, Cloud Advisor e Usage API estão implementados como camadas internas read-only de aquisição de dados OCI. A coleta OCI pública permanece desabilitada até a conclusão de Monitoring/MQL, correlação e analyzers.

A camada de Usage API utiliza o client oficial `oci.usage_api.UsageapiClient` e `request_summarized_usages()`. A janela padrão interna corresponde aos últimos 30 dias completos em UTC, usando granularidade `DAILY`; chamadas internas também podem informar `start_time` e `end_time` explicitamente. A API suporta paginação e a implementação percorre `opc-next-page` até o fim.

O dataset financeiro principal agrupa custo observado por `resourceId`, `service`, `region` e `compartmentId`. Um breakdown auxiliar separado agrupa por `resourceId`, `service`, `skuPartNumber` e `unit` para preservar SKU e quantidade de uso quando a API os fornece. Esses conjuntos não são concatenados para cálculo de total, evitando dupla contagem. O limite oficial de quatro dimensões de `groupBy` é respeitado.

`computedAmount` é tratado como custo observado e `computedQuantity` como quantidade de consumo. Moeda e unidade são preservadas exatamente quando retornadas; moeda ausente não é inferida, múltiplas moedas são agregadas separadamente e nenhuma conversão cambial é executada. Valores negativos/créditos permanecem fatos financeiros nativos e não são classificados como saving DeepOps.

Registros sem `resourceId` são preservados. Quando um `resourceId` existe e um resultado de Discovery é fornecido, a correlação é factual (`inventory_match=true|false`); ausência de correspondência não cria Finding ou Opportunity. Scope de região/compartment é marcado como `in`, `out` ou `unknown`, preservando registros cuja pertença não pode ser determinada.

Falta de autorização na Usage API é cobertura incompleta, não custo zero e não altera automaticamente o `CloudAccount.connection_status`. A camada não cria Opportunity, Finding, CollectionRun OCI, analyzer, saving DeepOps ou snapshot persistido, e não implementa Monitoring/MQL.

O fluxo público permanece com `manual_collection=false` e `scheduling=false`; OCI continua fora do executor público de scans. A próxima atividade é **22.8 — OCI Monitoring/MQL**.


## Monitoring/MQL da Atividade 22.8

Discovery, Cloud Advisor, Usage API e Monitoring estão implementados como camadas internas read-only de aquisição de dados OCI. OCI permanece sem coleta pública até a conclusão da correlação e dos analyzers.

A camada Monitoring usa `oci.monitoring.MonitoringClient.summarize_metrics_data()` com MQL no namespace `oci_computeagent`, consultando CPU, memória quando disponível e rede quando disponível por região/compartment e agrupando séries por `resourceId`. A implementação evita queries por recurso como estratégia padrão. Métrica ausente não é interpretada como zero, e falhas de autorização são representadas separadamente de uma consulta bem-sucedida sem datapoints.

Para uma janela padrão de 30 dias, a implementação usa intervalo de 1 hora. CPU e memória preservam mean/max agregados server-side; P95 do contexto interno é calculado sobre os datapoints horários retornados. `NetworksBytesIn` e `NetworksBytesOut` são tratados como contadores cumulativos e consultados com `increment()`, preservando unidade nativa.

Nenhuma Opportunity, Finding, regra de rightsizing ou saving DeepOps é produzida por Monitoring. `manual_collection=false`, `scheduling=false` e a ausência de executor OCI público continuam inalterados. A próxima camada é o Correlation Engine da Atividade 22.9.

## Correlation Engine da Atividade 22.9

Discovery, Cloud Advisor, Usage API e Monitoring podem ser consolidados internamente em um contexto
analítico por recurso. O OCID/resource ID nativo é a chave de correlação; nomes não são usados como
fallback automático.

A camada preserva relationships, Recommendation→ResourceAction, custos por moeda, breakdown de SKU,
métricas/coverage, janelas temporais, provenance e falhas parciais. Dados sem resource ID ficam em
contexto account/unallocated e dados com OCID ausente do Inventory permanecem representados como
contextos não inventariados.

O Correlation Engine é local/puro: não recebe credenciais, não chama OCI novamente, não persiste
snapshots e não gera recomendações DeepOps. Finding, Opportunity, thresholds, confidence, severity e
saving DeepOps continuam responsabilidade das etapas de analyzers.

OCI permanece com coleta manual e agendamento públicos desabilitados. A próxima atividade é a 22.10,
com os primeiros analyzers OCI sobre o contexto correlacionado.



## Analyzers OCI internos da Atividade 22.10

O DeepOps já possui uma primeira Wave de analyzers OCI internos operando exclusivamente sobre os
dados normalizados pelo Correlation Engine. Eles cobrem Block Volume sem attachment, Public IP
reservado sem associação, Compute parado mantendo storage persistente e ausência total de tags nos
resource types Wave 1 tecnicamente suportados.

Esses analyzers não fazem chamadas OCI, não recebem credenciais e não transformam automaticamente
Cloud Advisor em decisão DeepOps. Recommendations nativas e custos observados podem aparecer como
evidência com provenance explícito, mas savings DeepOps não são inventados.

Os analyzers ainda não são expostos pelo fluxo público de Scan. OCI permanece com
`manual_collection=false`, `scheduling=false`, sem `Scan` público e sem `CollectionRun` público.
A habilitação operacional ocorrerá na Atividade 22.11, após conectar e validar o pipeline completo.
