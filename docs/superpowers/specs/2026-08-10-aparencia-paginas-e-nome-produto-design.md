# Aparência das páginas e nome do produto

## Objetivo

Permitir que cada álbum use um de três fundos editoriais e uma sombra suave
opcional nas fotografias, preservando a fidelidade entre prévia e PDF. Unificar
também o nome visível do produto como **Fanara - Fotolivro**.

## Nome do produto

O texto visível será `Fanara - Fotolivro` na barra da janela, mensagens de
sistema, metadados, ajuda, documentação e qualquer identificação apresentada
ao usuário. Os artefatos Windows passam a se chamar `Fanara - Fotolivro.exe`,
pasta `Fanara - Fotolivro` e `Fanara - Fotolivro-Windows.zip`. Manifesto,
testes e instruções devem usar os mesmos nomes; nenhum artefato público mantém
o nome antigo isolado `Fotolivro`.

## Presets de fundo

Cada projeto oferece três escolhas mutuamente exclusivas para as páginas
internas:

- **Branco:** `#FFFFFF`.
- **Cinza:** `#D2D2D2`, neutro e sem textura.
- **Preto:** `#111215`, alinhado ao fundo escuro do aplicativo.

O padrão de projetos novos e migrados é Branco. A capa não recebe esse fundo:
ela continua sendo renderizada integralmente pelo estilo escolhido.

Cada preset seleciona automaticamente uma paleta de contraste para títulos,
filetes, molduras, números de página, site e nomes de arquivo. Texto corrente
deve manter contraste WCAG de pelo menos 4,5:1; elementos grandes ou puramente
gráficos, pelo menos 3:1. Marca d'água permanece sobre a própria fotografia e
não muda por causa do fundo.

## Sombra suave

Um controle `Sombra suave nas fotos` liga ou desliga o efeito por álbum. O
padrão é desligado. Quando ativo, o compositor desenha atrás de cada retângulo
físico de foto uma sombra neutra, curta e de baixa opacidade. O efeito deve
parecer separação do papel, não uma moldura decorativa: deslocamento máximo de
5 pt, expansão máxima de 3 pt e opacidade combinada abaixo de 16%.

A sombra não modifica pixels da fotografia, crop, proporção, marca d'água nem
legenda. Deve ficar contida na área editorial da página e nunca invadir outra
foto. Para preservar nitidez e tamanho do PDF, usar camadas vetoriais graduais
com `fill_opacity`, não rasterizar a página nem pré-compor a fotografia.

No fundo Preto o efeito pode ser muito discreto; a moldura adaptativa continua
garantindo separação visual. Não será criado brilho claro artificial.

## Interface e persistência

Na barra lateral, uma seção compacta `Aparência das páginas` apresenta um
controle segmentado Branco/Cinza/Preto e um checkbox `Sombra suave nas fotos`.
Os controles ficam disponíveis depois da análise e atualizam a prévia sem
alterar plano, seed, ordem, crop, capa ou seleção de fotos.

O schema do projeto ganha `fundo_paginas` (`branco|cinza|preto`) e
`sombra_fotos` (`bool`). Projetos anteriores migram idempotentemente para
`branco` e `false`. Salvar e reabrir restaura exatamente as duas escolhas.

## Renderização e erros

`Documento` continua sendo a única fronteira visual para prévia e PDF. A
paleta resolvida e a sombra são aplicadas apenas às páginas internas em todos
os templates e no caminho legado. Valores desconhecidos no projeto produzem
erro PT-BR; a UI nunca grava valores fora do catálogo.

## Verificação

- Testes cobrem os três fundos nos modos Prova e Fotolivro.
- Contraste é calculado e validado para todos os textos editoriais.
- Sombra ligada/desligada altera apenas pixels externos às fotos; dimensões,
  proporções e conteúdo das fotografias permanecem iguais.
- Capa e `BookPlan` permanecem byte/estruturalmente iguais ao trocar aparência.
- Round-trip e migração preservam os novos campos.
- Capturas da UI em 1093×614 a 125% verificam clipping, foco e hierarquia.
- PDFs Branco/Cinza/Preto, com e sem sombra, são renderizados e inspecionados.
- Empacotamento final contém apenas o novo nome e continua sem dados privados.
