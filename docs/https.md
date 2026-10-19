# HTTPS / TLS

O DeepOps gerencia HTTPS pelo Caddy sem expor a Admin API do Caddy para fora da rede interna do Compose. A configuração pode usar certificado automático (ACME) ou material TLS fornecido pelo administrador.

## Modos disponíveis

### Automático (Caddy / ACME)

O administrador informa apenas o domínio público. O Caddy solicita, renova e persiste o certificado no volume próprio. Para funcionar, o domínio precisa resolver para o host correto e os desafios ACME precisam alcançar as portas públicas 80/443.

### Certificado próprio

O material é informado em três campos independentes:

1. **Certificado do servidor (leaf)** — o certificado emitido para o domínio, normalmente exatamente um bloco PEM.
2. **Cadeia intermediária / CA Bundle** — zero ou mais CAs intermediárias necessárias para ligar o leaf à autoridade raiz.
3. **Chave privada** — a chave correspondente ao leaf, sem senha.

O contrato padrão da API é equivalente a:

```json
{
  "mode": "custom",
  "domain": "deepops.exemplo.com",
  "server_certificate": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
  "intermediate_chain": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
}
```

O campo legado `certificate_chain` é aceito apenas como compatibilidade transitória. O frontend usa o novo contrato.

## Certificado, intermediária, Root CA, chave e fullchain

Um certificado TLS custom normalmente é entregue pelo fornecedor em arquivos separados:

`server.crt`

```text
-----BEGIN CERTIFICATE-----
[certificado do domínio]
-----END CERTIFICATE-----
```

`intermediate.pem`

```text
-----BEGIN CERTIFICATE-----
[CA intermediária]
-----END CERTIFICATE-----
```

`private.key`

```text
-----BEGIN PRIVATE KEY-----
[chave privada]
-----END PRIVATE KEY-----
```

O **Root CA** é a raiz da cadeia de confiança. Em certificados públicos, essa raiz já está presente na trust store do sistema operacional/navegador e normalmente **não deve ser enviada pelo servidor**.

O DeepOps não concatena cegamente o conteúdo recebido. No modo custom ele valida a relação criptográfica da cadeia, ordena as intermediárias e constrói internamente:

```text
fullchain.pem =
  certificado leaf
  + intermediária 1
  + intermediária 2
  + ...
```

Se um Root CA self-signed for incluído no CA Bundle e pertencer à cadeia, ele é identificado para diagnóstico, mas omitido do `fullchain.pem` servido ao cliente.

## Validações antes da aplicação

Para o certificado leaf, o backend verifica:

- PEM válido e exatamente um certificado no campo do servidor;
- período de validade (não expirado e já válido);
- presença do domínio informado no SAN, incluindo wildcard compatível quando aplicável;
- correspondência entre a public key do certificado e a private key;
- chave privada PEM sem senha;
- Extended Key Usage para TLS servidor quando a extensão estiver presente.

Para as intermediárias, verifica:

- todos os blocos PEM;
- validade temporal;
- `BasicConstraints CA=true`;
- certificados duplicados;
- relações `issuer -> subject`;
- assinatura criptográfica entre leaf/intermediária e entre intermediárias consecutivas;
- cadeia quebrada, ambígua ou com certificados sem relação;
- Root CA self-signed incluído no bundle.

Intermediárias fora de ordem são reorganizadas somente quando a relação criptográfica permite determinar uma cadeia única.

Uma cadeia estruturalmente consistente pode terminar sem uma raiz presente na trust store deste host. Nesse caso o diagnóstico informa que ela está **não ancorada**. Isso pode significar uma CA privada legítima ou uma cadeia pública incompleta; o estado de confiança do handshake local ajuda a diferenciar o cenário operacional.

## CA pública x CA privada

### CA pública

Quando a cadeia termina em uma raiz presente na trust store padrão, o DeepOps informa `PUBLIC_TRUSTED` e o handshake com verificação padrão deve ser confiável.

### CA privada / corporativa

O Caddy pode apresentar corretamente o leaf e suas intermediárias e, ainda assim, navegadores exibirem alerta caso o Root CA corporativo não esteja instalado nas máquinas clientes.

Nesse cenário, o DeepOps não declara o HTTPS como publicamente confiável. O estado informa que a CA é privada/não pública ou que a cadeia não é confiável pela trust store local. O DeepOps **não instala CAs privadas automaticamente** no host nem nos clientes.

## Caddyfile gerenciado

Para um domínio configurado, o Caddyfile gerenciado mantém a rota interna usada pelos containers e torna o redirect público explícito:

