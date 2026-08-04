# Fotolivro editorial

Aplicativo Windows para transformar a pasta de uma sessão em um fotolivro A4
paisagem. Ele analisa as fotografias, propõe uma narrativa, mostra a prévia
editável e exporta o PDF final sem cortar ou distorcer as fotos 2:3.

## Instalação e abertura

Requer Python 3.10 ou mais recente. Em uma cópia do código, instale as
dependências e confirme a máquina:

```powershell
python -m pip install Pillow PyMuPDF PySide6
python verificar.py
python Provas.pyw
```

O verificador informa a versão do Python, Pillow, PyMuPDF, PySide6, fontes e
permissão de escrita. No pacote para Windows, extraia a pasta inteira e abra
`Fotolivro.exe`; não é necessário instalar Python.

## Dois modos

- **Prova**: aplica uma marca d'água discreta e mostra o código do arquivo sob
  cada imagem, para a seleção do cliente.
- **Fotolivro**: saída limpa, sem marca d'água e sem códigos.

Os dois modos usam A4 horizontal. Fotografias são encaixadas inteiras nas áreas
do projeto: não há recorte, esticamento ou rotação decorativa.

## Motor narrativo e mesa de edição

Após escolher a pasta, o motor avalia orientação, nitidez, exposição,
densidade e similaridade. Com uma semente reproduzível, ele compõe abertura,
páginas de detalhe e de respiro, mantendo no máximo duas páginas densas em
sequência. A mesa de edição permite:

- alternar entre Prova e Fotolivro;
- substituir as fotos da capa;
- regenerar outra proposta e desfazer a regeneração;
- inspecionar avisos de fotos ausentes, inválidas ou de baixa qualidade;
- salvar o projeto e exportar exatamente o plano que foi revisado.

## Fotos aceitas e RAW

São aceitos JPG/JPEG e arquivos RAW usuais, como NEF, CR2, ARW, DNG, ORF e
RW2. Quando há JPG e RAW com o mesmo nome, a foto aparece uma vez. Em RAW, o
aplicativo usa a prévia JPEG integrada pela câmera; ele **não revela RAW**,
não aplica perfis de cor, ajustes de exposição ou correções de lente. RAW sem
prévia JPEG suficientemente grande pode não ser aproveitado.

## Privacidade e arquivos de projeto

O arquivo `.provas.json` guarda somente o plano editorial, a configuração, os
caminhos das fotos e chaves de análise. Ele não copia imagens, miniaturas nem
o logotipo para dentro do projeto. Mantenha as fotos na pasta original para
reabrir e exportar. Antes de distribuir o aplicativo, `config.json` e
`logo.png` locais são excluídos do pacote.

## Linha de comando

Use a CLI para automação, amostras e exportações reproduzíveis:

```powershell
python provas_cli.py "C:\ensaios\Bianca" --modo prova --semente 42 --amostra
python provas_cli.py "C:\ensaios\Bianca" --modo fotolivro --salvar-projeto "C:\ensaios\Bianca.provas.json"
python provas_cli.py --abrir-projeto "C:\ensaios\Bianca.provas.json"
```

`--modo {prova,fotolivro}` é a interface atual. `--album` continua aceito como
alias obsoleto para `--modo fotolivro`. Há também `--saida`, `--titulo`,
`--data`, `--semente`, `--salvar-projeto`, `--abrir-projeto` e `--amostra`;
execute `python provas_cli.py --help` para a lista completa.

## Migração do Provas antigo

O Provas anterior montava folhas de seleção por grade. Nesta versão, abra a
mesma pasta de fotos na mesa editorial, escolha **Prova** para manter marca e
códigos, ou **Fotolivro** para a entrega limpa, revise a prévia e salve um novo
`.provas.json`. As preferências antigas em `config.json` não são migradas
automaticamente: informe novamente nome do estúdio, site e logotipo se quiser
usá-los. PDFs já gerados continuam inalterados.

## Gerar o pacote Windows

```powershell
python empacotar.py
```

O comando gera `dist/Fotolivro-Windows.zip`, com `Fotolivro.exe`, QSS, ícone,
plugins de plataforma do PySide6 e `LEIA-ME.txt`. Como o executável não tem
assinatura digital, o Windows pode pedir confirmação na primeira abertura.
