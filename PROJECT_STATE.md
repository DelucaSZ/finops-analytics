# Aven — Estado atual do projeto

**Referência:** 12/11/2026.  
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
| Configurações | Aparência, contas, políticas, segurança, usuários, auditoria, HTTPS, preços OCI, perfis Billing e retenção |

## Arquitetura de integração

- **AWS:** EC2 Instance Profile e `sts:AssumeRole` com External ID por conta; CloudFormation de permissões em `infrastructure/cloudformation/`.
- **OCI:** API Signing Key armazenada criptografada, escopo explícito por região/compartment, coleta manual ou agendada quando habilitada.
- **RDS:** pipeline `inventory → coverage → opportunities`; falhas são classificadas por estágio e disponibilidade de dados.
- **Custos:** Billing AWS, estimativas de oportunidade e telemetria/custo operacional CloudWatch são domínios diferentes.

## Calculadora Cloud — Fase 27

Rota `/calculator`, API autenticada `/api/v1/calculator/estimate`, motor financeiro `Decimal` e resolução de preços por adaptadores. A Task 27.7 corrige desconto de throughput gp3 EBS, metadados OCI e contratos das fixtures E2E. A validação específica depende de PR/CI e homologação operacional; **não** considerar estas alterações na `main` até o merge. Preços externos ainda precisam ser comprovados na role AWS Pricing e no catálogo comercial OCI DB System (licenças, edição e modalidade). Quando faltar um componente, o total final é nulo e apenas subtotais conhecidos são exibidos.

Relatório técnico: [Task 27.7](docs/calculator/27.7-final-qa.md).

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
