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

## DeepOps — justificativas das oportunidades (22/09/2026)

- Cada oportunidade exibe um resumo determinístico e “Ver evidências”, com dados observados, critérios e limitações, sem depender de Bedrock.
- Crescimento de custo: datas UTC (fim exclusivo apresentado como último dia incluído), custo esperado normalizado pela média diária, custo recente, delta e percentual. Base zero/negativa não usa mais o percentual artificial de 999%.
- O Cost Explorer é consultado com paginação completa. Para cada anomalia, uma consulta adicional por serviço/região identifica até 5 tipos de uso com maior aumento, usando as mesmas janelas e `UnblendedCost`. O detalhe pode falhar sem descartar o alerta principal. Há chamadas adicionais de API sujeitas à cobrança normal da AWS.
- Novas coletas salvam a configuração efetiva da política e horário da avaliação no JSON de evidências. Registros antigos continuam legíveis, sem inventar datas ou limites; uma nova varredura preenche os dados novos. Sem migração de banco ou novas permissões IAM.
- Alertas financeiros mostram economia “Não estimada”. A interface distingue crescimento de custo, consumo e causa raiz, e informa dados estimados, ausência de métricas CloudWatch e limites das estimativas de economia.
- Validação: 27 testes backend, Ruff e build de produção/tipos frontend aprovados; verificações adicionais de compatibilidade com evidências antigas, datas inclusivas, base zero, tags e ausência de métricas passaram. Validação visual indisponível: navegador remoto bloqueia localhost. AWS/EC2 não foram acessadas para teste real.
- Deploy requer web e worker atualizados; se o timer já estiver ativo, aguardar o deploy da main. Executar nova varredura nas contas para atualizar as evidências.


## DeepOps — oportunidades e navegação por prioridade (22/09/2026)

- Oportunidades: caixas de seleção individuais e seleção de todos os resultados filtrados; ações de aceitar/ignorar em lote com contador e retorno de sucesso/erro.
- Filtros combináveis de conta AWS, prioridade e tipo de oportunidade, além da busca textual. Para tags, usar “Recursos sem tags obrigatórias”. Alterar um filtro limpa a seleção.
- Visão geral: as linhas Alta/Média/Baixa em Risco e impacto levam a `/opportunities?severity=high|medium|low`. Filtros estruturados são preservados na URL.
- A lista carrega todas as páginas de achados abertos, em lotes de 500; removida a limitação visual silenciosa de 100 achados.
- API: `PATCH /api/v1/findings/bulk/status` recebe `finding_ids` e `status` (`accepted` ou `dismissed`). Exige autenticação; valida todo o lote antes do commit e recusa IDs ausentes ou achados já tratados, sem aplicar mudanças parciais.
- Verificações: build de produção e tipos do frontend aprovados; 18 testes Python aprovados, incluindo 8 novos casos de paginação, escopo do lote, duplicatas, autenticação, validação e conflitos; Ruff aprovado. Ajustada também a ordem de imports em `accounts.py`, que falhava no CI.
- Validação visual pendente: o navegador remoto bloqueou o acesso a localhost neste ambiente.
- Atualização na EC2: `git pull --ff-only origin main` e `docker compose up -d --build web api`. Sem migração de banco ou alteração de credenciais.


## DeepOps — deploy automático com rollback (22/09/2026)

- Implementados `scripts/auto_deploy.py`, instalador systemd e guia `docs/auto-deploy.md`.
- Timer consulta `origin/main` a cada minuto; usa fetch + releases isoladas, sem modificar o checkout original. Estado e imagens reais preservados antes de recriar `api`, `worker`, `web` e `proxy`; mantém `db` e volumes.
- Valida containers, reinícios, SQL e HTTP interno API/web/proxy por uma janela estável de 30 segundos. Falhas de ativação restauram a última release saudável; falhas de build preservam containers. Commit malsucedido bloqueado até novo commit ou retry explícito.
- Estado persistente e lock permitem recuperação após interrupção. Rollback não desfaz alterações no banco; mudança de infraestrutura/banco no Compose exige deploy manual. Não é blue/green e não substitui testes funcionais.
- Validação: 13 testes de deploy aprovados (falhas, rollback, recuperação, preservação de checkout/env e imagens), sintaxe Python/Bash verificada. Docker e acesso à EC2 indisponíveis nesta sessão; teste integral ocorrerá na instalação.
- Ativação na EC2 ainda necessária: em `/opt/finops-analytics`, `git pull --ff-only origin main` e `sudo bash scripts/install-auto-deploy.sh`. Consultar `sudo deepops-deploy status` e `sudo journalctl -u deepops-deploy.service -f`.
- Após habilitar, operar pelo controlador; não misturar deploy manual via Compose no checkout original com o timer. O SHA em produção fica no status do controlador. A primeira adoção é um baseline das imagens reais (commit delas desconhecido), seguido do primeiro deploy da main.

