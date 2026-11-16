# Aven — Estado atual do projeto

**Referência:** 16/11/2026.  
**Produto:** Aven — *Clarity. Flow. Control.*  
**Repositório:** `DelucaSZ/finops-analytics`.

Este arquivo resume o estado atual. O histórico detalhado de implementações está em [docs/implementation-roadmap.md](docs/implementation-roadmap.md) e nos documentos de tarefas. Esses registros são históricos, não a especificação operacional mais recente.

## Plataforma e escopo

- Aplicação FinOps multi-cloud self-hosted, com integrações AWS e OCI de leitura.
- Frontend Next.js 15/React 19, backend FastAPI/Python, PostgreSQL 17, worker e Caddy, orquestrados por Docker Compose.
- Usuários com perfis `admin`, `operator` e `viewer`, sessões revogáveis, TOTP, convites, recuperação de senha, auditoria e HTTPS administrável.
- Não realiza ações automáticas de escrita ou remediação sobre recursos cloud.

## Experiências funcionais

| Área | Estado resumido |
| --- | --- |
| Dashboard | KPIs de oportunidades atuais, economia potencial, prioridades e alertas condicionais de coleta |
| Oportunidades | Filtros, evidências, decisões, histórico, arquivamento lógico, retenção e contexto de descoberta |
| Inventory | Persistência de recursos AWS/OCI, observações, consulta server-side, filtros e paginação |
| Flow | Acompanhamento de movimentações e ledger FinOps |
| Billing | Custos AWS via Cost Explorer, perfis, agrupamentos, períodos e distinção realizado/estimado/forecast |
| Cloud Cost Calculator | Simulações read-only AWS EC2/RDS e OCI Compute/DB System; desconto e FX/imposto AWS, OCI BRL final, subtotais parciais, PT-BR/EN-US |
| RDS Reservations | Inventário, cobertura, utilização, vencimentos, oportunidades e pipeline de atualização |
| Coletas | Fila, worker, agendamento, investigação de execução e comparação |
| Configurações | Aparência, contas, políticas, segurança, usuários, auditoria, HTTPS, Pricing OCI e AWS regional, sincronização AWS manual controlada, perfis Billing e retenção |

## Arquitetura de integração

- **AWS:** EC2 Instance Profile e `sts:AssumeRole` com External ID por conta; CloudFormation de permissões em `infrastructure/cloudformation/`.
- **OCI:** API Signing Key armazenada criptografada, escopo explícito por região/compartment, coleta manual ou agendada quando habilitada.
- **RDS:** pipeline `inventory → coverage → opportunities`; falhas são classificadas por estágio e disponibilidade de dados.
- **Custos:** Billing AWS, estimativas de oportunidade e telemetria/custo operacional CloudWatch são domínios diferentes.

## Calculadora Cloud — Fase 27

Rota `/calculator`, API autenticada `/api/v1/calculator/estimate`, motor financeiro `Decimal` e resolução de preços por adaptadores. A Task 27.7 corrige desconto de throughput gp3 EBS, metadados OCI e contratos das fixtures E2E. A validação automatizada específica foi aprovada no [CI 43273433160](https://github.com/DelucaSZ/finops-analytics/actions/runs/43273433160): 1.196 testes backend, 603 testes frontend, 48 cenários de navegador Fase 27, 78 Fase 26 e 50 smoke autenticados. **Fase 27 tecnicamente concluída com limitações externas**, não homologada comercialmente em produção; **o PR #188 foi integrado à `main`. Preços externos ainda precisam ser comprovados na role AWS Pricing e no catálogo comercial OCI DB System (licenças, edição e modalidade). Quando faltar um componente, o total final é nulo e apenas subtotais conhecidos são exibidos.

Relatório técnico: [Task 27.7](docs/calculator/27.7-final-qa.md).

## AWS Pricing regional — Fase 28

As Tasks 28.1–28.8 foram integradas à `main` pelos PRs #190–#197. O pipeline AWS Price List Bulk → catálogo PostgreSQL versionado → Calculadora/Políticas → Opportunities está implementado: importação regional On-Demand USD por SKU/Rate Code/unidade/vigência, sincronização opt-in, Settings → Pricing AWS (`/settings/pricing/aws`), cobertura e status, resolutores de EC2/EBS/RDS e políticas com dados regionais. A 28.8 corrigiu risco de crédito de economia parcial, incompatibilidade de moeda, agregações incompletas, threshold RDS e ranking financeiro, preservando `NULL` e histórico.

**Implementado ≠ homologado ≠ ativado:** as verificações externas pendentes da 28.8 incluem comparação com preços AWS reais em `sa-east-1` e `us-east-1`, PostgreSQL preenchido com restauração, E2E Phase 28 autenticado, QA visual e benchmark/concorrência. O CI de 28.8 foi reportado aprovado, mas não comprova esses cenários. **Task 28.9: readiness documental em branch, decisão NO-GO operacional**; importação de produção e scheduler periódico não foram ativados nesta tarefa. Ver [readiness](docs/pricing/aws/28.9-production-readiness.md) e [runbook](docs/pricing/aws/production-runbook.md).

## Compatibilidade e decisões de manutenção

A identidade exibida ao usuário é Aven. Contratos técnicos já implantados — nomes de variáveis do `.env.example`, nomes de banco e roles, cookies, cabeçalhos, rotas, arquivos e chaves de persistência — permanecem válidos até uma migração dedicada. **Não renomear esses identificadores apenas para adequação visual.**

O Design System usa tokens semânticos, Theme Engine Light/Dark/System e componentes compartilhados. Novos componentes visuais não devem introduzir cores, tipografia, espaçamentos ou raios hardcoded.

## Operação recomendada

1. Validar alterações por PR e CI antes de publicação.
2. Manter backup de PostgreSQL, segredos e material criptográfico.
3. Atualizar os serviços com Docker Compose ou com controlador de deploy opcional, nunca assumindo que o timer esteja ativo.
4. Conferir migrations, API, worker, interface e rotas de negócio após deploy.
5. Verificar permissões e qualidade dos dados em AWS/OCI antes de interpretar ausência de oportunidades como ausência de desperdício.

Para instalação, operação, comandos, segurança e documentação por módulo, use o [README.md](README.md).

## Fase 28 — AWS Pricing: situação de entrega

- **28.1** auditoria (#190), **28.2** persistência/resolver (#191), **28.3** importação oficial (#192), **28.4** sincronização/versionamento (#193), **28.5** UI/admin (#194), **28.6** Calculadora (#195), **28.7** Políticas (#196), **28.8** controles financeiros (#197): **merges confirmados na main**.
- **28.9** homologação operacional/documentação/runbook: **branch em revisão**, sem merge automático e sem aprovação de implantação.
- **Fase 28 — implementação:** integrada ao código até 28.8. **Testes:** CI histórico reportado na 28.8; CI do SHA final 28.9 deve ser conferido. **Homologação comercial/operacional:** **BLOQUEADA** até evidência real. **Produção:** não autorizada por esta task.

Detalhes: [28.9 Readiness](docs/pricing/aws/28.9-production-readiness.md), [Fase 28 Closure](docs/pricing/aws/phase-28-closure.md), [28.8 Finance QA](docs/pricing/aws/28.8-financial-consistency-regression-qa.md).
