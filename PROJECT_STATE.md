# DeepOps — Estado do projeto

Atualizado em: 2026-09-22 (UTC)

## Atualização — 2026-09-22: DeepOps e legibilidade

Esta atualização prevalece sobre os registros históricos abaixo.

- Nome do produto alterado de NuvemIQ para DeepOps no menu, login, inicialização, título da aba, API, prompt de IA e documentação.
- Paleta escura/verde preservada. Texto padrão de 16 px, textos de apoio de 13–14 px e etiquetas/cabeçalhos de no mínimo 12 px, em unidades rem.
- Cores de texto secundário mais claras, botões maiores, foco de teclado visível e tabelas com rolagem acessível.
- Corrigida a regra genérica de spans das tabelas que sobrescrevia cores e formato das etiquetas de prioridade/status.
- Corrigido o botão Sair em telas estreitas e adicionada a marca ao login móvel.
- Compatibilidade preservada: variáveis NUVEMIQ_*, credenciais, banco/volumes, localStorage, External IDs e roles IAM existentes. Não renomear esses identificadores na EC2 para aplicar esta atualização.
- Base remota utilizada: b398911bcefdbab5a10ab540b85fc7546c0c6b2b, incluindo a geração de External ID pelo backend.
- Validação: build de produção Next.js e tipos aprovados; git diff --check aprovado; cores principais de texto com contraste mínimo de 7,13:1 nas quatro superfícies sólidas do tema.
- Limitações: navegador remoto bloqueou o acesso ao localhost, então a renderização visual não foi verificada. Pytest não pôde concluir devido a falha na dependência binária pydantic_core do ambiente local; as mudanças no backend são apenas textos de marca.
- Aplicação na EC2: git pull --ff-only origin main, seguido de docker compose up -d --build web api worker. Não exige migração de dados.

## Registro anterior

## Objetivo

Aplicação web self-hosted para Linux que analisa eficiência e desperdícios em múltiplas contas AWS. O motor de regras e de estimativas é determinístico e auditável; IA é usada apenas para explicar, correlacionar e priorizar os achados.

## Escopo validado do MVP

1. Volumes EBS sem anexação.
2. Elastic IP sem associação.
3. Snapshots fora da retenção.
4. EC2 desligada mantendo EBS pago.
5. EC2 não produtiva ligada fora do expediente.
6. Load Balancer sem tráfego.
7. RDS não produtivo ocioso.
8. Recursos sem tags de ambiente ou responsável.
9. Crescimentos anormais por conta, serviço e região.

Cada política possui configuração global e sobrescrita por conta em nível de campo. As contas que não sobrescrevem um campo herdam seu valor global.

## Arquitetura implementada

- Frontend: Next.js 15 e TypeScript.
- API: FastAPI, SQLAlchemy e Boto3.
- Banco: PostgreSQL 17.
- Processamento: worker Python com fila persistida no banco e agendamento de varreduras.
- Proxy: Caddy.
- Execução: Docker Compose em uma EC2 Linux.
- CI: GitHub Actions.
- Infraestrutura AWS: templates CloudFormation para a role central da EC2 e a role somente leitura nas contas analisadas.

Serviços do Compose: `postgres`, `api`, `worker`, `web` e `proxy`.

## Acesso às contas AWS

Decisão final: usar Instance Profile na EC2 central e `sts:AssumeRole` nas contas analisadas.

- Não usar Access Key permanente.
- Não usar Roles Anywhere neste MVP.
- Cada conta cadastrada informa Account ID, Role ARN, External ID, regiões e parâmetros opcionais.
- A conexão pode ser validada pela interface usando `AssumeRole` e `GetCallerIdentity`.
- A management account pode ser cadastrada para coleta consolidada do Cost Explorer.

## Funcionalidades prontas

- Login administrativo com JWT.
- CRUD de contas AWS.
- Teste de conexão por conta.
- Catálogo das nove políticas.
- Configuração global e sobrescrita por conta.
- Execução manual e agendada de scans.
- Histórico de scans e estado `completed_with_warnings` para falhas parciais.
- Achados com severidade, custo estimado, risco, evidências e recomendação.
- Dashboard executivo.
- Tela de oportunidades.
- Resolução conservadora de achados: uma regra que falha na coleta não encerra achados anteriores indevidamente.
- Explicações opcionais via Amazon Bedrock, desabilitadas por padrão.
- Modo demonstração com dados de exemplo usando `NUVEMIQ_DEMO_MODE=true`.

