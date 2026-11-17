# AWS Pricing — Production Runbook (Fase 28)

**Versão inicial:** 16/11/2026. **Estado:** preparado documentalmente, **não validado em produção**. **Gate:** `NO-GO` até o checklist de [readiness](28.9-production-readiness.md). Público: operadores autorizados e responsáveis por PostgreSQL/AWS/IAM. Toda operação de escrita requer janela, backup, registro de aprovação e ambiente identificado.

## 1. Segurança e pré-flight (somente leitura)

Identificar ambiente e commit, verificar se o Docker responde e se o worker/API estão saudáveis. Não colar segredos ou saída bruta de logs no PR; registrar IDs de execução, horário UTC e versões:

```bash
git rev-parse HEAD
docker compose config --quiet
docker compose ps
docker compose logs --tail=100 api worker
docker compose exec -T api python -m app.commands.aws_pricing_sync --status
docker compose exec -T api python -m app.commands.aws_pricing_sync --coverage --service AmazonEC2 --region sa-east-1
docker compose exec -T api python -m app.commands.aws_pricing_sync --coverage --service AmazonEC2 --region us-east-1
```

Os comandos acima são de inspeção, mas logs podem conter dados sensíveis: redigir antes de compartilhar. Falha de cobertura não autoriza inventar preço, nem comprova ausência de desperdício. Verificar `api`, `db`, `worker`, `web`/`proxy`, disco, RAM, DNS/HTTPS, credenciais do **backend**, schema vigente e latência. Manter `AVEN_AWS_PRICING_SYNC_ENABLED=0` e `AVEN_AWS_PRICING_IMPORT_ENABLED=0` até autorização específica.

## 2. Backups, restauração e migration

**Somente em homologação isolada antes de considerar produção:** capturar inventário e checksums de `aws_pricing_*`, `pricing_catalog_items`, OCI, `findings`, `opportunity_observations`, `opportunity_history_snapshots`, contas, políticas, overrides e auditoria. Guardar backup criptografado em destino protegido, com retenção e hash. Exemplo de backup lógico do container `db`; o operador deve configurar o diretório seguro fora do repositório:

```bash
mkdir -p /secure-backups
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > /secure-backups/aven-before-28.dump
sha256sum /secure-backups/aven-before-28.dump
```

**Prova de recuperação:** restaurar este arquivo em **outro cluster/stack PostgreSQL 17 descartável**, com banco vazio, role e extensões correspondentes, e então realizar consultas de integridade. Exemplo conceitual **somente no cluster descartável**: `pg_restore --no-owner --no-privileges -U <staging_user> -d <empty_staging_db> aven-before-28.dump`. Registrar total de objetos, linhas-chave e queries antes/depois; nunca apontar `pg_restore` para o banco em uso.

Após a prova de restauração, testar `alembic upgrade head` no banco novo e no dump legado restaurado. Verificar a cadeia `0040→0041→0042→0043`, locks/constraints, semântica `NULL` e preservação de IDs/linhas/zero legítimo. A API do Compose aplica migrations no startup; evitar executar duas migrações concorrentes. **A 0043 recusa downgrade quando há campos financeiros nulos.** Em incidente, restaurar backup verificado e versão compatível; não usar `UPDATE ... SET price=0` nem downgrade destrutivo.

## 3. Identidade AWS e IAM

Acesso AWS Pricing é realizado pelo backend/worker sob suas credenciais de hospedagem (instance profile ou chain autorizada), não pelas roles cross-account cadastradas. Confirmar necessidade e concessão mínima de `pricing:DescribeServices`, `pricing:ListPriceLists` e `pricing:GetPriceListFileUrl`; testar sem expor tokens em log. O endpoint da API Pricing pode usar `us-east-1`, independente do `RegionCode` comercial. Liberar DNS/HTTPS apenas para destinos permitidos pelo importador. **Não** alterar CloudFormation dos clientes para obter permissões de Pricing.

## 4. Dry-run regional (sem publicação)

Os comandos devem ser executados com `DATABASE_URL` de staging; salvar stdout em artefato protegido com horário UTC, fonte, região e status. O `--dry-run` pode fazer download e ocupar disco/rede, portanto dimensionar e monitorar.

