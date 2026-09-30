# Etapa 21 — validação integrada e fechamento da gestão multi-cloud de contas

## Escopo e revisão de base

A validação foi iniciada sobre a `main` em `18695f3697cd4019517e0eb2a9e71a79dbf0bfbd`, merge do PR #26 (Etapa 20). O escopo cobre exclusivamente as Etapas 16 a 20: navegação de Configurações, identidade comum de contas, OCI API Key, formulário unificado e matriz de capacidades/políticas por provider.

Cadastro e autenticação OCI **não** significam coleta FinOps OCI. Na revisão validada, OCI suporta cadastro, edição e teste de conexão, mas não suporta coleta manual, agendamento nem políticas FinOps.

## Objetivos originais da fase

| Objetivo | Estado esperado | Evidência principal |
| --- | --- | --- |
| “Contas AWS” virou “Contas” | Implementado | rota e tela `/settings/accounts`; navegação sem entrada AWS-específica |
| Contas e Políticas em Configurações | Implementado | `/settings/accounts`, `/settings/policies` e redirects legados |
| Cadastro OCI por API Key preservando AWS | Implementado | `CloudAccount`, `OciAccountConfiguration`, criptografia Fernet e teste OCI |
| Edição AWS/OCI e troca segura de credenciais OCI | Implementado | PATCH comum; substituição OCI explícita, validada antes do swap |

## Matriz de capacidades

| Provider | Cadastro | Edição | Teste de conexão | Coleta manual | Agendamento | Políticas FinOps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| AWS | sim | sim | sim | sim | sim | sim |
| OCI | sim | sim | sim | não | não | não |

Os bloqueios existem no backend e não dependem somente da interface. Tentativas incompatíveis não devem criar `Scan` ou `CollectionRun`.

## Migrations e preservação de dados

A cadeia termina em `0015_oci_api_keys`.

- `0014_cloud_accounts` cria a identidade administrativa `cloud_accounts`, migra cada conta AWS existente para provider `aws`, preserva o ID e liga `aws_accounts.cloud_account_id`.
- A migration aborta se encontrar AWS Account IDs inválidos ou duplicados, em vez de fabricar identidade.
- `0015_oci_api_keys` adiciona configuração OCI cifrada e auditoria de conta.
- Downgrade destrutivo é deliberadamente bloqueado. Recuperação exige backup consistente quando o schema anterior for necessário.
- A suíte de migrations cobre instalação nova e atualização de base anterior em SQLite e PostgreSQL 17, além de verificar drift entre Alembic e os modelos.

## Proteção das credenciais OCI

A API exige uma chave Fernet estável:

```env
NUVEMIQ_OCI_CREDENTIALS_KEY=<stable-fernet-key>
NUVEMIQ_OCI_CREDENTIALS_KEY_VERSION=v1
```

A chave deve ser armazenada fora do repositório e ter backup separado do PostgreSQL. O banco armazena ciphertext; sem a chave correta, as credenciais OCI não são recuperáveis.

Regras validadas pela suíte:

- PEM e passphrase não são retornados por listagem/consulta.
- respostas de validação são sanitizadas para não ecoar inputs sensíveis;
- fingerprint é conferido contra a chave pública derivada;
- PEM protegido por passphrase é suportado;
- ausência/chave inválida falha de forma segura sem impedir operação AWS;
- edição de escopo sem reenviar chave preserva o ciphertext;
- troca de credencial é explícita e validada antes do swap;
- falha ou concorrência durante a troca preserva a configuração anterior;
- alteração relevante invalida o teste de conexão anterior;
- auditoria guarda resultado/código seguro, não o segredo.

O worker AWS-only recebe `NUVEMIQ_OCI_CREDENTIALS_KEY=""` no Compose para não ampliar desnecessariamente o domínio de acesso ao segredo.

## Permissões OCI para o teste de conexão

O teste de conexão atual usa somente OCI Identity. O grupo do usuário de integração precisa de capacidade equivalente a:

```text
Allow group DeepOpsIntegration to inspect tenancies in tenancy
Allow group DeepOpsIntegration to inspect users in tenancy
Allow group DeepOpsIntegration to inspect compartments in tenancy
```

Em tenancies com Identity Domains, adapte a referência do grupo à sintaxe qualificada aplicável. Essas permissões **não** autorizam futuros coletores de Compute, Database, Object Storage ou Billing.

## Implantação

Ordem recomendada:

