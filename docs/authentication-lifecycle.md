# Autenticação — etapa 2

A etapa 2 troca o JWT no navegador por sessões revogáveis no servidor e entrega
convites, definição/recuperação de senha e gestão dos próprios acessos.

## Comportamento e páginas

- `/login`: cria sessão por cookie HttpOnly; nenhum token de sessão é retornado no
  JSON ou guardado em localStorage. O token antigo é removido do navegador.
- `/forgot-password`: solicitação de recuperação com resposta genérica, inclusive
  para conta inexistente, inativa, sem SMTP ou limitada por excesso de tentativas.
- `/accept-invitation#token=...`: define a senha e ativa o acesso de um convidado.
- `/reset-password#token=...`: troca a senha após validar o link recebido.
- `/security` (Minha segurança): altera senha, confirma identidade, lista sessões
  próprias e permite encerrar uma sessão ou todas. Erros de logout são apresentados;
  sair invalida a sessão no servidor, não apenas no navegador.

Convites duram 24 horas; links de recuperação duram 30 minutos. São aleatórios,
armazenados como hash, vinculados ao usuário e à versão de autenticação, e consumidos
uma única vez em transação. Reemitir um link invalida o anterior do mesmo tipo.
Mudanças de e-mail/perfil/status/senha também invalidam links anteriores.
Definir ou recuperar senha não cria uma sessão automaticamente; o usuário deve entrar.

Links usam fragmento `#token=`: o segredo não é enviado na URL HTTP aos logs do
proxy e a página o remove do histórico atual após leitura. Recarregar essa página
exige reabrir o link recebido. Nunca publique ou registre o link completo.

## Sessões e requisições

- Cookie `deepops_session`, HttpOnly, SameSite=Lax, Path=/, sem Domain.
- `Secure` é automático em `NUVEMIQ_ENVIRONMENT=production`. Produção rejeita
  `NUVEMIQ_COOKIE_SECURE=false`. O ambiente de desenvolvimento permanece compatível
  com o HTTP privado atual; HTTPS/abertura externa seguem nas etapas 5/6.
- Duração absoluta: `NUVEMIQ_ACCESS_TOKEN_MINUTES` (nome mantido, padrão 480 minutos).
- Inatividade: `NUVEMIQ_SESSION_IDLE_MINUTES` (padrão 30 minutos).
- O banco guarda apenas hash do identificador aleatório da sessão. Conta inativa,
  versão de autenticação alterada, sessão revogada ou prazo vencido bloqueiam acesso.
- Logout de todos/revogação administrativa não bloqueiam logins futuros. Troca de
  senha encerra todos os acessos e exige a nova senha no próximo login.
- JWT/Bearer da etapa 1 deixa de ser aceito. API e frontend devem ser atualizados juntos.

Clientes da API precisam preservar cookies. Todos os POST/PATCH/PUT/DELETE exigem
`X-DeepOps-Request: 1`. Nas rotas autenticadas, consulte `GET /api/v1/auth/csrf` com
o cookie e envie `X-CSRF-Token` nas alterações. O valor é vinculado à sessão;
CORS não deve aceitar origens de terceiros. O frontend faz isso automaticamente.

Login, recuperação e conclusão de link possuem limitação persistente no banco;
troca/confirmação de senha também. Login: 10 tentativas por identidade/15 minutos,
com limite adicional de 60 por peer. Recuperação: 3 solicitações por identidade/15
minutos e 18 por peer. Os headers de IP encaminhado não são confiados automaticamente:
atrás do proxy atual, o limite por peer pode ser compartilhado pelos usuários. Ajustar
confiança de proxy e limites conforme o tráfego antes da exposição externa.

## Administração (API; tela administrativa na etapa 4)

Permissão admin e senha confirmada nos últimos cinco minutos são necessárias para
alterar usuários, emitir links ou revogar sessões de outra pessoa. Um login recente
já satisfaz essa confirmação; depois, usar Minha segurança ou `/auth/reauthenticate`.

