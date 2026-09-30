# Deploy automático na EC2 com rollback

A EC2 consulta `origin/main` a cada minuto (90 segundos após boot/instalação).
As mudanças publicadas no GitHub passam a chegar automaticamente à aplicação.
Não é necessário abrir portas, configurar webhook nem fornecer acesso SSH ao ChatGPT.

## Instalação única

Pré-requisitos: Ubuntu com systemd, Python 3 com `tarfile.data_filter` (Ubuntu
24.04+), Git, Docker e Compose com `up --wait`. O usuário root precisa conseguir
ler o repositório sem prompt de senha. O instalador testa essa autenticação.
A stack atual precisa estar funcionando e o projeto Compose deve ser `nuvemiq`
(nome técnico mantido para preservar volumes e banco).

Execute na EC2:

```bash
cd /opt/finops-analytics
git pull --ff-only origin main
sudo bash scripts/install-auto-deploy.sh
```

Se houver alterações locais rastreadas, o instalador interrompe sem descartá-las.
Isso inclui eventuais correções locais de `backend/app/core/config.py`.
Resolva-as preservando a correção já incorporada à `main`; não use `reset --hard`.
O `.env` continua em `/opt/finops-analytics/.env` e nunca entra no Git.
O instalador preserva a configuração existente em `/etc/deepops-deploy.json`.

## Como funciona

1. Na instalação, testa a stack atual e preserva as imagens realmente em execução.
   Esse primeiro snapshot é chamado `baseline-...`, pois não é possível deduzir o
   commit de uma imagem antiga sem metadados de build.
2. Faz `git fetch` de `main` e extrai o commit exato em um diretório de release.
   O checkout de trabalho não recebe merge, reset ou alterações automáticas.
3. Copia o `.env` para a release e constrói as imagens enquanto a versão atual
   continua atendendo. Falha de build não altera containers em execução.
4. Guarda os IDs das imagens e a configuração resolvida. Recria `api`, `worker`,
   `web` e `proxy` com imagens locais, sem baixar ou reconstruir durante rollback.
   O PostgreSQL e os volumes permanecem em execução.
5. Verifica os healthchecks existentes, executa `SELECT 1` no banco a partir da
   API e testa HTTP da API, frontend e rotas do proxy. Exige 30 segundos estáveis,
   observando também o ID e contador de reinícios de todos os containers.
6. Antes do build, compara o conteúdo de `backend/app/migrations/versions` com a
   release saudável. Qualquer adição, remoção ou alteração de migration bloqueia o
   auto-deploy e exige implantação manual com backup consistente.
7. Para releases sem mudança de migration, se a ativação passar, registra o SHA como
   saudável. Se falhar, restaura as imagens e configuração anteriores e repete a
   validação. O commit que falhou fica bloqueado; um commit novo pode ser tentado
   normalmente.

`docker compose up --wait` aguarda containers running/healthy; por isso os testes
HTTP/SQL e a janela de estabilidade complementam o Compose. Referência:
https://docs.docker.com/reference/cli/docker/compose/up/

Existe uma breve indisponibilidade durante a recriação: não é um deploy blue/green.
O rollback automático cobre falhas detectadas durante deploy/estabilização; não
identifica todos os bugs funcionais nem falhas surgidas horas depois. O worker é
verificado quanto a execução/reinícios, não pelo resultado de uma varredura AWS.
Reiniciar o worker durante uma varredura pode interrompê-la; pause o timer durante
varreduras críticas. Este mecanismo não aguarda o CI do GitHub: publique na `main`
somente código já validado, ou proteja a branch exigindo CI antes do merge.

## Operação

```bash
# Ver commit saudável, anterior, atualização pendente e commits bloqueados
sudo deepops-deploy status

# Acompanhar atualizações
sudo journalctl -u deepops-deploy.service -f

# Consultar agenda
systemctl list-timers deepops-deploy.timer

# Verificar agora (também permite recuperação de deploy interrompido)
sudo systemctl start deepops-deploy.service

# Pausar novas atualizações; um deploy já em andamento continua até terminar
sudo systemctl stop deepops-deploy.timer

# Retomar
sudo systemctl start deepops-deploy.timer

# Voltar à versão anterior e bloquear a versão que foi removida
sudo deepops-deploy rollback

# Desbloquear tentativas após corrigir problema externo, como disco/rede
sudo deepops-deploy retry
sudo systemctl start deepops-deploy.service

# Depois de um deploy manual com migration, adotar a stack saudável como novo baseline
sudo deepops-deploy adopt
```

