# Legendas editoriais do modo Prova

## Objetivo

Remover a aparência de tarja técnica dos nomes de arquivo e tratá-los como
legendas editoriais discretas, individualmente associadas a cada fotografia.

## Comportamento aprovado

- A mudança vale somente para o modo `prova`; o fotolivro limpo continua sem
  nomes de arquivo.
- Cada nome é centralizado horizontalmente pelo eixo da própria fotografia,
  nunca pelo eixo da página ou da célula abstrata.
- A área reservada abaixo da fotografia permanece, evitando sobreposição e
  alterações na proporção original da imagem.
- A legenda não possui retângulo, faixa, cápsula ou qualquer preenchimento de
  fundo. O fundo visível é o próprio fundo da página.
- O texto usa a cor secundária discreta já definida pela paleta editorial e a
  tipografia sem serifa existente.
- Nomes longos continuam abreviados com elipse e nunca escapam da largura da
  própria fotografia.
- Todos os caminhos de renderização de páginas internas aplicam a mesma regra,
  garantindo igualdade entre prévia e PDF exportado.

## Implementação

O compositor de `Documento` deve deixar de pintar o painel da legenda e deve
calcular o ponto central a partir do retângulo físico da foto. A largura
disponível para fitting será a largura da fotografia, descontado um pequeno
respiro lateral. O renderer legado de cartão seguirá exatamente o mesmo
contrato para não criar uma segunda aparência.

Nenhuma mudança será feita em capa, marca d'água, seleção de fotos, templates,
altura reservada para legenda ou modo Fotolivro.

## Verificação

- Teste estrutural garante ausência de desenho preenchido na área da legenda.
- Teste geométrico garante que o centro do texto coincide com o centro da foto.
- Teste de nome longo garante fitting dentro da largura da foto.
- PDF de prova representativo será renderizado em PNG e inspecionado quanto a
  alinhamento, espaçamento, contraste e ausência da faixa.
- Regressões confirmam que o modo Fotolivro permanece sem legenda e que a
  prévia continua usando o mesmo renderer do PDF.
