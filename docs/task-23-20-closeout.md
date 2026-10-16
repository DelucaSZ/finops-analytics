# Etapa 23.20 — Fechamento pós-merge

**Status:** concluída e incorporada à `main` pelo PR #74.

Este documento registra o fechamento da Task 23.20 após o merge do redesign global e da experiência multi-cloud.

## Publicação

- PR de implementação: **#74 — feat: Task 23.20 — redesign global e experiência multi-cloud**.
- Head funcional validado antes do merge: `1534c4c005ae861a24e0beb226dfa9e44a98a01b`.
- Merge commit na `main`: `029a1b579ac6c91f8adee14ac9748a91eb7c8ef4`.
- A implementação alterou 18 arquivos no PR original, com consolidação de tema, navegação, tokens, responsividade e branding multi-cloud.

## Estado final da implementação

A experiência global passa a utilizar branding provider-neutral, temas `System`, `Light` e `Dark`, sidebar desktop recolhível e persistente, drawer mobile independente, tokens semânticos compartilhados e nova área `Configurações > Aparência`.

Foram consolidadas visualmente Dashboard, Oportunidades/Histórico/detalhe, Fluxo, Billing, Coletas, Settings, Pricing OCI, Billing Profiles, Usage & Costs e autenticação, sem alterar regras de negócio para facilitar a interface.

Permanecem invariantes:

- nenhuma conversão cambial automática;
- BRL e USD continuam separados;
- Pricing OCI permanece em BRL;
- Billing e Fluxo continuam domínios distintos;
- lifecycle humano e presença técnica continuam dimensões independentes;
- nenhuma nova regra financeira, provider, analyzer, forecast, Billing OCI ou comportamento de lifecycle foi introduzido pela 23.20.

## Validação automatizada

O head funcional do PR #74 foi aprovado nos gates cumulativos do projeto:

- backend: `ruff check .` aprovado;
- backend: `ruff format --check .` aprovado;
- backend: `pytest -q` com **850 testes aprovados**;
- frontend: `npm test` com **113 testes aprovados**;
- frontend: `npm run build` aprovado, incluindo lint/type validation e geração das páginas;
- security job aprovado;
- Stage 21 Compose smoke aprovado;
- Auto deploy tests aprovado.

O build final manteve **103 kB** de First Load JS compartilhado e não adicionou dependências visuais novas.

## Smoke visual e rollout operacional

O smoke visual manual não é tratado como evidência automatizada nem como requisito retroativo para o merge já realizado. A decisão operacional adotada após o merge é validar a experiência diretamente no ambiente implantado durante o próximo rollout/pull de produção.

Essa validação operacional deve observar principalmente:

- temas `System`, `Light` e `Dark`;
- persistência da preferência de tema;
- sidebar desktop expandida/recolhida e persistência após reload;
- drawer mobile, overlay, Escape e fechamento após navegação;
- contraste, focus visible, tabelas, forms, dialogs e estados de erro/loading;
- ausência de regressões entre Billing e Fluxo;
- preservação visual da separação entre status humano e presença técnica;
- preservação de BRL/USD sem consolidação cross-currency;
- console do navegador sem erros durante os fluxos principais.

Se o teste direto em produção revelar regressão visual, a correção deve ser tratada como hotfix/follow-up da 23.20 sem reinterpretar os critérios financeiros ou de lifecycle da etapa.

## Documentação relacionada

O detalhamento funcional e arquitetural do redesign permanece em `docs/task-23-20-product-ui-redesign.md`. Este arquivo registra especificamente o fechamento pós-merge, a validação automatizada concluída e a decisão de realizar o smoke visual como validação operacional no rollout.