1. Faça backup consistente do PostgreSQL e garanta cópia recuperável da chave `NUVEMIQ_OCI_CREDENTIALS_KEY`.
2. Atualize código/imagens.
3. Configure a chave OCI na API antes de cadastrar ou testar OCI.
4. Suba banco e API; o startup executa as migrations.
5. Confirme que a revisão em `deepops_mfa_schema_version` é `0015_oci_api_keys`.
6. Suba/reinicie worker, frontend e proxy.
7. Verifique `/health`, autenticação, `/settings/accounts` e `/settings/policies`.
8. Valide uma conta AWS existente antes de iniciar mudanças operacionais.
9. Para OCI, valide cadastro/edição e teste de conexão. Não espere coleta ou agendamento OCI nesta fase.

API e worker devem operar sobre o schema já migrado. Durante rollout, evite manter processos antigos escrevendo em paralelo enquanto a migration estrutural de contas é aplicada.

## Recuperação

Não trate “voltar a imagem anterior” como rollback suficiente quando o binário anterior não conhece o schema atual.

- Falha antes da migration: restaure a revisão anterior da aplicação conforme o procedimento normal.
- Falha após migration, mas com aplicação nova recuperável: corrija/configure e mantenha o schema atual.
- Necessidade real de voltar para schema anterior: restaure **banco + configuração criptográfica** a partir de um backup consistente anterior à migration correspondente.
- Dados criados depois do backup restaurado serão perdidos; isso deve ser tratado explicitamente como impacto de recuperação.

## Validação automatizada

### Baseline anterior à Etapa 21

A `main` em `18695f3` possuía CI e Auto deploy tests aprovados após o merge da Etapa 20.

### Smoke integrado adicionado na Etapa 21

O workflow `.github/workflows/stage21-compose-smoke.yml` cria um projeto Compose isolado no GitHub Actions e valida:

- `docker compose config`;
- build das imagens backend/frontend;
- inicialização real de PostgreSQL 17, API, worker, web e proxy;
- migrations no startup;
- healthcheck da API através do proxy;
- entrega do frontend pelo proxy;
- revisão `0015_oci_api_keys` no banco;
- restart de todos os serviços e nova verificação de prontidão/persistência;
- captura de logs como artefato;
- teardown com volume exclusivo do projeto de CI.

O workflow não usa credenciais cloud reais e não toca volumes de produção.

## Matriz de validação

| Cenário | Ambiente/tipo | Resultado | Evidência/comando | Limitação |
| --- | --- | --- | --- | --- |
| Backend lint/format/pytest | GitHub Actions | ver CI do PR | `ruff check .`, `ruff format --check .`, `pytest -q` | mocks em fluxos cloud |
| Migrations fresh/upgrade | PostgreSQL 17 + SQLite em pytest | ver CI do PR | `test_migrations.py` | não usa dump de produção |
| Frontend unit/build | GitHub Actions | ver CI do PR | `npm test`, `npm run build` | não substitui browser E2E |
| Navegação/redirects | testes frontend | ver CI do PR | `settings-navigation.test.mjs` | validação de browser real permanece separada |
| AWS fluxo operacional | testes backend | ver CI do PR | suites de contas/scans/worker/policies | chamadas AWS são simuladas |
| OCI cadastro/segredo/teste | testes backend | ver CI do PR | `test_cloud_accounts.py` | sem credencial OCI real |
| Bloqueios OCI operacionais | testes backend | ver CI do PR | `test_provider_capabilities.py` | sem coletor OCI por design |
| Stack Compose integrado | GitHub Actions | ver workflow Stage 21 | `docker compose -p deepops-stage21 ...` | sem cloud real |
| Cloud AWS real | ambiente autorizado | não executado nesta etapa | — | requer credenciais/ambiente operacional |
| Cloud OCI real | ambiente autorizado | não executado nesta etapa | — | requer credencial de teste fornecida por mecanismo seguro |
| Browser E2E real | navegador | não executado nesta etapa | — | não há suíte Playwright/Cypress no repositório |
| Produção | produção | não executado nesta etapa | — | implantação não faz parte da validação de repositório |

## Critério de fechamento

A fase pode ser considerada implementada quando CI, migrations e smoke Compose estiverem verdes. Ela não deve ser descrita como “totalmente validada em cloud/produção” enquanto AWS/OCI reais, browser E2E e implantação de produção não tiverem sido executados em ambientes autorizados.
