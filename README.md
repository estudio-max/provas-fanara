# Provas

Gera o PDF de seleção de fotos a partir da pasta do ensaio — o mesmo trabalho que
hoje é feito no Lightroom, sem abrir o Lightroom.

Lê a pasta, monta uma capa com as próprias fotos da sessão, diagrama as páginas
com a quantidade de fotos que você pedir, grava a marca d'água em cada imagem e
escreve o código do arquivo embaixo de cada foto.

**300 fotos ficam prontas em cerca de 50 segundos, num PDF de ~20 MB.**

## Abrir

- **Windows**: duplo-clique em **`Provas.bat`** (ou, se já empacotou, em
  `dist/Provas/Provas.exe`).
- **macOS**: duplo-clique em **`Provas.command`**. Na primeira vez pode ser
  preciso liberar a execução: `chmod +x "Provas.command"`.
- Em qualquer sistema: `python3 Provas.pyw`.

Antes do primeiro uso numa máquina nova, vale rodar `python3 verificar.py`, que
confere dependências e fontes e diz exatamente o que falta.

O fluxo é: escolher a pasta → conferir as opções → **Amostra (12 fotos)** para ver
como ficou → **Gerar PDF**. As opções escolhidas ficam salvas para a próxima vez.

## De onde vêm as imagens

- Se houver **JPG**, ele é usado.
- Se a pasta só tiver **RAW** (`.NEF`, `.CR2`, `.ARW`, `.DNG`, `.ORF`, `.RW2`…),
  o app lê a pré-visualização JPEG em tamanho cheio que a câmera já gravou dentro
  do arquivo. É por isso que é rápido: não há revelação de RAW.
- Quando os dois existem com o mesmo nome (`D61_3313.NEF` + `D61_3313.JPG`), é a
  mesma foto e aparece uma vez só.
- A orientação da câmera é respeitada — retrato sai em pé.

## Os dois modos

| | Prova para o cliente escolher | Álbum |
|---|---|---|
| Marca d'água | **Aplicar** ligado | desligado |
| Códigos sob as fotos | ligado | desligado |

Sem a legenda, o cartão fecha simétrico em volta da foto e a imagem sai maior —
por isso o mesmo app serve para entregar um álbum.

## Capas

- **Mosaico** — todas as fotos da sessão preenchendo a página.
- **Losango** — malha de diamantes. Fica melhor a partir de ~80 fotos; abaixo
  disso os losangos crescem ou algumas fotos se repetem.
- **Destaque** — mosaico escurecido com um losango grande, aceso, no centro. A
  foto de destaque é a do meio da sessão.

## Diagramação

Você diz quantas fotos quer por página; o app testa as combinações de colunas e
linhas e escolhe a que deixa **cada foto o maior possível** para o formato do
ensaio. As linhas encolhem até a altura real das fotos e o bloco é centralizado,
para não abrir vãos no meio da página.

- **Girar horizontais**: fotos deitadas giram 90° para ocupar a célula em pé,
  como o "rotate to fit" do Lightroom.
- **A4 deitado**: inverte a página, útil quando o ensaio é quase todo horizontal.
- **Qualidade**: leve (150 dpi) · normal (200 dpi) · alta (300 dpi, para imprimir).

## Cor de fundo

Há quatro atalhos (Grafite, Preto, Papel, Branco) e um seletor para qualquer cor.
**Todo o resto do tema se recalcula sozinho**: escolhendo um fundo claro, o texto
inverte para escuro, os cinzas intermediários são refeitos, o véu da capa passa a
clarear em vez de escurecer e o logotipo deixa de ser convertido para branco.
Não existe "tema claro" separado para manter — existe uma cor, e o resto deriva
dela.

## Nome do estúdio e site

- **Nome do estúdio** aparece no topo das páginas *quando não há logotipo*, e vai
  no campo autor do PDF.
- **Site** aparece no rodapé de todas as páginas e no pé da capa, na cor de
  destaque. Com os códigos ligados ele fica centralizado; no modo álbum, à
  esquerda, já que o recado sobre os códigos some.

## Marca d'água

O logotipo é gravado **nos pixels** da imagem, não desenhado por cima no PDF —
não dá para remover copiando a foto do arquivo. Opacidade e tamanho são
ajustáveis. O logotipo padrão fica em `assets/logo.png`; qualquer PNG com fundo
transparente serve.

## Linha de comando

Para automatizar ou testar sem abrir a janela:

```bash
python provas_cli.py "C:\ensaios\Bianca" -n 6 --capa destaque
```

