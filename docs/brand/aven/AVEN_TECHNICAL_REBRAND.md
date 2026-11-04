# Aven — Identidade pública e compatibilidade técnica

A identidade pública única do produto é **Aven**, com assinatura **Clarity. Flow. Control.** O frontend utiliza `frontend/lib/brand.ts` como fonte de nome, descrição e caminhos dos assets; `frontend/components/brand/brand-logo.tsx` fornece as variantes oficiais de logo.

## Situação de produção

- O runtime dispõe de lockups oficiais em SVG de alta resolução para superfícies claras e escuras, com variantes horizontal, vertical e sem assinatura.
- Ícones, favicon e fundos ambientes são selecionados pelas referências versionadas em `frontend/public/brand/aven/`.
- A sidebar, o login, as telas de autenticação e os metadados do navegador usam Aven.
- Tema Light/Dark/System, tokenização semântica e componentes oficiais são contratos obrigatórios da camada visual.

Os registros anteriores de assets indisponíveis ou de logo provisória descreviam etapas intermediárias e não devem ser tratados como bloqueios atuais.

## Identificadores técnicos mantidos

A atualização da documentação **não modifica** contratos que já persistem em instalações existentes. Entre eles:

| Categoria | Regra |
| --- | --- |
| Variáveis de ambiente | Seguir os nomes efetivamente definidos em `.env.example` e `backend/app/core/config.py` |
| IAM e CloudFormation | Preservar nomes dos arquivos/templates, roles já criadas e External IDs |
| Banco de dados | Preservar migrations, tabelas de versão e identidades persistidas |
| Sessão e autenticação | Não renomear cookies, cabeçalhos CSRF, eventos ou chaves criptográficas |
| APIs | Não alterar caminhos e campos serializados sem contrato de compatibilidade |
| Preferências | Preservar storage keys para não redefinir o estado salvo dos usuários |
| Automação de deploy | Preservar arquivos de serviço, unidades systemd e diretórios persistidos |

Renomeações desses contratos exigem aliases, migração, testes e rollback explícitos; não fazem parte de uma limpeza de documentação.

## Política de branding

Nenhum texto público novo deve apresentar nomes anteriores do produto. O validador em `frontend/scripts/check-brand.mjs` verifica arquivos de runtime, enquanto `frontend/scripts/brand-legacy-allowlist.mjs` classifica exceções técnicas de compatibilidade. A documentação pode utilizar os termos **identificador legado**, **contrato persistido** ou **nome técnico existente** sem reintroduzir marcas descontinuadas como identidade visível.

## Critérios de aceitação

- Consumo de `AvenLogo` e do mapa de assets oficiais;
- componentes novos usando tokens e Theme Engine;
- nenhum contrato técnico renomeado indevidamente;
- `npm run lint:brand` e `npm run lint:design-system` aprovados;
- validação de login, shell, dados, formulários, tema e responsividade no frontend.

Consulte também [guia oficial](README.md), [assets de produção](AVEN_OFFICIAL_BRANDING_ASSETS.md) e [regressão visual](../../../frontend/docs/visual-regression.md).
