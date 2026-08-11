# Fotolivro editorial

Aplicativo Windows para transformar a pasta de uma sessão em um fotolivro A4
paisagem. Ele analisa as fotografias, propõe uma narrativa, mostra a prévia
editável e exporta o PDF sem recortar, distorcer ou girar fotos decorativamente.

## Instalação e abertura

Para executar o código-fonte, instale Python 3.10 ou mais recente e as
dependências:

```powershell
python -m pip install .
python verificar.py
python Provas.pyw
```

`verificar.py` confirma as versões mínimas, fontes, escrita e o pipeline real
de PDF A4 paisagem. No pacote distribuído, extraia a pasta inteira e abra
`Fotolivro.exe`; Python não é necessário.

## Fluxo da mesa de edição

1. Clique em **Escolher pasta**.
2. Clique em **Analisar fotografias** para gerar o plano e as prévias.
3. Escolha **Prova para seleção** ou **Fotolivro limpo**.
4. Escolha a capa. Novos projetos usam **Clássica**: uma fotografia, título e
   estúdio. Use **Trocar fotos da capa** para escolher a imagem e **Ajustar
   enquadramento** para arrastar, aplicar zoom de 100–250% ou restaurar o foco
   automático. Mosaico e Curvas editoriais continuam disponíveis.
5. Opcionalmente use **Regenerar**; a última regeneração pode ser desfeita.
6. Use **Salvar projeto** para guardar o plano ou **Exportar PDF** para a
   entrega final.

Cada página interna com alternativa mostra o botão `↻`. Ele mantém as mesmas
fotos, mas pode permutar suas posições em uma diagramação compatível; os
cliques percorrem o ciclo determinístico e voltam ao início. A escolha fica
salva no projeto e vale tanto para a prévia quanto para o PDF. Capa e páginas
sem alternativa não exibem esse controle.

O motor narrativo avalia orientação, nitidez, exposição, densidade e
similaridade. Com uma semente reproduzível, monta abertura, detalhes e respiros
e limita páginas densas a no máximo duas consecutivas.

## Dois modos

- **Prova para seleção**: inclui marca d'água e o código do arquivo sob cada
  fotografia.
- **Fotolivro limpo**: não inclui marca d'água nem códigos.

Esses modos são fechados para manter a intenção de cada entrega. Ambos usam A4
horizontal e encaixam as fotografias inteiras nas áreas do projeto.

## Fotos aceitas e limitações RAW

São aceitos JPG/JPEG e RAW usuais, como NEF, CR2, ARW, DNG, ORF e RW2. Quando
existem RAW e JPG com o mesmo nome, a imagem aparece uma vez. Para RAW, o
aplicativo usa a prévia JPEG integrada pela câmera; ele não revela RAW, não
aplica perfis de cor, correção de lente ou ajustes de exposição. Arquivos sem
prévia JPEG utilizável podem ser ignorados.

## Privacidade e projetos

Um `.provas.json` guarda o plano editorial, a configuração e referências aos
caminhos das fotos; não contém fotos, miniaturas ou logotipos. Mantenha as
fotografias na pasta original para reabrir e exportar o projeto. O pacote
Windows exclui `config.json` e `logo.png` locais.

A detecção de rosto é executada localmente; nenhuma fotografia é enviada pela internet.
Projetos v1 abrem como mosaico. Logotipo inválido é ignorado com aviso.
Projetos novos usam Capa Clássica; a foto e o recorte escolhidos são preservados
no `.provas.json`. O logotipo completo das capas mantém suas cores originais,
sem conversão preto/branco dependente da fotografia de fundo.

## Linha de comando

Para automação, gere um plano novo ou reexporte um salvo:

```powershell
python provas_cli.py "C:\ensaios\Bianca" --modo prova --capa mosaico --titulo "Seleção Bianca" --saida "C:\entregas\Bianca-prova.pdf"
python provas_cli.py "C:\ensaios\Bianca" --modo fotolivro --capa curvas_editoriais --titulo "Bianca" --estudio "Estúdio Fanara" --site "fanara.com.br" --logo "C:\marcas\fanara.png" --salvar-projeto "C:\ensaios\Bianca.provas.json" --saida "C:\entregas\Bianca-fotolivro.pdf"
python provas_cli.py --abrir-projeto "C:\ensaios\Bianca.provas.json" --saida "C:\entregas\Bianca.pdf"
python provas_cli.py --abrir-projeto "C:\ensaios\Bianca.provas.json" --saida "C:\entregas\Bianca.pdf" --sobrescrever
```

`--modo {prova,fotolivro}` é a interface atual; `--album` é um alias obsoleto
para `--modo fotolivro`. Ao abrir um projeto, `--saida` é obrigatório e deve
terminar em `.pdf`. A CLI preserva qualquer PDF que já exista no destino;
somente `--sobrescrever` autoriza explicitamente sua substituição, inclusive
ao reexportar um projeto salvo.
Use `python provas_cli.py --help` para os argumentos em português.

## Migração do Provas antigo

O Provas anterior montava folhas de seleção por grade. Abra a mesma pasta nesta
mesa editorial, escolha **Prova para seleção** para a entrega com marca e
códigos ou **Fotolivro limpo** para a entrega sem ambos, revise e salve um novo
`.provas.json`. Preferências antigas em `config.json` não são usadas por esta
mesa; PDFs já gerados permanecem inalterados.

## Gerar o pacote Windows

```powershell
python empacotar.py
```

O comando, executado no Windows, gera `dist/Fotolivro-Windows.zip` com
`Fotolivro.exe`, o QSS, ícone, plugin de plataforma PySide6, NumPy, OpenCV,
o cascade facial local, `BUILD-MANIFEST.json` e `LEIA-ME.txt`.
Como o executável não tem assinatura digital, o Windows pode pedir confirmação
na primeira abertura.