## DeepOps — usuários e permissões, etapa 1 (23/09/2026)

- Autorizada e implementada a etapa 1 do plano de segurança: base de usuários,
  perfis `admin`/`operator`/`viewer`, Alembic e migração única do administrador.
- API inicializa o schema e o admin em transação antes de servir; worker aguarda.
  Tabelas antigas preservadas, sem alteração no Compose/volumes. Credenciais do
  `.env` servem somente ao primeiro bootstrap e não sobrescrevem usuários depois.
- Senhas Argon2id, UUID no JWT e consulta de usuário/perfil no banco a cada chamada.
  Tokens antigos rejeitados; mudanças de perfil/e-mail/status invalidam tokens.
- Endpoints `/auth/me` e `/users` (listar/criar/editar/desativar), com proteção do
  último admin ativo serializada no banco. Sem exclusão definitiva ou cadastro público.
- Leituras liberadas aos três perfis; scans/ações de oportunidades/IA para operador
  e admin; usuários, contas AWS e alterações de políticas apenas para admin.
- Escopo seguinte: etapa 2 sessões/convites/recuperação; etapa 3 TOTP; etapa 4 telas;
  etapa 5 HTTPS; etapa 6 liberação externa. A aba de configurações ainda não existe.
- Guia de migração/API/rollback em `docs/users-and-permissions.md`. Rollback da
  imagem preserva dados, mas uma imagem antiga restaura a autenticação antiga.
  EC2 não foi acessada; implantação deve ser acompanhada pelo controlador existente.
- Validação local: 62 testes backend, Ruff e build de produção/tipos frontend
  aprovados. Os 6 testes específicos PostgreSQL aguardam CI (serviço PostgreSQL 17
  incluído no workflow). Publicação bloqueada pela revisão automática por exigir
  autorização explícita para push; branch local `feature/users-foundation` pronta.

## DeepOps — autenticação, etapa 2 (24/09/2026)

- Etapa 1 publicada pelo PR #1 na main (`f667dcd`), após 68 testes backend,
  build frontend e testes do auto deploy aprovados.
- Etapa 2 troca Bearer/JWT por cookie HttpOnly com sessão opaca revogável no banco.
  Frontend remove o token antigo do localStorage. Login mantém as credenciais,
  mas requer nova autenticação; API e web precisam ser atualizados juntos.
- Logout, logout de todos, lista/revogação de sessões próprias, revogação por admin,
  duração absoluta (480 min por padrão) e inatividade (30 min). CSRF vinculado à
  sessão e header obrigatório nas alterações. Confirmação de senha por 5 minutos
  para administração de usuários e emissão de links de acesso.
- Convites de 24 h, recuperação de 30 min, consumo atômico de uso único, hashes no
  banco, reemissão invalida link anterior. Pendentes não contam como último admin.
  Troca de senha encerra sessões. Sem MFA/TOTP ainda (etapa 3).
- Novas páginas /forgot-password, /reset-password, /accept-invitation e /security
  (Minha segurança). Aba administrativa completa permanece na etapa 4.
- SMTP opcional com TLS para recuperação pública, resposta uniforme, limites
  persistentes por identidade/peer. Sem SMTP, admin gera link privado; recuperação
  do único admin por operador do host: `python -m app.manage password-reset --email ...`.
- URLs usam origem configurada e fragmento, removido da página após leitura. Nunca
  logar links/tokens. Não houve envio real de e-mails nos testes.
- Migração 0003_auth_lifecycle aditiva; mantém checkpoint alembic_version=0002_users
  para rollback da imagem da etapa 1. Revisões atuais em deepops_schema_version.
  Essa compatibilidade é testada, incluindo preservação de usuários e consumo
  simultâneo de recuperação. Rollback restaura limitações da autenticação antiga.
- Cookie Secure automático em produção. Desenvolvimento mantém compatibilidade
  com HTTP privado; configurar HTTPS antes de exposição externa. SMTP e origem
  ficam no .env; nenhuma credencial real foi adicionada ao código.