```bash
docker compose exec -T api python -m app.commands.aws_pricing_import --service AmazonEC2 --region sa-east-1 --dry-run
docker compose exec -T api python -m app.commands.aws_pricing_import --service AmazonEC2 --region us-east-1 --dry-run
docker compose exec -T api python -m app.commands.aws_pricing_import --service AmazonRDS --region sa-east-1 --dry-run
docker compose exec -T api python -m app.commands.aws_pricing_sync --status --region sa-east-1
```

O relatório informa versão, quantidade, rejeições e componentes faltantes. Retorno `0` não prova homologação comercial; reportar `partial`/`failed`, não converter em sucesso. Fixtures e `--offline-dry-run` servem somente para teste de parser/contrato.

## 5. Publicação manual controlada — EXIGE APROVAÇÃO

Antes de cada unidade: comparar preço oficial e SKU/RateCode/currency/effective date na fonte, confirmar checksum e cobertura, validar backups e obter aceite de janela. Em staging, ativar **temporariamente** `AVEN_AWS_PRICING_IMPORT_ENABLED=1` na API/worker que executará a operação; manter `AVEN_AWS_PRICING_SYNC_ENABLED=0`. Após aplicar mudança no `.env` runtime, recriar **apenas** containers autorizados (sem `down -v`), confirmar flags reais sem mostrar segredos e monitorar. O exemplo abaixo **não autoriza execução em produção**:

```bash
docker compose exec -T api python -m app.commands.aws_pricing_sync --service AmazonEC2 --region sa-east-1 --apply
docker compose exec -T api python -m app.commands.aws_pricing_sync --service AmazonEC2 --region us-east-1 --apply
```

Avançar para `AmazonRDS`, `AWSELB` e `AmazonVPC` apenas após validação por unidade; EBS/snapshots podem compartilhar `AmazonEC2`. Não chamar `--all --apply` como carga inicial sem janela e limites previamente aprovados. Operação UI: Settings → Pricing AWS → região/serviço → status/cobertura → submissão por administrador autenticado, com CSRF, opt-in de importação e auditoria (sem reautenticação adicional a cada pedido); `202` só indica enfileiramento, consultar `sync/requests` e `sync/runs`/status até publicação e validação.

## 6. Reconciliação financeira e liberação de consumidores

Para cada cenário e região, anexar ARN/versão/arquivo hash, item AWS com SKU/Rate Code, unidade, termo On-Demand, atributos, effective date e tarifa USD; comparar com `GET /api/v1/pricing/aws/rates` e detalhamento (admin autenticado), Calculadora e Políticas **para a mesma configuração**. Verificar EC2 Linux/Windows, EBS gp2/gp3 capacidade/IOPS/throughput, RDS PostgreSQL/MySQL/MariaDB Single/Multi-AZ e storage, IPv4, snapshot, ALB/NLB/CLB. Custo parcial não é custo total. Diferença legítima de tempo, desconto, FX e imposto altera o **total**, não a tarifa-base.

Executar ensaio `v1 → coleta → observação/snapshot → v2 → coleta` em staging; comparar histórico, rankings e Savings Recognition por moeda. Um zero comercial real deve permanecer `0`; falta de tarifa deve permanecer `NULL` e não reconhecer economia. Usar [modelo de evidências](28.9-evidence-template.md).

## 7. Scheduler automático — manter desligado até GO

Após aprovação formal: definir intervalo, stale, limites e regiões em configuração de execução, aplicar `AVEN_AWS_PRICING_IMPORT_ENABLED=1` e `AVEN_AWS_PRICING_SYNC_ENABLED=1` **somente no ambiente autorizado**; recriar worker com mudanças revisadas. Iniciar com limites conservadores (defaults: 2 jobs/ciclo, 1 concorrente, 1 download). Consultar `--status`, UI e logs. O backend usa locks PostgreSQL, e deve manter `last_successful_batch_id` em erro; verificar empiricamente. Reverter flags para `0` diante de falha repetida ou de segurança. Gate de publicação manual pode ser desabilitado independentemente do agendamento.