```caddyfile
http://proxy {
    # rotas internas
}

http://deepops.exemplo.com {
    redir https://deepops.exemplo.com{uri} 308
}

https://deepops.exemplo.com {
    tls /config/deepops/certs/.../fullchain.pem /config/deepops/certs/.../private-key.pem
    # API, /health e frontend
}
```

No modo automático, a diretiva `tls` com caminhos não é adicionada e o Caddy mantém o ciclo ACME.

A Admin API do Caddy continua disponível apenas na rede interna do Compose. A porta administrativa não é publicada pelo host.

## Aplicação transacional e rollback

A aplicação custom segue esta ordem:

1. validar domínio, leaf, intermediárias e private key;
2. construir o fullchain ordenado;
3. gravar arquivos candidatos em diretório privado;
4. gerar e carregar o Caddyfile candidato;
5. executar o probe TLS local contra o Caddy;
6. se o probe local falhar, restaurar a configuração anterior e remover os arquivos candidatos;
7. após sucesso local, persistir Caddyfile e estado TLS;
8. executar o diagnóstico DNS/endpoints publicados.

Diretórios de material TLS usam permissão `0700` e arquivos sensíveis usam `0600`.

Falha ou timeout ao alcançar o próprio IP público a partir da EC2 **não desfaz** uma configuração que passou no probe local. Isso é importante em redes onde hairpin/NAT loopback não é suportado.

Se um endpoint DNS acessível apresentar outro fingerprint, a configuração local permanece aplicada, mas o estado de publicação é `MISMATCH`.

## Estado e diagnóstico

A tela **Configurações > HTTPS** separa quatro dimensões:

- **configuração salva** — modo e domínio persistidos;
- **TLS local** — o certificado que o Caddy local apresenta para o SNI configurado;
- **DNS público** — registros A e AAAA resolvidos pelo host;
- **endpoint publicado** — o certificado observado ao conectar diretamente em cada IP resolvido usando o domínio como SNI.

O status inclui, quando disponível:

- emissor;
- início/fim da validade;
- fingerprint SHA-256;
- SANs;
- quantidade de certificados do fullchain custom;
- registros A e AAAA;
- resultado de cada endpoint;
- confiança pela trust store;
- data da última validação.

Estados de publicação:

- `VERIFIED` — endpoints testados apresentam o mesmo certificado esperado;
- `PARTIAL` — parte foi verificada e parte não pôde ser confirmada;
- `MISMATCH` — ao menos um endpoint acessível apresentou certificado/hostname divergente;
- `UNREACHABLE` — os IPs resolvidos não puderam ser alcançados a partir deste host;
- `DNS_NOT_FOUND` — não foram encontrados registros A/AAAA.

`VERIFIED` confirma a correspondência do certificado publicado com o aplicado. A confiança pública da CA continua sendo apresentada separadamente; uma CA privada pode ter fingerprint correto e ainda exigir instalação explícita do Root CA nos clientes.

## Compatibilidade

Estados TLS persistidos em formato anterior continuam legíveis. Caddyfiles custom já persistidos não são reescritos automaticamente no deploy. Uma nova aplicação custom passa a usar o estado versionado e `fullchain.pem` validado.

## Segurança do material TLS

A private key:

- não é persistida no banco;
- não é devolvida pelas APIs;
- não é incluída no `state.json`;
- não deve aparecer em logs ou mensagens de erro;
- é gravada somente no storage persistente protegido usado pelo Caddy.

A aplicação HTTPS continua exigindo autenticação administrativa e reautenticação recente para aplicar alterações.

## Validação externa

O diagnóstico feito pela própria EC2/VPC é útil, mas não é a confirmação definitiva de publicação na Internet. DNS dividido, load balancer, proxy intermediário, NAT/hairpin e diferenças de rota podem fazer a visão interna divergir da visão de um cliente externo.

A confirmação final deve ser executada de uma máquina externa à EC2/VPC:

```bash
curl -vI https://DOMINIO
```

```bash
openssl s_client \
  -connect DOMINIO:443 \
  -servername DOMINIO \
  -showcerts </dev/null
```

Confira também os endereços publicados:

```bash
dig +short A DOMINIO
dig +short AAAA DOMINIO
```

Para múltiplos A/AAAA, valide cada endpoint relevante, sempre usando o hostname correto como SNI, e compare o fingerprint apresentado com o exibido pelo DeepOps.

O script `scripts/check-external-readiness.py` continua validando o host/Compose e o handshake local de readiness. A confirmação definitiva do endpoint público deve ser realizada externamente.
