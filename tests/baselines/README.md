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