## 8. Monitoramento, alertas e escalação

| Sinal | Diagnóstico | Resposta segura / critério de recuperação |
| --- | --- | --- |
| `stale` / sem sucesso | `--status`, execução/ARN/vigência, IAM/egress | Investigar falha; não publicar sem fonte aprovada; registrar batch novo válido |
| `failed`/retry | logs API/worker, código de erro, backoff, limites de arquivo | Corrigir causa e repetir unidade com autorização; confirmar last-good |
| `busy`/lock | 2 workers, locks por unidade, jobs em `running` | Esperar/rever fila sem editar SQL; confirmar expiração e reprocessamento |
| SKU obrigatório ausente | `--coverage`, filtros de região/OS/engine/tenancy | Manter cobertura parcial; não aumentar economia/reconhecimento |
| Tarifa ambígua/moeda | SKU/Rate Code, modalidade, USD, data | Bloquear aceitação; reconciliar fonte, preservar histórico |
| Falha integridade/download | origem allowlisted, checksum, DNS e espaço | Bloquear publicação; registrar evidência e reexecutar dry-run |
| Disco/RAM alto | consumo de staging, limite bytes/products/rates | Suspender novas unidades, limpar apenas temporários confirmados sem afetar dados |
| Erro em migration | `alembic current`, logs, dump restaurável | Parar mudanças e aplicar plano de restauração isolado |

Escalar ao responsável técnico FinOps e DBA/on-call quando falha afetar consistência de preço, histórico, moeda, acesso, restauração ou disponibilidade. Confirmar correção com consulta de catálogo, cobertura, batch atualizado e ausência de regressões nos consumidores. Definir responsáveis, limiares e canal de alerta antes do GO.

## 9. Recuperação e rollback por cenário

- **Falha de sync:** desabilitar `AVEN_AWS_PRICING_SYNC_ENABLED`; preservar catálogo last-good e histórico.
- **Tarifa incorreta:** desabilitar também `AVEN_AWS_PRICING_IMPORT_ENABLED`; bloquear novas publicações, coletar evidência, reconciliar e aprovar uma correção versionada. Não apagar linhas.
- **Worker instável:** pausar automatismo, capturar logs redigidos e fila; reparar/retomar conservando lock e idempotência.
- **Fila manual falhou:** consultar request/run, corrigir IAM/rede; nunca forçar estado por SQL.
- **Migration ou schema incompatível:** verificar backup **restaurado em clone** e executar plano de recuperação/compatibilidade; não executar downgrade 0043 com `NULL` nem migrar produção sem janela.
- **Regressão de aplicação:** avaliar rollback do código para versão **compatível com schema atual**, sem destruir banco; testar em clone.
- **Segredo exposto:** bloquear importação, revogar/rotacionar credencial via processo IAM, revisar logs e auditoria; não registrar material sensível no PR.

Cada incidente deve registrar gatilho, hora UTC, versões, impacto, responsável, decisão de rollback, dados preservados, checklist pós-recuperação (DB, worker, Pricing, Calculadora, Políticas, Opportunities, ledger, histórico), RTO/RPO **aprovados**, e aceitação do responsável.

## 10. Testes de liberação e registro de resultado

```bash
# Backend (runner com dependências instaladas e TEST_POSTGRES_URL apontando para PostgreSQL de teste)
cd backend
ruff check .
ruff format --check .
pytest -q

# Frontend
cd ../frontend
npm run lint
npm run typecheck
npm test
npm run build
npm run lint:i18n
npm run lint:i18n:references
npm run lint:i18n:coverage
npm run lint:design-system
npm run check:visual-regression
npm run test:aven:phase27
npm run test:i18n:authenticated
```

Registrar SHA exato, GitHub Actions run/job/conclusion, limites de testes e qualquer skip; não presumir que o E2E autentique com staging se usa fixtures do CI. Adicionar Phase 28 funcional e visual, bench e restore **separadamente**. Sem essas evidências, status final permanece NO-GO. Nunca executar deploy, sync automático ou merge da branch sem aprovação.