```bash
python provas_cli.py "C:\ensaios\Bianca" --album -q alta --fundo "#F4F2EE" --site seusite.com.br
```

`--album` é atalho para `--sem-marca --sem-codigos`. Use `--amostra` para gerar
só com as 12 primeiras fotos. `python provas_cli.py --help` lista tudo.

## macOS (Monterey ou mais novo)

O app roda no Mac. Três coisas foram tratadas para isso:

- **Fontes.** Cada papel tipográfico é procurado numa lista — nomes do Windows,
  depois os equivalentes do macOS (Georgia, Trebuchet MS, Verdana, Arial), depois
  os do Linux. Não achando nenhuma, cai para as fontes que **todo PDF já
  entende** (Times e Helvetica). O documento perde requinte e não deixa de sair.
- **Preferências.** Dentro de um `.app`, o executável fica no interior do pacote,
  onde não se deve gravar. No Mac o `config.json` vai para
  `~/Library/Application Support/Provas/`.
- **Abrir o PDF pronto** usa `open`, não `xdg-open`.

Rodando do código-fonte, precisa de Python 3.10+ com tkinter. O Python do
**python.org** é o recomendado: o do sistema e o do Homebrew às vezes vêm sem
tkinter ou com um Tk antigo. Depois:

```bash
python3 -m pip install Pillow PyMuPDF
```

```bash
python3 verificar.py "/Users/voce/Ensaios/Bianca"
```

O `verificar.py` mostra o que foi encontrado — versões, pastas de fontes, qual
fonte cada papel pegou — e, se você passar uma pasta de ensaio, gera um PDF de
teste. É a forma mais rápida de saber se está tudo certo naquela máquina.

## Enviar para outra pessoa

```bash
python empacotar.py
```

No Windows gera `dist/Provas-Windows.zip`; no macOS, `dist/Provas-macOS.zip` com
o `Provas.app`. Cerca de 40 MB, e a pessoa não precisa instalar mais nada. Vai
junto um `LEIA-ME.txt` explicando o uso e o aviso de segurança do sistema.

**O PyInstaller não faz compilação cruzada**: a versão de Mac só pode ser gerada
rodando `empacotar.py` num Mac, e o pacote sai para a arquitetura daquela máquina
— um build feito em Apple Silicon não roda em Mac Intel, e vice-versa.

Três decisões do empacotamento, todas deliberadas:

- **Pasta, não arquivo único.** O `.exe` único descompactaria ~80 MB a cada
  abertura e é bem mais propenso a alarme falso de antivírus. Zipada, continua
  sendo um arquivo só para enviar.
- **O logotipo não vai embutido.** Quem receber aponta o próprio na janela; caso
  contrário sairia a marca d'água do seu estúdio nas fotos dele. Se a marca
  estiver ligada sem logotipo válido, o app avisa antes de gerar.
- **Nada de nome fixo no código.** "Nome do estúdio" e "Site" são campos.

Por não ter assinatura digital paga, o sistema do destinatário vai reclamar na
primeira abertura. No **Windows**: "O Windows protegeu o computador" → *Mais
informações* → *Executar assim mesmo*. No **macOS** o bloqueio é mais duro —
é preciso clicar com o botão direito no `Provas.app` e escolher *Abrir* (abrir
com duplo-clique não oferece a opção de liberar). Se o Mac disser que o app
"está danificado", o comando abaixo remove a marca de quarentena:

```bash
xattr -dr com.apple.quarantine "/Applications/Provas.app"
```

Isso vale para qualquer programa não assinado e só se resolve comprando um
certificado de desenvolvedor.

Depois de enviar, `dist/` pode ser apagada; `empacotar.py` refaz quando precisar.

## Estrutura

```
provas/tema.py        paleta derivada da cor de fundo, fontes e medidas
provas/raw.py         lê o JPEG embutido nos arquivos RAW (parser TIFF próprio)
provas/imagens.py     abre, orienta, marca d'água, miniaturas, mosaico
provas/capas.py       os três estilos de capa
provas/documento.py   grade, tipografia e escrita do PDF
provas/motor.py       o pipeline que junta tudo
provas/app.py         a janela
verificar.py          diagnóstico de dependências e fontes da máquina
empacotar.py          gera o app para distribuir (Windows ou macOS)
```

Depende de **Pillow** e **PyMuPDF**:

```bash
python -m pip install Pillow PyMuPDF
```

As fontes vêm do sistema e são embutidas no PDF: Constantia e Segoe UI no
Windows, Georgia e Trebuchet MS no macOS, com Times e Helvetica como última
garantia.
