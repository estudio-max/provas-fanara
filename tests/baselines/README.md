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
