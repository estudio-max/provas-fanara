# Ilustrações do passo a passo

Instruções para gerar as imagens da coluna de exemplo do passo a passo do
Fanara - Fotolivro. São onze imagens: cinco telas, e nas telas de escolha uma
imagem por opção — o exemplo troca quando o ponteiro passa sobre cada botão.

Os arquivos vão para `assets/passo-a-passo/`, com exatamente os nomes desta
lista. O `empacotar.py` recolhe todos os `.jpg` dessa pasta automaticamente.

## Especificação

| | |
|---|---|
| Área na tela | **400 × 600 px** |
| Proporção | **2:3, retrato** |
| Entregar em | **800 × 1200 px** (o dobro, para telas densas) |
| Formato | JPG ou PNG |
| Fundo | `#131418` |

Cinco regras que valem para todas:

1. **Proporção 2:3 em retrato.** Qualquer outra deixa faixas vazias nas
   laterais, porque a imagem é centralizada sem cortar. É a regra que mais
   importa.
2. **Fundo escuro `#131418`.** É a cor do painel. Fundo branco vira um bloco
   claro cortado no meio de um diálogo escuro.
3. **Sem texto dentro da imagem.** A explicação já está do lado direito, e
   texto embutido não seria traduzido quando o app falar inglês.
4. **Margem interna generosa.** A imagem encosta nas bordas do painel; o
   assunto precisa respirar longe do corte.
5. **Nas telas de escolha, mesma cena.** Mesma luz, mesmo ângulo, mesmo
   enquadramento — mudando só o que aquela opção muda. Se as imagens forem
   cenas diferentes, a comparação não se lê.

Os prompts estão em inglês porque os geradores de imagem respondem melhor
nessa língua. Como nada dentro da imagem é texto, o idioma do app não muda
nada.

---

## Tela 1 — Escolher a pasta do ensaio

Uma imagem. A tela só tem a ação de abrir a pasta.

### `pasta.jpg`

```
A dark, moody still life photographed from directly above: an open camera
memory card, a card reader, and a small stack of loose photographic prints
resting on a dark charcoal desk. A folder of RAW files is implied, not
literal — no computer screen, no user interface. Deep shadows, single soft
light from the upper left, warm wood and brushed metal textures. Background
is near-black, #131418. Muted palette with a single warm amber highlight.
Vertical 2:3 composition, subject centred with generous empty space at top
and bottom. Photographic, editorial, shallow depth of field. No text, no
logos, no interface elements.
```

---

## Tela 2 — Para que serve este PDF?

Duas imagens, uma por opção. Precisam ser comparáveis.

### `prova.jpg` — botão “Analisar como prova”

```
A printed photographic contact proof sheet lying on a dark charcoal surface,
seen slightly from above. Four portrait photographs arranged in a row on
white paper, each one carrying a faint translucent watermark across its
centre and a small alphanumeric file code printed underneath. A pencil rests
beside the sheet, suggesting a client marking choices. Background near-black,
#131418. Soft directional light from the upper left, deep shadows. Vertical
2:3 composition, generous empty space above and below the sheet.
Photographic and editorial. No readable text beyond the impression of small
codes, no logos, no user interface.
```

### `fotolivro.jpg` — botão “Analisar como fotolivro”

```
The same printed photographic sheet on the same dark charcoal surface, same
angle and same lighting as the proof version — but the four portrait
photographs are completely clean: no watermark, no file codes, nothing
printed under them. Pristine white paper, generous margins, ready for a
press. The pencil is gone. Background near-black, #131418. Soft directional
light from the upper left. Vertical 2:3 composition, generous empty space
above and below. Photographic and editorial. No text, no logos, no user
interface.
```

---

## Tela 3 — Acabamento das páginas

Quatro imagens. As três de fundo têm de ser a **mesma página com as mesmas
fotos**, mudando só a cor do papel — senão a diferença não fica legível.

### `fundo-branco.jpg` — botão “Fundo branco”

```
A single landscape page from a photo book, photographed flat from directly
above, floating against a near-black #131418 background. The page itself is
pure white with three portrait photographs laid out on it in a row, generous
white margins around them. The photographs are muted studio portraits in
warm neutral tones. No shadow under the photographs — they sit flat on the
paper. Vertical 2:3 composition, the page centred with wide empty dark space
above and below. Clean, editorial, precise. No text, no logos, no interface.
```

### `fundo-cinza.jpg` — botão “Cinza”