Um lock impede deploys simultâneos. O estado é gravado atomicamente antes da
ativação; após reboot/interrupção, a próxima consulta restaura a última versão
saudável antes de avaliar commits novos. Se o próprio rollback falhar, a transação
permanece pendente, o serviço sinaliza erro no journal e a próxima execução tenta
a recuperação de novo. Isso não garante recuperação se a EC2, disco, Docker ou
banco estiverem indisponíveis.

## Dados e manutenção

- O rollback é de **código, imagens e configuração**, não dos dados gravados.
  O controlador recusa qualquer alteração nos arquivos versionados de migrations,
  além de mudanças na definição do serviço `db`, redes, volumes, configs e secrets.
  Uma release com migration exige deploy manual e backup consistente; assim uma
  falha depois da migration nunca dispara rollback automático para imagens antigas.
  Isso ainda não detecta SQL ad-hoc destrutivo executado fora das migrations.
- Nunca executa `docker compose down -v`, `git reset --hard` ou limpeza de volumes.
- Releases, configurações resolvidas, cópias do `.env` e estado ficam em
  `/var/lib/deepops-deploy`, com diretórios privados e arquivos sensíveis `0600`.
  As imagens são retidas com tags locais. Não execute `docker system prune -a` nem
  remova essas tags/releases sem preservar as versões `current`, `previous` e
  qualquer transação `pending`. Releases não são apagadas automaticamente;
  acompanhe o espaço em disco e retenha as versões necessárias para recuperação.
- A origem do `.env` é o checkout original. Alterações nele são usadas no próximo
  commit implantado; o rollback restaura a cópia da release saudável.
- Após ativar esta automação, use `deepops-deploy` para operar a stack. O `git log`
  do checkout original não identifica a versão em produção; use `status`.
  Não misture `docker compose up` manual no checkout original com o timer ativo.
- O controlador é instalado em `/usr/local/sbin` e não altera a si mesmo durante
  um deploy. Para atualizar o controlador: pare o timer, espere qualquer execução
  ativa terminar, execute `git pull --ff-only origin main`, rode novamente o
  instalador e retome o timer. O baseline e estado são preservados.


## Releases com migration

Use este procedimento para uma release que altera `backend/app/migrations/versions`:

1. Antes de publicar a revisão para o branch monitorado, pare o timer:
   `sudo systemctl stop deepops-deploy.timer`.
2. Faça backup validável do PostgreSQL e preserve separadamente chaves de criptografia,
   inclusive `NUVEMIQ_OCI_CREDENTIALS_KEY` e sua versão.
3. Atualize o checkout e reinstale o controlador caso o próprio
   `scripts/auto_deploy.py` tenha mudado.
4. Execute `./scripts/deploy.sh /opt/finops-analytics`. O script constrói as imagens
   antes da indisponibilidade, para `worker` e `api`, sobe a API/migrations primeiro
   e só retoma worker/web/proxy depois que banco e API estiverem saudáveis.
5. Execute os smoke tests operacionais. Não volte apenas as imagens se a migration já
   foi aplicada. Em falha incompatível, restaure um backup de banco consistente com a
   revisão anterior.
6. Com a nova stack saudável e o checkout no mesmo commit, execute
   `sudo deepops-deploy adopt` para rebaselinar imagens/configuração e limpar o
   bloqueio daquele commit.
7. Retome o timer com `sudo systemctl start deepops-deploy.timer`.

Na primeira implantação da proteção introduzida pela Etapa 21, pare o timer **antes
do merge/publicação** dessa release. Um controlador antigo instalado em
`/usr/local/sbin/deepops-deploy` ainda não conhece o bloqueio de migrations.