## Estrutura relevante

- `frontend/`: interface web.
- `backend/app/api/`: rotas da API.
- `backend/app/services/collectors.py`: nove análises FinOps.
- `backend/app/services/policies.py`: defaults e mesclagem global/conta.
- `backend/app/services/aws_auth.py`: autenticação STS AssumeRole.
- `backend/app/services/ai.py`: explicações opcionais via Bedrock.
- `backend/app/worker.py`: processamento e agendamento.
- `infrastructure/cloudformation/`: roles central e cross-account.
- `docs/aws-onboarding.md`: configuração das contas AWS.
- `docs/deployment.md`: implantação em Linux/EC2.
- `compose.yaml`: stack completa.
- `.env.example`: variáveis necessárias, sem credenciais reais.

## Validações concluídas no desenvolvimento anterior

- Ruff format/check: aprovado.
- Pytest: 10 testes aprovados.
- Build de produção do Next.js: aprovado.
- Validação de tipos do frontend: aprovada durante o build.
- `cfn-lint` nos dois templates CloudFormation: aprovado.
- Smoke test da API: health, login e catálogo com nove políticas.
- Smoke test do modo demo: uma conta, quatro achados e economia demonstrativa de 454,13.
- Nenhum segredo ou `.env` real foi versionado.

O Docker não estava disponível no ambiente de desenvolvimento desta sessão. Portanto, a subida integral com `docker compose` deve ser validada na EC2.

## Publicação no GitHub

- Repositório remoto: `https://github.com/DelucaSZ/finops-analytics.git`.
- Branch de destino: `main`.
- Base remota preservada: `1207cca050f137a3075984eba79514bcded92388` (`Initial commit`).
- Fonte: os 79 arquivos do pacote `NuvemIQ-MVP.zip`, com atualização deste documento.
- Escrita pela integração GitHub validada após a autorização do usuário.
- Publicação como novo commit descendente da base remota, sem force-push.
- Os commits locais anteriores `a8510c3` e `4af3bce` são referências históricas: o ZIP não contém o diretório `.git`, portanto seus objetos não foram recuperados.

### Fluxo de trabalho pelo tablet

- A integração autenticada permite publicar arquivos, commits e atualizar a branch diretamente pelo chat.
- O usuário não precisa executar comandos Git no tablet para esse fluxo.
- Antes de cada publicação, consultar a branch remota e preservar alterações concorrentes.
- Credenciais de Git HTTPS no terminal local não foram configuradas; a publicação usa a integração.
- Nunca enviar tokens ou senhas pelo chat.

### Verificações desta publicação

- Os 79 arquivos recuperados foram comparados byte a byte com o ZIP antes da atualização deste documento.
- Análise sintática dos arquivos Python aprovada.
- Nenhum `.env` real ou padrão de chave privada/token foi encontrado na verificação realizada.
- Os testes e builds listados acima são resultados anteriores; não foram reexecutados nesta etapa de publicação.

## Próxima etapa recomendada

1. Conferir a execução do CI no GitHub após a publicação.
2. Preparar uma EC2 Ubuntu ou Amazon Linux com Docker e Docker Compose.
3. Anexar a role central à EC2.
4. Aplicar a role somente leitura nas primeiras contas AWS.
5. Copiar `.env.example` para `.env` e definir senhas/segredos fora do Git.
6. Executar `docker compose up -d --build`.
7. Validar login, cadastro de conta, `AssumeRole` e primeiro scan real.

## Comandos de verificação local

```bash
cd backend
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/pytest -q

cd ../frontend
npm run build

cd ..
backend/.venv/bin/cfn-lint infrastructure/cloudformation/*.yaml
git diff --check
```

## Regra de continuidade

Ao retomar o projeto, usar este arquivo como fonte de verdade do estado atual. Não refazer a arquitetura nem trocar o modelo de autenticação sem uma nova decisão explícita.