| Rota (prefixo `/api/v1`) | Uso |
| --- | --- |
| `POST /users/invitations` | `{name, email, role}`; cria usuário pendente e retorna link uma vez |
| `POST /users/{id}/invitation` | Reemite convite de usuário pendente |
| `POST /users/{id}/password-reset` | Gera link para usuário ativo com senha |
| `DELETE /users/{id}/sessions` | Revoga sessões do usuário |
| `POST /auth/reauthenticate` | `{password}`; confirma identidade por cinco minutos |
| `POST /auth/change-password` | `{current_password, new_password}`; troca e encerra acessos |
| `GET /auth/sessions` | Lista acessos próprios ainda válidos |
| `DELETE /auth/sessions/{id}` | Encerra uma sessão própria |
| `POST /auth/logout` | Encerra a sessão atual |
| `POST /auth/logout-all` | Encerra todas as sessões próprias |
| `POST /auth/forgot-password` | `{email}`; solicitação pública de recuperação |
| `POST /auth/reset-password` | `{token, password}`; consome link de recuperação |
| `POST /auth/accept-invitation` | `{token, password}`; consome convite |

Criação direta com senha pela API da etapa 1 foi preservada, agora exigindo confirmação
recente. Convites permitem que o próprio usuário escolha a senha. Um convite pendente
com perfil admin não conta como administrador disponível para a proteção do último admin.

O administrador entrega convites/links manuais por canal privado. Defina
`NUVEMIQ_PUBLIC_URL=https://deepops.seudominio.com.br` para links absolutos. Sem essa
configuração, a API retorna caminhos relativos, que devem ser anexados ao endereço
real da aplicação; nunca usa o header Host para formar links enviados por e-mail.

## Recuperação por e-mail (opcional)

Defina `NUVEMIQ_PUBLIC_URL`, `NUVEMIQ_SMTP_HOST`, `NUVEMIQ_SMTP_PORT`,
`NUVEMIQ_SMTP_FROM` e, se necessário, `NUVEMIQ_SMTP_USERNAME` e `NUVEMIQ_SMTP_PASSWORD`.
A conexão exige STARTTLS; para TLS implícito, configure `NUVEMIQ_SMTP_SSL=true` e a
porta correspondente. Credenciais permanecem no ambiente, fora do Git.

O pedido público responde antes da consulta/envio em background. Não informa se
houve envio. Falhas de SMTP são registradas sem endereço, token ou credenciais;
o usuário pode solicitar novamente ou contatar o administrador. O envio em background
não é uma fila durável: um restart no momento do envio pode exigir nova solicitação.

Sem SMTP, recuperação administrativa continua disponível. Para a perda da senha do
único administrador, um operador autorizado com acesso privilegiado ao host pode gerar
um link para a conta existente, sem criar outra conta nem reativar contas desabilitadas:

```bash
docker compose exec api python -m app.manage password-reset --email admin@empresa.com.br
```

Se usa releases isoladas do auto deploy, execute o mesmo módulo no container `api`
ativo do projeto `nuvemiq` (o checkout pode apontar para outra release). O link exibido
é um segredo de recuperação. Somente operadores com acesso autorizado ao host/banco
podem executar esse procedimento; ele não é um endpoint público.

## Migração e rollback

A revisão `0003_auth_lifecycle` adiciona sessões, tokens de uso único, limites de
requisições e o campo `password_set`, preenchido como verdadeiro para contas existentes.
Os logins existentes continuam válidos, mas precisam de nova autenticação no navegador.

A etapa 1 falharia ao encontrar uma revisão Alembic desconhecida. Por isso, esta
versão preserva `alembic_version=0002_users` como checkpoint de compatibilidade e
passa a controlar novas revisões em `deepops_schema_version`. A migração/adoção é
atômica com o mesmo lock do banco. Não altere essas tabelas manualmente.

O rollback para a etapa 1 mantém os dados e consegue iniciar pelo checkpoint antigo,
mas restaura o login JWT dessa versão e suas limitações. Ao retornar à etapa 2, os
registros novos são preservados. Não execute downgrade destrutivo de schema. Futuras
migrações devem revisar compatibilidade antes de confiar em rollback de imagem.

MFA/TOTP não está habilitado nesta etapa. Telas administrativas completas, auditoria,
HTTPS e liberação externa continuam nas etapas seguintes.
