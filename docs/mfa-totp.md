# MFA TOTP — etapa 3

## Uso

1. Abra **Minha segurança → Autenticação em duas etapas** e confirme sua senha.
2. Escaneie o QR code com Google Authenticator, Microsoft Authenticator ou outro
   aplicativo TOTP. Também é possível cadastrar a chave manualmente (SHA-1,
   seis dígitos, intervalo de 30 segundos, emissor DeepOps).
3. Confirme com um código do novo autenticador em até dez minutos. Só então o MFA
   fica ativo. As outras sessões e links de acesso anteriores são invalidados.
4. Guarde os dez códigos de recuperação exibidos uma única vez. Cada código
   substitui o segundo fator uma vez, mas nunca substitui a senha.
5. Nos próximos logins, informe senha e depois TOTP ou código de recuperação.
   O código usado na ativação não pode ser reutilizado: aguarde o próximo.

Trocar o autenticador e gerar novos códigos exigem senha + segundo fator.
Na troca, o autenticador anterior continua funcionando até a confirmação do novo.
A troca invalida todos os códigos de recuperação anteriores e encerra as outras
sessões. Redefinir ou alterar a senha **não desativa MFA**. Reautenticação e troca
voluntária de senha também exigem o segundo fator quando cadastrado.

## Política de obrigatoriedade

`NUVEMIQ_MFA_REQUIRED=false` mantém a adoção gradual em ambiente privado. Uma vez
ativado em uma conta, o segundo fator é sempre exigido, independentemente dessa
variável. Não há endpoint para desativação voluntária.

Configure `NUVEMIQ_MFA_REQUIRED=true` antes de liberar acesso externo. Contas novas,
antigas e convites aceitos sem MFA ficam restritos ao cadastro do autenticador e
logout. A restrição é aplicada no backend a todas as rotas de negócio, inclusive
para sessões já existentes; o frontend encaminha para `/mfa-setup`.

A configuração vale para admin, operator e viewer. HTTPS continua sendo requisito
separado para liberação externa (etapas seguintes). Mantenha o relógio do servidor
e do celular sincronizados por NTP/horário automático.

## Criptografia e chaves

O banco guarda o segredo TOTP criptografado com Fernet (criptografia autenticada).
Os códigos de recuperação têm 128 bits de aleatoriedade e são armazenados apenas
como SHA-256 vinculado ao usuário. QR codes são gerados na própria API; nenhuma
chave é enviada a serviços externos. Respostas de autenticação usam `no-store`.

Por padrão a chave Fernet é derivada de `NUVEMIQ_SECRET_KEY` com HKDF-SHA256 e
contexto exclusivo para TOTP. Essa variável deve ter pelo menos 32 caracteres
aleatórios; valores padrão/exemplos conhecidos não permitem ativar MFA.
**Não altere esse segredo após cadastrar autenticadores** sem um procedimento de
migração: isso impediria a descriptografia dos segredos existentes.

Opcionalmente, antes do primeiro cadastro, use uma chave independente em
`NUVEMIQ_MFA_ENCRYPTION_KEY`. Gere-a em um terminal privado com:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Guarde a chave em segredo no `.env` do host (não no Git) e mantenha backup separado
do banco. Ativar a chave dedicada depois de já usar a derivação também exige
migração/reconfiguração dos autenticadores; não há rotação automática nesta etapa.
Falha de descriptografia retorna erro e nunca permite login somente com senha.

O Compose já injeta o `.env` em API/worker. Com o auto deploy, alterações no `.env`
original são copiadas para a próxima release, conforme `docs/auto-deploy.md`.

## Recuperação administrativa

Valide a identidade do titular por um canal confiável antes de redefinir MFA.
Não peça segredo TOTP nem códigos de recuperação por mensagens.

Um admin com MFA ativo pode usar `POST /api/v1/auth/mfa/reset/{user_id}`, com cookie,
CSRF e corpo `{ "password": "...", "code": "...", "reason": "motivo/ticket" }`.
A senha e o segundo fator são do administrador; o motivo deve ter 10–500 caracteres.
A tela administrativa completa será entregue na etapa 4. Admin sem MFA, usuários
não administradores e reset da própria conta por essa rota são rejeitados.

Se o único administrador perder o autenticador **e** todos os códigos de recuperação,
o operador autorizado do host pode executar no container API ativo:

```bash
docker exec -it <container-api-ativo> python -m app.manage mfa-reset \
  --email admin@exemplo.com --reason 'Identidade validada no chamado interno 12345'
```

O reset remove o segredo/códigos antigos, invalida desafios e sessões, grava auditoria
com titular, ator, data e motivo, e exige novo cadastro no próximo login, mesmo se
`NUVEMIQ_MFA_REQUIRED=false`. A senha permanece. Não concede uma sessão completa ao
administrador nem ao titular. Na recuperação pelo host, `actor_id` nulo identifica
operação do host; o motivo deve identificar o chamado/operador sem incluir segredos.

## Implementação e auditoria

- Login com MFA entrega desafio opaco (somente hash no banco), válido por cinco
  minutos, vinculado ao usuário e à versão das credenciais. Somente o desafio mais
  recente pode ser concluído. A sessão completa só nasce após validar o segundo fator.
- Máximo de cinco tentativas por desafio, com limitação persistida por identidade
  e peer. Trocas de senha, desativação e mudanças de perfil invalidam desafios.
- TOTP aceita janela de ±30 segundos, rejeita passos já consumidos e relógio anterior
  ao último passo. O consumo de TOTP, recuperação e desafio é serializado na mesma
  transação com lock no banco, inclusive entre múltiplos processos da API.
- Configuração pendente vincula segredo criptografado à sessão e expira em dez
  minutos; é ativada somente com prova do novo segredo. Ativação gira a sessão.
- Eventos de configuração, ativação, login MFA, falha, recuperação, regeneração e
  reset ficam em `security_events`, sem código, senha, QR ou segredo.
  `GET /api/v1/auth/mfa/events` retorna os últimos 50 eventos da própria conta.
- Limitações de peer atrás do proxy seguem a etapa 2: não confiar automaticamente
  em headers forwarded enviados pelo cliente. MFA TOTP não oferece resistência a
  phishing equivalente a passkeys/WebAuthn; passkeys não fazem parte desta etapa.

## Deploy e rollback

A migração `0004_totp` adiciona tabelas MFA/auditoria e o marcador `mfa_verified`
às sessões. Não remove dados. Atualize API, worker e web juntos. API aplica a migração
antes de servir; worker aguarda. Sessões de contas ainda sem MFA continuam válidas,
sujeitas à política de obrigatoriedade.

Para que uma falha na primeira implantação permita restaurar a imagem anterior,
`deepops_schema_version` fica no checkpoint `0003_auth_lifecycle`; as revisões desta
etapa são acompanhadas por `deepops_mfa_schema_version`. `alembic_version` continua
no checkpoint legado da etapa 1. Não fazer downgrade das tabelas MFA.

**Depois de cadastrar MFA, não volte a imagens das etapas 1/2:** elas desconhecem o
segundo fator e restauram login só com senha. Conclua a estabilização da release
antes de cadastrar autenticadores. Para rollback posterior, use uma release que
já implemente MFA. A compatibilidade de schema não preserva segurança de código antigo.

Validação automatizada cobre SQLite e PostgreSQL no CI: migração, restrição por
política, QR/chave, troca de autenticador, recuperação, falhas de chave, replay,
expiração e consumo concorrente de provas. A EC2 não é acessada por esta entrega.
