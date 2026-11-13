# Aven

**Clarity. Flow. Control.**

Aven é uma plataforma **FinOps multi-cloud, self-hosted**, voltada à visibilidade de recursos, análise de custos, identificação de desperdícios e acompanhamento de oportunidades de otimização em **AWS e Oracle Cloud Infrastructure (OCI)**.

O sistema centraliza inventário, coletas, evidências, custos, reservas e decisões operacionais em uma única experiência web. Aven **não aplica remediações automaticamente**: não encerra, redimensiona nem exclui recursos nas contas cloud. Alterações de configuração e decisões sobre oportunidades são persistidas no próprio sistema, conforme as permissões dos usuários.

> **Estado do projeto:** este documento descreve as capacidades presentes no repositório em 13/11/2026. Recursos e cobertura variam por provedor, permissões IAM e dados disponíveis. Não confunda economia potencial com economia realizada nem ausência de dados com custo zero.

## Sumário

- [Funcionalidades](#funcionalidades)
- [Arquitetura](#arquitetura)
- [Instalação rápida](#instalação-rápida)
- [Integração com AWS e OCI](#integração-com-aws-e-oci)
- [Operação e atualização](#operação-e-atualização)
- [Segurança e permissões](#segurança-e-permissões)
- [Desenvolvimento e testes](#desenvolvimento-e-testes)
- [Documentação técnica](#documentação-técnica)
- [Limitações e interpretação dos dados](#limitações-e-interpretação-dos-dados)

## Funcionalidades

### Dashboard executivo (`/`)

- Visão consolidada do backlog de oportunidades acionáveis e do potencial de economia mensal por moeda.
- Indicadores de oportunidades abertas, tratadas, rejeitadas e novas desde a coleta anterior.
- Distribuição por prioridade/severidade, provedor, conta, serviço e regra.
- Destaques de oportunidades relevantes e alertas condicionais sobre falhas operacionais recentes.
- Foco em situação atual; detalhes de execução e investigação ficam no módulo de Coletas.

### Oportunidades (`/opportunities`)

- Descoberta de desperdícios e ineficiências a partir de evidências coletadas.
- Detalhes técnicos por recurso, regra, conta, região, severidade, confiança e impacto financeiro estimado.
- Filtros, busca, paginação e navegação contextual da coleta que detectou o achado.
- Tratamento, rejeição, reabertura, arquivamento e restauração, com ações em lote conforme permissão.
- Ciclo de vida separado entre **decisão humana** e **presença técnica** do recurso, com observações históricas persistidas.
- Política administrativa de retenção e arquivamento lógico; o histórico técnico pode continuar disponível mesmo quando uma tela não aparece na navegação principal.
- Explicações determinísticas com evidências e critérios; explicação adicional por Amazon Bedrock é opcional.

O catálogo AWS inclui detectores de volumes EBS sem uso, Elastic IPs ociosos, snapshots antigos, instâncias EC2 e recursos relacionados, load balancers, RDS não produtivo, conformidade de tags e anomalias de crescimento de custos. A disponibilidade de cada regra depende da conta, das APIs e das políticas configuradas.

### Inventory (`/inventory`)

- Inventário persistido de recursos descobertos em AWS e OCI, independente da existência de oportunidades.
- Pesquisa, filtros por provedor/conta/região/serviço/tipo/estado, ordenação e paginação no servidor.
- Identificadores técnicos extensos, como ARNs e OCIDs, com contexto de conta, localização e última observação.
- Diferenciação entre recursos observados, ausentes em coletas subsequentes e seus estados de ciclo de vida.
- Histórico de observações de inventário. A ausência em uma coleta não significa exclusão automática do recurso.

### FinOps Flow (`/flow`)

- Fluxo operacional de acompanhamento do tratamento das oportunidades.
- Integração com o ledger FinOps e movimentações manuais já suportadas.
- Acompanhamento de estados, contexto financeiro e decisões, sem confundir projeções com economia comprovada.
- Rota de compatibilidade `/finops/ledger` redirecionada para o fluxo principal.

### Billing (`/billing`)

- Consultas de custos **AWS Cost Explorer**, com seleção explícita das contas cadastradas.
- Resumo financeiro, evolução temporal, gráficos por serviço/conta e detalhamento por agrupamento.
- Períodos predefinidos e personalizados, granularidade, métricas e Billing Profiles.
- Distinção entre dados **realizados, estimados e forecast**, inclusive períodos parcialmente estimados.
- Consulta condicionada à seleção de contas: nenhuma conta selecionada não é interpretada como todas.
- Respeito à moeda retornada pelo provedor e à integridade de períodos incompletos.

### Calculadora Cloud (`/calculator`)

- Simulação de custos **AWS EC2 e RDS** e **OCI Compute VM e Base Database Service (DB System)**, sem provisionamento de recursos nem registro de custos realizados.
- AWS EC2 Linux/Windows Shared On-Demand com EBS gp2/gp3, IOPS e throughput gp3; AWS RDS PostgreSQL/MySQL/MariaDB em Single-AZ ou Multi-AZ DB instance com storage gp2/gp3 suportado.
- OCI Compute Flex E3/E4/E5 com OCPU, RAM, licenciamento Windows, Boot/Block Volumes e VPU; OCI DB System em VM.BaseDB.x86/ECPU mediante vínculos de preço homologados.
- Quantidade e períodos mensais, horas, dias, semanas e intervalos de datas/horas; resumo e detalhamento de componentes com proveniência, moeda e vigência.
- Desconto percentual **somente em componentes elegíveis AWS**, conversão manual opcional USD/BRL e imposto configurável (13% padrão ao converter). OCI usa **preços finais em BRL**, sem ajustes.
- SKUs indisponíveis geram **estado parcial ou não precificado**, com total definitivo nulo. O licenciamento OCI DB System ainda depende de SKUs/bindings comerciais aprovados e não recebe tarifa fictícia.
- Interface autenticada em PT-BR/EN-US, temas Light/Dark/System, componentes Aven e layout responsivo.

Os preços AWS exigem acesso da role central do backend ao AWS Price List Query API; disponibilidade regional, desconto contratual real e valores OCI de produção devem ser verificados. Detalhes: [auditoria final da Fase 27](docs/calculator/27.7-final-qa.md).

### Reservas Amazon RDS (`/rds/reservations`)

- Inventário de DB Instances provisionadas e Reserved DB Instances das contas AWS habilitadas.
- Análise de **cobertura, utilização, capacidade não coberta/parcialmente coberta e vencimento de reservas**.
- Compatibilidade e associação de capacidade conforme regras implementadas no backend; a interface não inventa correspondências.
- Oportunidades derivadas de cobertura insuficiente, capacidade não utilizada e expiração próxima.
- Pipeline de atualização: **inventário → cobertura → oportunidades**, com status operacional, data real do snapshot e classificação de atualização/desatualização.
- Falha do inventário bloqueia o cálculo de cobertura; indisponibilidade da validação opcional via Cost Explorer não transforma cobertura válida em falha; falha de geração de oportunidades não apaga cobertura concluída.
- Atualização por API administrativa ou pelo comando operacional abaixo, além do processamento integrado ao worker.

~~~bash
docker compose exec api python -m app.commands.rds_reservations_refresh
# Opcional: restringir a uma conta cadastrada
docker compose exec api python -m app.commands.rds_reservations_refresh --cloud-account-id 123
~~~

O identificador informado é o ID interno da conta, não o AWS Account ID. A API administrativa oferece `POST /api/v1/rds/reservations/refresh` e `GET /api/v1/rds/reservations/operational-status`. A validação de Billing pode ser desabilitada explicitamente quando necessário, sem alterar o modelo de cobertura.

### Coletas (`/collections`)

- Execuções manuais e agendadas em contas compatíveis, com fila persistente e worker.
- Status, erros, avisos de cobertura parcial, escopo e momento de execução.
- Investigação de oportunidades por coleta e comparação entre execuções.
- Processamento com contexto de provedor e isolamento de falhas onde suportado.
- A rota `/scans` permanece como acesso operacional secundário/de compatibilidade.

### Configurações (`/settings`)

| Área | Capacidades |
| --- | --- |
| Aparência | Tema claro, escuro ou automático pelo sistema; identidade visual Aven |
| Contas | Cadastro, regiões/escopos, credenciais de integração, teste de conexão e agendamento conforme o provedor |
| Políticas | Regras globais e sobrescritas por conta, com edição administrativa |
| Minha segurança | Senha, reautenticação, TOTP e códigos de recuperação |
| Sessões | Consulta e encerramento das próprias sessões |
| Usuários | Convites, criação, edição, perfis, desativação/reativação e recuperação de acesso |
| Auditoria | Eventos de autenticação, segurança e operações administrativas |
| HTTPS | Domínio, certificado automático via Caddy ou certificado próprio, validação e aplicação controlada |
| Pricing OCI | Catálogo e preços efetivos por vigência, com administração e auditoria |
| Billing Profiles | Perfis salvos para consulta de custos |
| Uso e custos | Telemetria de chamadas CloudWatch e estimativas do custo operacional associado |
| Retenção e histórico | Políticas administrativas de retenção de observações e oportunidades |

Áreas e ações são condicionadas ao perfil do usuário e às capacidades do provedor. OCI possui onboarding, coleta manual/agendada e descoberta; o conjunto de regras, a cobertura de serviços e os dados de custos **não são necessariamente idênticos aos da AWS**.

## Arquitetura

~~~text
Navegador
   │
   ▼
Caddy (HTTP/HTTPS)
   ├── Next.js 15 + React 19 (web)
   └── FastAPI (API /api/v1)
          │
          ├── PostgreSQL 17 (dados, filas, auditoria e migrations)
          └── Worker Python (coletas, agendamentos e rotinas operacionais)
                 ├── AWS: STS AssumeRole, inventário, CloudWatch, Cost Explorer, RDS
                 └── OCI: API Signing Key, discovery, métricas e serviços disponíveis
~~~

| Componente | Localização | Responsabilidade |
| --- | --- | --- |
| Frontend | `frontend/` | Páginas, Aven Design System, Theme Engine e integração com a API |
| Backend | `backend/app/` | Domínios, autenticação, endpoints e serviços de coleta/análise |
| Worker | `backend/app/worker_runtime.py` | Processamento assíncrono, scheduler e tarefas periódicas |
| Persistência | PostgreSQL + Alembic | Modelos, histórico, políticas, contas, filas e auditoria |
| Proxy | `proxy/` | HTTPS, certificados e roteamento |
| Infraestrutura | `infrastructure/cloudformation/` | Templates de permissões/roles e exposição AWS |
| Compose | `compose.yaml` | Stack `db`, `api`, `worker`, `web` e `proxy` |

As APIs de provedores são consultadas em modo de leitura; os usuários autorizados podem alterar somente o **estado administrativo interno** do Aven.

## Instalação rápida

### Pré-requisitos

- Host Linux com Docker Engine e plugin Docker Compose.
- Acesso à origem do repositório.
- Recursos compatíveis com os serviços da stack, acesso ao PostgreSQL interno e saída de rede para os provedores configurados.
- Para AWS em produção: credenciais temporárias via **EC2 Instance Profile** e delegação `sts:AssumeRole` nas contas-alvo.
- Para OCI: chave de criptografia estável e material API Signing Key cadastrado, conforme guia específico.
- DNS e certificados válidos se o serviço for exposto externamente.

### Inicialização

~~~bash
git clone https://github.com/DelucaSZ/finops-analytics.git
cd finops-analytics

cp .env.example .env
# Edite .env com os segredos, senhas, URL pública e opções do seu ambiente.
# Não reutilize os valores de demonstração do template.

docker compose up -d --build
docker compose ps
~~~

Acesse a URL configurada no proxy e autentique-se com o administrador provisionado na primeira inicialização. O bootstrap inicial do usuário não redefine automaticamente uma senha já persistida apenas porque o arquivo `.env` mudou.

O template `.env.example` é a **fonte operacional dos nomes exatos das variáveis de ambiente**. Os identificadores internos existentes são mantidos para compatibilidade com bancos, roles, cookies e instalações já em execução; alterar prefixos de configuração diretamente pode impedir o startup.

Para ambientes de avaliação, o template inclui uma opção explícita de modo demonstração. Ela deve permanecer desativada em produção.

**Produção:** antes da publicação, configure TLS/HTTPS, origem pública, segredos, MFA obrigatório, acesso mínimo na rede e backups. Consulte [deploy Linux](docs/deployment.md), [HTTPS](docs/https.md) e [acesso externo](docs/external-access.md).

## Integração com AWS e OCI

### AWS

1. Prepare a role central de execução e o Instance Profile na conta que hospeda a aplicação.
2. Implemente o template de role somente leitura nas contas analisadas, usando um External ID exclusivo por integração.
3. Cadastre no Aven o Account ID, Role ARN, External ID e regiões pretendidas.
4. Execute **Testar conexão** antes da coleta.
5. Habilite Cost Explorer quando for necessário consultar Billing ou validações financeiras; confirme as permissões específicas do inventário RDS.

**Atenção:** permissões IAM e visibilidade de Billing dependem do tipo de conta (management, member ou standalone). Aven não deve misturar indevidamente escopos de faturamento. Os templates existentes de CloudFormation permanecem no diretório `infrastructure/cloudformation/`; verifique seus parâmetros antes de aplicá-los.

Guia: [Onboarding AWS](docs/aws-onboarding.md).

### OCI

1. Crie um usuário/grupo de integração com políticas read-only no escopo autorizado.
2. Cadastre Tenancy OCID, User OCID, fingerprint, regiões, compartments e a chave privada de assinatura da API.
3. Configure uma chave de criptografia Fernet estável para API e worker; mantenha backup fora do banco e do Git.
4. Teste a conexão e habilite a coleta manual ou agendada se a capability estiver disponível.
5. Interprete warnings de permissões/métricas como cobertura parcial, nunca como custo zero.

Guia: [Onboarding OCI](docs/oci-onboarding.md) e [pricing OCI](docs/oci-pricing.md).

## Operação e atualização

~~~bash
# Estado da aplicação
docker compose ps

# Logs relevantes
docker compose logs -f api worker web

# Reconstruir e recriar os serviços da aplicação sem apagar volumes
docker compose up -d --build api worker web proxy

# Health da API dentro do serviço
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"

# Testes e inspeção da configuração consolidada
docker compose config
~~~

O banco e seus volumes persistentes não devem ser removidos em atualizações regulares. Faça backup antes de migrations e valide os serviços após o deploy. Há também um [controlador de atualização automática opcional](docs/auto-deploy.md); não assuma que seu timer está habilitado na instalação atual. Para operação manual, use Compose diretamente.

## Segurança e permissões

- **Perfis:** `admin` (administração), `operator` (operações permitidas) e `viewer` (consulta).
- **Sessões:** cookies HttpOnly revogáveis; autenticação via senha com Argon2id e MFA TOTP quando configurado/obrigatório.
- **Proteção de alterações:** validação CSRF, sessão autenticada, reautenticação em operações sensíveis e controle de permissões no backend.
- **Usuários:** convites temporários, recuperação de senha, desativação e encerramento de sessões.
- **Auditoria:** trilhas de eventos de autenticação, MFA e operações administrativas.
- **Segredos:** nunca faça commit de `.env`, chaves OCI, senhas, material TLS ou credenciais cloud. Use armazenamento seguro e backup externo.
- **Privilégios mínimos:** restrinja IAM, Security Groups, rede e acesso ao banco; prefira HTTPS e mecanismos seguros de administração do host.

Aven **não é um sistema multi-tenant de segregação de clientes por usuário**: usuários autorizados acessam as contas cadastradas conforme o contrato atual de permissões. Consulte [usuários e permissões](docs/users-and-permissions.md), [autenticação](docs/authentication-lifecycle.md), [MFA](docs/mfa-totp.md) e [configurações](docs/settings.md).

## Desenvolvimento e testes

Backend (Python 3.12 recomendado pelo alvo do Ruff):

~~~bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest -q
uvicorn app.main:app --reload
~~~

Frontend (Node.js compatível com Next.js 15):

~~~bash
cd frontend
npm ci
npm run dev

# Verificações do frontend
npm run lint:brand
npm run lint:design-system
npm run lint:i18n
npm run lint:i18n:references
npm run lint:i18n:coverage -- --report
# Em CI: npm run smoke:i18n:browser (Chromium + playwright-core, após build)
npm run lint
npm run typecheck
npm test
npm run build
# E2E Chromium isolado da calculadora, depois do build e da instalação do driver
npm run test:aven:phase27
~~~

A interface oferece `pt-BR` (padrão) e `en-US`, com seletor na Topbar e preferência em cookie `aven.locale`. A camada `next-intl` usa catálogos ICU em ambos idiomas; a alteração de idioma não converte moedas nem altera consultas. Novos textos de interface devem ser localizados e ter proteção de regressão no PR. O relatório 25.9 distingue auditoria estática de verificações reais no navegador, que ainda podem estar pendentes.

O CI contém verificações adicionais de segurança, migrações e smoke tests. Uma execução local parcial não substitui a validação integrada contra AWS/OCI e ambiente de produção.

## Documentação técnica

| Tema | Referência |
| --- | --- |
| Estado atual e decisões | [PROJECT_STATE.md](PROJECT_STATE.md) e [roadmap](docs/implementation-roadmap.md) |
| Design System e branding | [Fonte oficial Aven](docs/brand/aven/README.md) |
| Instalação / HTTPS / acesso externo | [Deployment](docs/deployment.md), [HTTPS](docs/https.md), [External access](docs/external-access.md) |
| AWS e reservas RDS | [Onboarding AWS](docs/aws-onboarding.md), [inventário RDS](docs/task-23-29-rds-reservation-inventory.md), [cobertura RDS](docs/task-23-30-rds-reservation-coverage.md) |
| OCI e preços | [Onboarding OCI](docs/oci-onboarding.md), [Pricing](docs/oci-pricing.md) |
| Inventory | [Modelo de inventário](docs/inventory-domain.md), [Query API](docs/inventory-query-api.md) |
| Oportunidades | [Lifecycle](docs/opportunity-lifecycle.md), [Políticas](docs/opportunity-management-policy.md), [Retenção](docs/opportunity-operational-archiving.md) |
| Dashboard e coletas | [Dashboard](docs/dashboard.md), [Investigação por coleta](docs/collection-investigation.md) |
| Governança | [Auditoria](docs/audit-events.md), [Usuários](docs/users-and-permissions.md), [Settings](docs/settings.md) |
| Calculadora Cloud | [QA e limites da Fase 27](docs/calculator/27.7-final-qa.md), [AWS adapters](docs/calculator/27.3-aws-adapters.md), [OCI adapters](docs/calculator/27.4-oci-adapters.md) |
| Qualidade visual | [Regressão visual](frontend/docs/visual-regression.md) |
| Internacionalização | [Guia pt-BR/en-US](docs/i18n/25.9-translation-guidelines.md), [relatório QA](docs/i18n/25.9-final-qa-report.md), [matriz](docs/i18n/25.9-test-matrix.md), [limitações](docs/i18n/25.9-known-limitations.md) |

Os documentos de tarefas numeradas registram decisões históricas. Para o comportamento **atual**, prefira código, APIs, testes e guias operacionais mantidos.

### AWS Pricing regional — backend de importação (Task 28.3)

A fundação persistente da Fase 28 suporta preço oficial AWS On-Demand por serviço e região em USD. A Task 28.3 adiciona **importação administrativa controlada**, com descoberta via AWS Pricing Bulk API, arquivo JSON incremental, normalização, auditoria de SKU/Rate Code, validação de cobertura, proteção de histórico e `dry-run`. Ainda **não há execução agendada, tela Pricing AWS, migração dos consumidores ou carga real de produção**; Calculadora e Políticas permanecem no comportamento anterior até tasks dedicadas.

Comando seguro de validação: `cd backend && python -m app.commands.aws_pricing_import --service AmazonEC2 --region sa-east-1 --dry-run`. A aplicação exige `AVEN_AWS_PRICING_IMPORT_ENABLED=1` para `--apply`, além do contexto administrativo e IAM do backend. Ver [guia do importador 28.3](docs/pricing/aws/28.3-official-import-engine.md) e [fundação 28.2](docs/pricing/aws/28.2-database-foundation.md).

## Limitações e interpretação dos dados

- **Economia potencial não equivale a economia realizada.** Estimativas de oportunidades dependem da regra e das evidências disponíveis.
- **Billing e oportunidades têm semânticas distintas.** Crescimento de custo não comprova, isoladamente, aumento de consumo nem uma mudança específica em recurso.
- **Moedas diferentes não devem ser somadas silenciosamente** e ausência de preço não deve ser convertida em zero.
- **Reservas RDS dependem de inventário consistente** e compatibilidade técnica; validações opcionais de Cost Explorer não tornam cobertura inválida quando indisponíveis.
- **OCI e AWS têm cobertura funcional diferente.** Uma capability não documentada para um provedor não deve ser presumida.
- **O produto não executa remediação cloud.** Tratar ou arquivar uma oportunidade modifica seu acompanhamento no Aven, não o recurso do provedor.
- **Histórico técnico e visão operacional não são a mesma coisa.** Estados atuais, snapshots e decisões devem ser interpretados conforme os respectivos domínios.

---

**Identidade oficial:** Aven — *Clarity. Flow. Control.*  
**Repositório:** [DelucaSZ/finops-analytics](https://github.com/DelucaSZ/finops-analytics)


### Task 25.9 — validação automatizada da internacionalização

A Task 25.9 adiciona verificadores de catálogo e referências, guardrail incremental contra novos textos fixos e smoke Chromium com HTTPS local. No CI do commit `32ed73d6`, os testes frontend passaram 552/552; [CI](https://github.com/DelucaSZ/finops-analytics/actions/runs/42879306806), [Compose](https://github.com/DelucaSZ/finops-analytics/actions/runs/42879306736) e [Auto Deploy Tests](https://github.com/DelucaSZ/finops-analytics/actions/runs/42879306922) foram aprovados. Veja [matriz](docs/i18n/25.9-test-matrix.md) e [limitações](docs/i18n/25.9-known-limitations.md). A integração automatizada não substitui homologação end-to-end das telas financeiras e administrativas em staging.

### AWS regional Pricing — sincronização (Fase 28.4)

O catálogo AWS agora tem suporte de backend para sincronização regional com **AWS Pricing Bulk API**, histórico operacional e versionamento de tarifas. A sincronização usa as regiões das contas AWS **ativas**, executa verificações por serviço/região, conserva a última versão financeira válida em falhas e oferece consulta de cobertura e de freshness. O importador oficial existente é reutilizado; não há preços hardcoded criados pela Task 28.4.

O agendamento está **desabilitado por padrão** (`AVEN_AWS_PRICING_SYNC_ENABLED=0`); publicação exige opt-in adicional `AVEN_AWS_PRICING_IMPORT_ENABLED=1`. Sem execução massiva ou deploy automático. A UI em Settings será entregue na Task 28.5; Calculadora AWS e Políticas continuam inalteradas até as Tasks 28.6/28.7.

```bash
cd backend
python -m app.commands.aws_pricing_sync --status
python -m app.commands.aws_pricing_sync --coverage --service AmazonEC2 --region sa-east-1
python -m app.commands.aws_pricing_sync --service AmazonEC2 --region sa-east-1 --dry-run
```

Configuração completa, migração 0041, requisitos PostgreSQL, operação, riscos e validação: [Task 28.4 — sincronização e monitoramento](docs/pricing/aws/28.4-synchronization-versioning-monitoring.md).