```
Exactly the same photo book page, same three portrait photographs, same
layout, same camera angle and lighting as the white version — but the page
stock is a soft mid grey instead of white. Everything else identical.
Floating against a near-black #131418 background. Vertical 2:3 composition,
page centred with wide empty dark space above and below. Clean, editorial,
precise. No text, no logos, no interface.
```

### `fundo-preto.jpg` — botão “Preto”

```
Exactly the same photo book page, same three portrait photographs, same
layout, same camera angle and lighting as the white version — but the page
stock is deep near-black. The photographs glow against it and their colours
read denser. A thin edge of the page separates it from the surrounding
background. Floating against a near-black #131418 background. Vertical 2:3
composition, page centred with wide empty dark space above and below. Clean,
editorial, precise. No text, no logos, no interface.
```

### `sombra.jpg` — botão “Sombra nas fotos”

```
A close crop of a white photo book page seen at a slight angle, showing two
portrait photographs that appear to rest on top of the paper rather than be
printed into it. Each photograph casts a soft, wide, diffuse drop shadow down
and slightly to the right, as if lit from above — the shadow is smoky and
gradual, never a hard edge. The lifted, tactile quality is the subject of the
image. Near-black #131418 background around the page. Vertical 2:3
composition. Macro, editorial, shallow depth of field. No text, no logos, no
interface.
```

---

## Tela 4 — Estilo da capa

Três imagens. O que precisa aparecer é a **estrutura** de cada estilo, não a
beleza da foto usada.

### `capa-classica.jpg` — botão “Clássica”

```
The cover of a printed photo book, photographed flat from above against a
near-black #131418 background. The cover is white with one single large
photograph occupying most of it, and a narrow band of empty paper above the
image where a title would sit. Restrained, editorial, a lot of air. The
photograph is a muted studio portrait in warm neutral tones. Vertical 2:3
composition, the book centred with generous dark space above and below. No
readable text, no logos, no interface.
```

### `capa-mosaico.jpg` — botão “Mosaico”

```
The cover of a printed photo book, photographed flat from above against a
near-black #131418 background, same book and same lighting as the classic
version. This cover is filled edge to edge with a tight grid of many small
photographs — roughly twenty of them — forming a dense mosaic, with a narrow
dark band at the foot of the cover. Muted studio portraits in warm neutral
tones. Vertical 2:3 composition, the book centred with generous dark space
above and below. No readable text, no logos, no interface.
```

### `capa-curvas.jpg` — botão “Curvas editoriais”

```
The cover of a printed photo book, photographed flat from above against a
near-black #131418 background, same book and same lighting as the other two.
On this cover the photographs are masked into large organic rounded shapes —
soft irregular blobs, not rectangles — scattered around an empty centre where
a title would sit. Roughly nine shapes, muted studio portraits in warm
neutral tones, on a dark cover stock. Vertical 2:3 composition, the book
centred with generous dark space above and below. No readable text, no logos,
no interface.
```

---

## Tela 5 — Exportar o PDF

Uma imagem. A tela fala de revisar e exportar, então mostra o objeto pronto.

### `exportar.jpg`

```
A finished printed photo book lying closed on a dark charcoal desk, seen from
above at a slight angle, with a few loose printed pages fanned out beside it.
The book looks freshly delivered — crisp edges, clean white pages, no wear.
Deep shadows, single soft light from the upper left, warm neutral tones.
Background near-black, #131418. Vertical 2:3 composition, the book positioned
in the lower two thirds with generous empty dark space above. Photographic,
editorial, shallow depth of field. No text, no logos, no interface elements.
```

---

## Ressalva

Sete destas onze imagens hoje são **saída real do motor**, renderizadas do
ensaio “eu selfie”: as duas de modo, as quatro de acabamento e as três de
capa. Elas mostram literalmente o que o aplicativo produz; uma imagem gerada
por IA mostra uma representação.

Se o problema for só o enquadramento, essas sete podem ser regeradas direto
do motor já em 2:3, sem prompt nenhum, reservando a IA para as duas que não
são saída do app — a da pasta e a do PDF pronto. Os onze prompts ficam aqui
para o caso de você preferir o conjunto inteiro com uma direção de arte única.

## Depois de gerar

Coloque os arquivos em `assets/passo-a-passo/` com os nomes desta lista e
abra o app. Nada mais precisa ser alterado: o carregamento é por nome, e o
`empacotar.py` já recolhe a pasta inteira.
