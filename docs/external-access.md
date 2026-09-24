# Liberação externa segura

A etapa 6 fecha o ciclo iniciado em usuários, sessões, MFA e HTTPS. O objetivo é
publicar somente o Caddy em 80/443 e manter API, worker, frontend interno,
PostgreSQL e API administrativa do Caddy inacessíveis diretamente pela internet.

## Pré-requisitos obrigatórios

Antes de alterar o Security Group:

1. aplique HTTPS em **Configurações > HTTPS** e confirme o certificado;
2. use um DNS estável apontando para a EC2, preferencialmente com Elastic IP;
3. mantenha `.env` fora do Git e faça backup de `NUVEMIQ_SECRET_KEY` e da chave
   de MFA dedicada, quando usada;
4. configure no host:

```dotenv
NUVEMIQ_ENVIRONMENT=production
NUVEMIQ_PUBLIC_URL=https://deepops.seudominio.com
NUVEMIQ_CORS_ORIGINS=https://deepops.seudominio.com
NUVEMIQ_COOKIE_SECURE=true
NUVEMIQ_MFA_REQUIRED=true
NUVEMIQ_DEMO_MODE=false
NEXT_PUBLIC_API_URL=/api/v1
```

O domínio acima é exemplo. Não copie literalmente.

Depois de mudar o ambiente, recrie API, worker e web. A alteração para production
faz o cookie de sessão exigir HTTPS.

## Security Group

O repositório contém
`infrastructure/cloudformation/deepops-public-security-group.yaml`.

O SG criado permite somente:

| Porta | Protocolo | Origem | Finalidade |
| --- | --- | --- | --- |
| 80 | TCP | CIDR configurado | redirect HTTPS e desafio ACME |
| 443 | TCP | CIDR configurado | aplicação DeepOps |

Não há regra para 22, 2019, 3000, 5432 ou 8000. Use Session Manager em vez de SSH
público. Se SSH for indispensável, use outro SG com CIDR administrativo específico,
nunca `0.0.0.0/0`.

**Atenção:** regras de todos os Security Groups anexados a uma EC2 são somadas.
Anexar o SG novo não neutraliza um SG antigo permissivo. Revise e remova/restrinja
qualquer regra antiga que publique portas internas.

Exemplo de criação por CloudFormation:

```bash
aws cloudformation deploy \
  --stack-name deepops-public-sg \
  --template-file infrastructure/cloudformation/deepops-public-security-group.yaml \
  --parameter-overrides VpcId=vpc-xxxxxxxx AllowedIPv4=0.0.0.0/0
```

Para uma aplicação restrita a rede corporativa/VPN, substitua `AllowedIPv4` pelo
CIDR correspondente. IPv6 fica desligado por padrão; só habilite se a EC2 e o DNS
usarem IPv6 e o caminho estiver deliberadamente publicado.

## IMDS e credenciais AWS

A EC2 central deve continuar usando Instance Profile, sem Access Key permanente.
Exija IMDSv2. Como API/worker rodam em Docker bridge e precisam obter credenciais
do Instance Profile, valide o hop limit do metadata para o cenário de containers;
em hosts Docker normalmente é necessário valor 2. Não aumente além do necessário e
não execute workloads não confiáveis no mesmo host.

## Host e Docker

O Compose publica somente 80/443 no serviço `proxy`. API (8000), web (3000),
PostgreSQL (5432) e admin do Caddy (2019) permanecem apenas na rede Docker.

Confirme no host:

```bash
docker compose ps
sudo ss -lntp
```

Não deve existir bind público da aplicação em 2019, 3000, 5432 ou 8000.

O Security Group é o controle de borda principal. Se usar UFW/nftables, considere
que regras de publicação do Docker interagem diretamente com iptables/nftables;
não assuma que uma regra UFW bloqueia um `ports:` publicado pelo Docker.

## Verificador local de prontidão

Após configurar o `.env`, HTTPS e containers:

```bash
python3 scripts/check-external-readiness.py --repo /opt/finops-analytics
```

O verificador exige:

- modo `production`;
- URL pública HTTPS sem caminho;
- cookies seguros;
- MFA obrigatório;
- demo desligado;
- CORS limitado à própria origem pública;
- somente 80/443 publicados pelo Compose;
- configuração TLS persistida;
- handshake TLS confiável com SNI;
- `/health` em HTTPS;
- HSTS e `X-Content-Type-Options`.

Ele não altera firewall, DNS ou Security Group.

## Validação externa

A última validação precisa partir de outra rede/host, não da própria EC2:

```bash
curl -fsS -D - https://deepops.seudominio.com/health
```

Esperado: HTTP 200, JSON com `"status":"ok"`, HSTS e certificado válido.

Também teste que as portas internas não estão disponíveis externamente:

```bash
for port in 2019 3000 5432 8000; do
  nc -zvw3 deepops.seudominio.com "$port" && echo "ERRO: $port acessível"
done
```

O resultado esperado é falha de conexão/timeout em todas elas.

## Cabeçalhos aplicados pelo proxy

O endpoint HTTPS gerenciado aplica:

- `Strict-Transport-Security: max-age=31536000`;
- `X-Content-Type-Options: nosniff`;
- `X-Frame-Options: DENY`;
- `Referrer-Policy: no-referrer`;
- `Permissions-Policy` bloqueando câmera, microfone e geolocalização;
- CSP mínima com `frame-ancestors 'none'`, `base-uri 'self'` e `object-src 'none'`;
- remoção do cabeçalho `Server`.

HSTS é enviado somente no endpoint HTTPS. Não foi usado `includeSubDomains` para
não impor HTTPS a subdomínios que não pertencem ao DeepOps.

## Critério de conclusão

Considere a etapa concluída no ambiente somente quando:

1. o verificador local passar;
2. o SG final não tiver regras públicas além de 80/443;
3. todos os SGs anexados forem revisados;
4. o teste HTTPS externo retornar 200 e certificado válido;
5. 2019/3000/5432/8000 falharem externamente;
6. login exigir MFA e o cookie de sessão estiver marcado Secure.
