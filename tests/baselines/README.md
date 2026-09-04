# Baselines da regressão visual

Esta gate usa fotografias sintéticas 2:3 com cores, rótulos, cenas de plano
amplo/detalhe e uma duplicata visual controlada. As imagens renderizadas são
intermediárias e ficam em `tmp/visual-qa`; somente esta descrição textual é
versionada.

| Caso | Fotos | Orientação | Semente aprovada | Modos |
| --- | ---: | --- | ---: | --- |
| `24-verticais` | 24 | retrato | 1201 | prova e fotolivro |
| `24-horizontais` | 24 | paisagem | 2402 | prova e fotolivro |
| `32-mistas` | 32 | retrato/paisagem | 3203 | prova e fotolivro |

Critérios visuais: capa coerente com a prévia, abertura legível, páginas densas
sem mais de duas consecutivas, pausas editoriais, encerramento claro, legenda
longa contida no modo prova, nenhuma legenda ou marca no fotolivro limpo e
fotografias inteiras sem corte, distorção ou rotação decorativa.

## Reproduzir a inspeção

Depois de executar os testes E2E, renderize novamente todos os PDFs a 120 dpi e
gere as folhas de contato com:

```powershell
python tests/visual_qa.py tmp/visual-qa
```

O helper reabre cada PDF com PyMuPDF, grava todas as páginas em
`tmp/visual-qa/<caso>/<modo>/page-NNN.png` e escreve
`tmp/visual-qa/<caso>/<modo>-contact-sheet.png`. Esses PNGs são evidência local
ignorada pelo Git e devem ser inspecionados visualmente, não versionados.

## Capa Curvas editoriais - Órbita equilibrada

A gate aprovada cobre `1`, `3`, `5`, `6` e `9` retratos, sempre com a semente
determinística `8600 + quantidade`. Para cada quantidade são combinadas as
fixtures `claros`, `escuros` e `mistos` com logotipo `horizontal`, `vertical` e
`ausente`, totalizando 45 PDFs e 45 folhas de contato. As fotografias alternam
2:3 vertical e 3:2 horizontal, têm rótulo único e um rosto sintético deslocado
para tornar enquadramento, repetição e foco visualmente auditáveis.

Reproduza exatamente essa matriz a 120 dpi com:

```powershell
python tests/visual_qa.py --case curvas-editoriais --dpi 120 --output tmp/visual-qa/curvas-editoriais
```

Na inspeção, aceite somente: arcos antialias sem serrilhado ou frestas; nenhum
rosto cortado; contraste legível no núcleo central; título, estúdio e site
contidos; logotipos sem distorção; vazios intencionais equilibrados; cada foto
usada uma única vez; e primeira página do PDF idêntica à prévia. Os dois modos
continuam cobertos pela matriz E2E automatizada de quantidades `1..9`: prova
com marca/nomes somente no miolo e fotolivro sem ambos.

## Capa Clássica

A matriz Clássica cobre foto horizontal e vertical, escolha automática,
enquadramento manual à esquerda/direita, zoom 100%, 150% e 250%, além de título
curto e acentuado. Reproduza as seis capas e a overview a 120 dpi com:

```powershell
python tests/visual_qa.py --case capa-classica --dpi 120 --output tmp/visual-qa/capa-classica
```

Aceite somente: fundo branco; margens laterais de 8%; título Bodoni contido;
estúdio com tracking regular; fotografia sem área vazia ou distorção; rosto
preservado no automático; foco/zoom distintos no manual; e primeira página do
PDF idêntica à prévia.

## Aparência das páginas internas

A matriz cobre os 12 estados de três fundos (`branco=#FFFFFF`,
`cinza=#D2D2D2`, `preto=#111215`) × sombra desligada/ligada × Prova/Fotolivro.
As capas Clássica, Mosaico e Curvas editoriais são distribuídas de modo
determinístico pela matriz. A fixture contém retratos 2:3, paisagens 3:2 e um
nome de arquivo longo. A captura nativa registra os controles em 1093×614 a
125%, com Preto e sombra ligados.

Reproduza os 12 PDFs, suas páginas originais, folhas de contato, overview,
captura da interface e manifesto QA com:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_SCALE_FACTOR = "1.25"
python tests/visual_qa.py --case aparencia-paginas --dpi 120 --output tmp/visual-qa/aparencia-paginas
```

Aceite somente: fundo exato e uniforme nas áreas livres; texto e filetes
legíveis; sombra curta, discreta, sem banding, brilho ou invasão de outro slot;
fotografias inteiras e sem distorção; nome longo centralizado sob a própria
foto no modo Prova; marca d'água somente na Prova; nenhum nome ou marca no
Fotolivro; capas sem qualquer efeito da aparência interna; e prévia idêntica ao
PDF. O arquivo `aparencia-paginas-qa.json` deve listar 12 combinações, os três
estilos de capa, DPI 120 e escala 1,25.
