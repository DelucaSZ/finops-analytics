# Usuários e permissões — etapa 1

Esta entrega implementa a base de autenticação e autorização. O gerenciamento é
feito pela API nesta etapa. A aba Configurações e a adaptação visual dos botões aos
perfis pertencem à etapa 4; o backend já rejeita operações sem permissão com 403.
Não há isolamento por cliente ou conta AWS: os usuários pertencem ao mesmo time.

## Perfis

| Operação | Administrador (`admin`) | Operador (`operator`) | Leitura (`viewer`) |
| --- | --- | --- | --- |
| Consultar dashboards, contas, políticas, execuções e oportunidades | Sim | Sim | Sim |
| Executar varreduras | Sim | Sim | Não |
| Alterar oportunidades individualmente ou em lote | Sim | Sim | Não |
| Solicitar explicação por IA (pode gerar custo) | Sim | Sim | Não |
| Criar, alterar, excluir e testar contas AWS; gerar External ID | Sim | Não | Não |
| Alterar e restaurar políticas | Sim | Não | Não |
| Listar, criar, editar e desativar usuários | Sim | Não | Não |

## Migração e primeiro acesso

1. Mantenha o acesso restrito à rede controlada e tenha um backup recente/restaurável
   do PostgreSQL antes da primeira implantação desta versão.
2. Preserve `NUVEMIQ_ADMIN_EMAIL` e `NUVEMIQ_ADMIN_PASSWORD` do administrador atual.
   Valores de exemplo `change-me` e `replace-this-password` são recusados no bootstrap.
3. Atualize pelo mecanismo de deploy já utilizado (timer, se estiver habilitado).
   A lista de serviços, volumes e configuração do banco no Compose não mudou.
4. A API aplica as revisões `0001_legacy` e `0002_users`, importa o administrador
   e só então passa a aceitar requisições. O worker aguarda a inicialização por até
   120 segundos e, em caso de falha, encerra para que a política de restart atue.
5. Entre novamente com o mesmo e-mail e senha. Os JWTs anteriores são rejeitados.

`0001_legacy` adota as tabelas existentes e cria a base em bancos vazios;
`0002_users` adiciona `users` e `auth_state`. Dados de contas, políticas, execuções
e oportunidades são preservados. Migração e bootstrap compartilham uma transação,
com lock de migração no PostgreSQL/SQLite. Falhas impedem a API de iniciar.

O bootstrap usa uma marca persistente: reiniciar containers ou alterar o `.env`
não redefine senha, perfil, nome ou status do administrador. Não existe fallback
para autenticação pelo `.env`. Não apague `auth_state` para recuperar acesso.

As senhas são armazenadas com Argon2id. E-mails são normalizados para minúsculas
e são únicos; novos usuários recebem `viewer` se o perfil não for informado.
O identificador de autenticação passa a ser o UUID do usuário. Cada requisição
verifica no banco se o usuário está ativo e seu perfil atual.

## API administrativa

Todas as rotas abaixo usam o prefixo `/api/v1`. Autentique-se em `POST /auth/login`
e use `Authorization: Bearer <access_token>`; não grave tokens em repositórios/logs.
O contrato de resposta de login foi preservado para o frontend existente.

| Método e rota | Uso |
| --- | --- |
| `GET /auth/me` | Dados públicos da própria conta autenticada |
| `GET /users?limit=50&offset=0` | Listar usuários, inclusive inativos; máximo de 200 por página |
| `POST /users` | Criar usuário com nome, e-mail, senha inicial e perfil |
| `PATCH /users/{id}` | Alterar nome, e-mail, perfil ou `is_active` |

Exemplo de corpo para criação (substitua a senha antes de usar):

```json
{
  "name": "Nome do usuário",
  "email": "usuario@empresa.com.br",
  "password": "SUBSTITUA-POR-UMA-SENHA-UNICA",
  "role": "operator"
}
```

A senha inicial deve ter 12–128 caracteres. Nesta etapa ela é definida pelo
administrador e entregue por canal privado; convites, troca/recuperação de senha e
fluxos de primeiro acesso serão implementados na etapa 2. Não há envio de e-mail.
Não use a criação de usuários para contornar recuperação de acesso.

Para desativar: `PATCH /users/{id}` com `{"is_active": false}`. Alterações de perfil,
e-mail ou status incrementam a versão de autenticação: tokens existentes deixam
de funcionar, inclusive após reativar a conta. Não há exclusão definitiva nesta
etapa. O último administrador ativo não pode ser desativado ou rebaixado; essa
proteção é serializada no banco, incluindo alterações concorrentes.

Nenhuma resposta de usuário contém hash, senha ou versão de token. Erros de
validação não retornam o conteúdo enviado, evitando eco de senhas inválidas.

## Rollback

As migrações são aditivas: a imagem antiga consegue acessar os dados FinOps e as
novas tabelas permanecem preservadas. O controlador de deploy não executa downgrade
de banco; as revisões recusam downgrade destrutivo.

**Compatibilidade do banco não significa preservar a nova autenticação:** voltar
para uma imagem anterior a esta etapa restaura o login antigo pelo `.env` e remove
os controles de usuários/perfis daquela versão. Mantenha o acesso restrito durante
um rollback e preserve as credenciais antigas no ambiente enquanto essa imagem
for candidata à recuperação. Ao retornar à versão nova, os usuários persistidos
continuam valendo; o bootstrap não é repetido.

Esta etapa não libera a aplicação para a internet: cookies/sessões, convites,
recuperação, MFA, limites de tentativas, auditoria, HTTPS e endurecimento da EC2
continuam nas próximas etapas do plano.

## Validação

```bash
cd backend
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest -q
```

O CI também executa os testes de migração/transação em PostgreSQL 17. Localmente,
defina `TEST_POSTGRES_URL` para um banco **de testes** com permissão de criar schemas;
cada teste cria e remove um schema isolado. Sem a variável, esses casos são
ignorados e a variante SQLite é executada. Há cobertura de migração com dados
existentes, bootstrap único, rollback transacional, perfis, tokens inválidos,
revogação por alteração de conta e proteção concorrente do último administrador.
