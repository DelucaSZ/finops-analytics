# HTTPS e certificados

A etapa 5 adiciona gerenciamento de HTTPS ao DeepOps sem conceder ao backend acesso
ao Docker ou a um shell no host. A aplicação conversa somente com a API
administrativa do Caddy na rede interna do Compose; a porta administrativa não é
publicada no host.

## Modos disponíveis

### Certificado automático

Em Configurações > HTTPS, selecione Certificado automático, informe o domínio DNS e
valide/aplique. O Caddy realiza emissão e renovação ACME automaticamente.

Antes de aplicar:

- o domínio deve apontar para o host do DeepOps;
- o Caddy precisa conseguir concluir o desafio ACME aplicável;
- as portas públicas 80/443 precisam chegar ao Caddy quando o emissor exigir;
- não use URL, porta, wildcard ou endereço IP no campo de domínio.

A abertura do Security Group, revisão de firewall e validação da exposição externa
continuam na etapa 6. Se a emissão não puder ser concluída nesta etapa, a tentativa
falha e o HTTP anterior permanece ativo.

O volume caddy_data permanece persistente entre deploys e é onde o Caddy guarda o
material ACME que administra. O status da tela faz um novo handshake TLS; assim, uma
renovação posterior aparece com a nova validade/fingerprint sem exigir que a chave
privada passe pelo DeepOps.

### Certificado próprio

Selecione Certificado próprio e cole o certificado do domínio, as intermediárias na
sequência e a chave privada correspondente.

Antes de tocar no Caddy, o backend valida formato PEM, limites de tamanho, validade,
presença do domínio no SAN e correspondência criptográfica entre certificado e chave.

Depois do carregamento, o DeepOps abre uma conexão TLS real com o proxy usando SNI e
a trust store do sistema. Isso também valida hostname e cadeia de confiança. Somente
após esse handshake a nova configuração é persistida.

Certificados próprios não são renovados automaticamente pelo DeepOps. Para rotacionar,
aplique o novo conjunto pela mesma tela antes do vencimento.

## Proteção da chave privada

A chave privada entra apenas no corpo da requisição autenticada, é representada como
SecretStr no endpoint, nunca é devolvida pela API ou gravada no banco e não é
incluída em mensagens de erro. No host ela é escrita com permissão 0600 dentro do
volume caddy_config e é removida do formulário após aplicação bem-sucedida.

Proteja backups e snapshots dos volumes caddy_config e caddy_data, pois eles contêm
material TLS. Não copie esses arquivos para o repositório Git.

## Aplicação e rollback

O fluxo de aplicação é transacional:

1. o DeepOps monta a configuração candidata;
2. para certificado próprio, grava o material em diretório candidato protegido;
3. envia somente o Caddyfile para POST /load da API interna do Caddy;
4. se o Caddy não conseguir provisionar a configuração, a anterior continua ativa;
5. o DeepOps faz um handshake HTTPS real contra o domínio configurado;
6. se o handshake falhar, a configuração anterior é recarregada e os arquivos
   candidatos são descartados;
7. somente após sucesso o Caddyfile gerenciado vira a configuração persistente.

O Caddy usa persist_config off: o arquivo gerenciado pelo DeepOps é a fonte de
verdade após reinício. Se esse arquivo ainda não existir, o container inicia com
proxy/Caddyfile, que mantém o HTTP atual.

A configuração gerenciada também mantém http://proxy para probes internos do Compose.
Isso preserva health check e auto-deploy quando o domínio público responde em HTTPS.

## API administrativa

Todos os endpoints são exclusivos para administradores:

- GET /api/v1/tls consulta o modo salvo e verifica o certificado servido agora;
- POST /api/v1/tls/validate valida domínio e certificado/chave no modo próprio;
- POST /api/v1/tls/apply exige reautenticação recente e executa aplicação, handshake
  e persistência.

A API do Caddy escuta 2019 apenas na rede Docker e exige o Origin esperado do
container da API. Não há bind de 2019 no host, montagem de docker.sock ou execução
de comando fornecido pelo usuário.

## Operação

Depois de aplicar, valide também a partir de um cliente externo com uma requisição
HTTPS ao domínio e ao caminho /health.

O teste externo completo, endurecimento do Security Group e liberação definitiva da
aplicação fazem parte da etapa 6.
