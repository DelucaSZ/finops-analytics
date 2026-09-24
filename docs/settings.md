# Configurações — etapa 4

O menu **Configurações** reúne:

| Área | Acesso | Funções |
| --- | --- | --- |
| Minha segurança | Todos | Senha, confirmação de identidade, TOTP e códigos de recuperação |
| Sessões | Todos | Consultar e encerrar sessões da própria conta |
| Usuários | Administradores | Criar, convidar, editar, desativar/reativar, perfis, recuperação e sessões |
| Auditoria | Administradores | Histórico de acessos, MFA e alterações administrativas |

O endereço antigo `/security` redireciona para `/settings/security`. As permissões
são verificadas no backend, além da navegação: conhecer a URL não concede acesso.
Contas com cadastro MFA obrigatório pendente continuam restritas a `/mfa-setup`.
HTTPS/certificados serão tratados na etapa 5.

## Gestão de usuários

- Prefira **Convidar usuário**: nome, e-mail e perfil geram um link de 24 horas para
  o titular definir sua senha. **Criar com senha** permite cadastro direto com pelo
  menos 12 caracteres. Perfis: administrador, operador e visualizador.
- A lista possui busca por nome/e-mail, filtro de situação, paginação de 50 contas
  e status de MFA. Convites pendentes não contam como administradores ativos.
- **Editar** permite nome, e-mail e perfil. Alterar e-mail/perfil encerra sessões e
  invalida links antigos. A alteração da própria conta encaminha ao login quando
  necessário. O backend impede remover o último administrador ativo com senha.
- **Desativar** encerra o acesso e preserva o histórico; **Reativar** não revive
  sessões antigas. Para convite invalidado, use **Renovar convite**.
- **Recuperar senha** gera link de 30 minutos e preserva MFA. **Renovar convite**
  invalida o convite anterior. O link fica apenas na memória da página, pode ser
  copiado e ocultado; compartilhe somente em canal privado. Não há envio automático
  de e-mail nessa tela. O SMTP do fluxo Esqueci minha senha permanece como antes.
- Alterações sensíveis exigem confirmação recente. Se solicitada, preencha o bloco
  **Confirmar identidade** com sua senha e segundo fator quando ativo; em seguida
  repita a ação. Dados de formulário são preservados durante essa confirmação.
- **Recuperar MFA** exige que o administrador tenha MFA e informe sua própria senha,
  segundo fator e motivo/chamado. Revoga acessos do titular e exige novo cadastro.
  Não é permitido recuperar a própria conta por essa ação; consulte `mfa-totp.md`.
- **Sessões** em cada usuário mostra navegador, início, última atividade e expiração.
  O administrador pode encerrar uma sessão ou todas. Encerrar a própria sessão
  administrativa também exige entrar novamente.

## Auditoria

A listagem possui categoria, filtro de conta e paginação, com responsável, titular,
data e motivo/campos alterados. Nomes e e-mails são os **atuais** do cadastro; IDs
persistem e mudanças de cadastro não reescrevem os eventos. Não há edição ou exclusão
pela API. Essa trilha no banco não é um armazenamento inviolável contra o operador
do banco; retenção/exportação externa não faz parte desta etapa.

Eventos administrativos são gravados na mesma transação da alteração: falhas de
validação/conflito não produzem um evento de sucesso. Não são persistidos senhas,
links, tokens, segredos ou códigos MFA. Motivos de recuperação são texto informado
pelo administrador, que não deve incluir credenciais.

Esta etapa acrescenta eventos de login com senha, tentativas recusadas para contas
conhecidas, logout, revogação de sessão, reautenticação, alteração/redefinição de
senha, aceite/emissão/renovação de convite e alterações administrativas. Eventos MFA
da etapa 3 já existentes também aparecem. Não se reconstrói histórico anterior à
implementação. Tentativas com e-mail inexistente não criam uma identidade fictícia
na auditoria; continuam submetidas à limitação de tentativas persistida.

## API e implantação

- `GET /api/v1/users`: campos públicos de cadastro + `mfa_enabled` e
  `mfa_reset_required`; filtros `q`, `state=active|inactive|pending`, `limit`, `offset`.
- `GET /api/v1/users/{id}/sessions`: sessões válidas do usuário, sem tokens/hashes.
- `DELETE /api/v1/users/{id}/sessions/{session_id}`: revogação individual com
  reautenticação, validação do titular e auditoria. Revogação global já existente.
- `GET /api/v1/audit`: apenas admin; `category=auth|user|mfa`, `user_id`, `limit`,
  `offset`; resposta `{items, total}`, com `Cache-Control: no-store`.

Sem nova migração de schema: reutiliza `security_events` da etapa 3. Atualize API e
web juntos pelo fluxo normal de deploy. Credenciais, volumes e configuração de
certificados não são alterados. A instância EC2 não foi acessada nesta entrega.

Testes cobrem isolamento por perfil, paginação/filtros, integridade da auditoria,
proteção de dados sensíveis, reautenticação e revogação de sessão do titular correto,
além da suíte anterior de MFA, sessões, usuários e migrações.