- Guia: docs/authentication-lifecycle.md. Validação visual indisponível: navegador
  remoto bloqueou localhost. EC2 e SMTP reais não foram acessados nesta entrega.
- Validação local da etapa 2: 93 testes backend aprovados, 8 casos PostgreSQL
  destinados ao CI, Ruff e build/tipos de produção do frontend aprovados.

## DeepOps — MFA TOTP, etapa 3 (24/09/2026)

- Etapa 2 publicada pelo PR #2 na main (`c9c34ed`), CI aprovado no PR e após merge.
- Implementados TOTP SHA-1/6 dígitos/30 s, QR gerado pela própria API, chave manual,
  confirmação antes da ativação e segredo criptografado com Fernet. Configuração
  expira em dez minutos e vincula o segredo pendente à sessão que a iniciou.
- Login de conta com MFA entrega desafio de cinco minutos, cinco tentativas, sem
  sessão completa. Segundo fator válido cria sessão marcada como MFA verificado.
  Replay bloqueado por passo temporal; consumo serializado com lock no banco.
- Dez códigos de recuperação de 128 bits, somente hashes no banco, exibidos uma
  vez. Troca do autenticador/regeneração exigem senha e segundo fator; reset de
  senha preserva MFA. Troca do autenticador revoga outras sessões e códigos antigos.
- Recuperação por admin com MFA ou operador do host, com motivo e auditoria,
  revoga sessões/desafios/códigos e obriga novo cadastro, mesmo no modo opcional.
- Configuração `NUVEMIQ_MFA_REQUIRED=true` exige cadastro para todos; sem ele só
  cadastro MFA/logout são permitidos. Default false preserva implantação gradual
  privada. A variável real da EC2 não foi modificada. Liberação externa continua
  dependendo das etapas de HTTPS e revisão operacional.
- Interface em Minha segurança, login com segundo fator/recuperação e /mfa-setup
  para cadastro obrigatório. Telas administrativas completas continuam na etapa 4.
- Chave derivada de NUVEMIQ_SECRET_KEY com HKDF, ou chave Fernet dedicada em
  NUVEMIQ_MFA_ENCRYPTION_KEY. Manter chave estável e backup fora do banco. Exemplos
  conhecidos de segredo não permitem ativação; descriptografia falha sem bypass.
- Migração 0004_totp aditiva; novo checkpoint deepops_mfa_schema_version preserva
  checkpoint da etapa 2 para rollback da primeira implantação. Após cadastrar MFA,
  não retornar a imagens anteriores à etapa 3, que desconhecem o segundo fator.
- Guia de operação, recuperação e limitações: docs/mfa-totp.md. EC2 não acessada;
  validação visual não realizada (navegador remoto bloqueou localhost nesta sessão).
- Validação local: 119 testes backend aprovados, 11 casos PostgreSQL destinados à
  CI; Ruff e build/tipos de produção frontend aprovados.

## DeepOps — Configurações, etapa 4 (24/09/2026)

- Etapa 3 publicada pelo PR #3 na main (`4a5c688`), 130 testes aprovados na CI.
- Menu Configurações com Minha segurança e Sessões para todos; Usuários e Auditoria
  apenas para administradores. /security redireciona para /settings/security.
- Usuários: convite ou criação direta, busca/situação/paginação, status MFA, edição
  de nome/e-mail/perfil, desativação/reativação, renovação de convite, recuperação
  de senha e MFA, lista/revogação individual/global de sessões. Reautenticação no
  próprio fluxo; backend mantém proteção do último admin e permissões existentes.
- Links de acesso somente em memória, copiáveis/ocultáveis; nenhuma mensagem ou
  convite real foi enviado por esta entrega. Recuperação MFA pede senha/segundo
  fator do administrador e motivo, revoga acessos e exige novo cadastro.
- Auditoria administrativa com filtro de categoria/conta e paginação; eventos
  administrativos atômicos e novos eventos de acesso/senha, além dos eventos MFA.
  Sem credenciais nos registros; nomes/e-mails exibidos refletem o cadastro atual.
  Histórico não é retroativo e tentativas de contas inexistentes não geram evento.
- Sem nova migração; reutiliza security_events. Guia em docs/settings.md.
  Certificados/HTTPS permanecem na etapa 5 e liberação externa na etapa 6.
- Validação local: 126 testes aprovados, 11 PostgreSQL destinados à CI; Ruff e
  build/tipos frontend. EC2 não acessada; inspeção visual em navegador indisponível
  nesta sessão (acesso remoto a localhost bloqueado nas etapas anteriores).
