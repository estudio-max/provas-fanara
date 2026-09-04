# Capa Clássica, recorte manual e identidade Fanara

## Objetivo

Adicionar uma terceira opção de capa, **Clássica**, inspirada na referência fornecida pelo usuário: uma fotografia, título no topo e fotógrafo/estúdio como subtítulo. A Capa Clássica será o padrão de projetos novos, terá seleção independente de fotografia e permitirá ajuste manual do recorte.

O mesmo escopo corrige a divergência atual em que mudanças de capa aparecem no PDF exportado, mas a grade de prévia continua exibindo a miniatura anterior.

## Diagnóstico confirmado da prévia

O motor gera corretamente a nova capa e o PDF consome essa renderização. O defeito está no cache da grade de prévia: a chave atual da capa contém apenas semente, modo, número, template e IDs de fotografias. Ela não contém estilo, identidade, fotografia da Capa Clássica nem recorte.

A reprodução isolada instalou primeiro uma capa vermelha e depois uma azul para o mesmo `BookPlan`; a segunda leitura permaneceu vermelha. Portanto, a correção deve ser feita na identidade do cache, não no renderer ou no exportador.

## Estilos de capa

O aplicativo passa a oferecer:

- **Clássica** (`classica`);
- **Mosaico editorial** (`mosaico`);
- **Curvas editoriais** (`curvas_editoriais`).

Projetos novos usam `classica`. Projetos existentes preservam o estilo salvo. Projetos antigos sem o campo de estilo continuam migrando para `mosaico`, evitando alteração visual retroativa.

As seleções são independentes:

- Clássica mantém uma fotografia própria;
- Mosaico e Curvas preservam a seleção múltipla existente;
- alternar estilos não apaga escolhas dos outros estilos.

## Composição A4 horizontal

A capa usa A4 horizontal, 297 × 210 mm, fundo branco e as proporções medidas na referência aprovada.

### Margens e posições

- margens laterais da fotografia: 8% da largura;
- topo do título: 6,1% da altura;
- topo do subtítulo: 14,1% da altura;
- topo da fotografia: 18,7% da altura;
- base da fotografia: 91,6% da altura;
- fotografia e textos centralizados no eixo horizontal.

### Tipografia

- título: **Bodoni Moda Regular**, 34 pt, caixa alta, alto contraste, alinhamento central;
- subtítulo: **Segoe UI Light**, 10 pt, caixa alta, alinhamento central e tracking equivalente a 0,26 em;
- título reduz automaticamente até 22 pt para caber entre as margens;
- se ainda não couber a 22 pt, a operação é bloqueada com mensagem PT-BR, sem renderização parcial;
- caracteres acentuados devem ser suportados integralmente.

A fonte Bodoni Moda será incluída como recurso redistribuível do aplicativo e do pacote Windows, acompanhada de sua licença SIL Open Font License. A renderização não dependerá de a fonte estar instalada no computador do usuário.

O estilo Clássica não mostra site ou logotipo sobre a capa. O campo fotógrafo/estúdio alimenta exclusivamente o subtítulo.

## Seleção da fotografia

Quando não houver seleção manual, o sistema escolhe automaticamente uma fotografia horizontal, priorizando qualidade, nitidez, exposição, diversidade e segurança facial. Se nenhuma horizontal válida existir, usa a melhor fotografia disponível.

No estilo Clássica, **Trocar fotos da capa** abre o seletor em modo de escolha única. A seleção é armazenada separadamente da lista múltipla usada por Mosaico e Curvas.

Se a fotografia escolhida desaparecer da pasta:

- o projeto preserva a referência salva;
- a prévia apresenta aviso não bloqueante;
- uma substituta automática é usada para permitir exportação;
- a substituta não altera o projeto; o usuário pode torná-la permanente pelo seletor de capa.

## Enquadramento automático e manual

O enquadramento automático usa a detecção facial local já existente. Ele calcula o menor recorte que cobre integralmente a moldura sem distorção, mantém rostos confiantes na área visível e escolhe o ponto focal mais equilibrado.

O botão **Ajustar enquadramento** abre um editor dedicado com a mesma proporção e geometria da área fotográfica do PDF.

### Interações

- arrastar reposiciona a fotografia;
- zoom varia de 100% a 250%;
- o mínimo real pode ser maior que 100% quando necessário para cobrir a moldura;
- a fotografia nunca pode deixar áreas vazias;
- **Enquadramento automático** restaura o cálculo protegido por rosto;
- **Aplicar** salva o recorte;
- **Cancelar** mantém integralmente o estado anterior;
- fechar a janela equivale a cancelar.

O ajuste manual é soberano. A detecção facial orienta o ponto inicial, mas não desfaz uma decisão manual aplicada pelo fotógrafo.

### Persistência do recorte

O projeto salva:

- ID da fotografia da Capa Clássica;
- ponto focal X normalizado entre 0 e 1;
- ponto focal Y normalizado entre 0 e 1;
- zoom normalizado entre o mínimo de cobertura e 2,5;
- modo `automatico` ou `manual`.

Valores fora do intervalo são normalizados durante a leitura. Dados ausentes usam enquadramento automático.

## Paridade entre prévia e PDF

Prévia, editor de recorte e exportação usam o mesmo compositor da Capa Clássica. Não haverá uma implementação visual aproximada exclusiva da interface.

A identidade de cache da capa inclui:

- estilo;
- título;
- fotógrafo/estúdio;
- fotografia selecionada e fingerprint do arquivo;
- ponto focal;
- zoom;
- modo automático ou manual;
- tamanho solicitado da miniatura;
- modo Prova ou Fotolivro quando ele alterar pixels.

Uma mudança em qualquer item invalida somente a capa. As páginas internas permanecem em cache e não são recompostas.

## Logotipo completo nas capas Mosaico e Curvas

O logotipo escolhido pelo fotógrafo é uma arte pronta e não recebe adaptação
automática ao fundo da capa. O renderer preserva seus RGB e não converte partes
da mesma marca em preto ou branco para obter contraste local.

- em imagens RGBA, pixels originalmente com alfa zero continuam transparentes;
- qualquer pixel originalmente visível (`alpha > 0`) torna-se chapado (`alpha = 255`);
- imagens RGB/opacas permanecem integralmente opacas, inclusive seu fundo próprio;
- não há cutout inferido por luminância, recoloração dependente do canvas nem
  criação de transparência em arquivo opaco;
- orientação EXIF, contenção sem distorção, warnings e ownership permanecem.

Esse contrato pertence ao logotipo completo do projeto nas capas Mosaico e
Curvas. Ele é independente da derivação abaixo, aplicada exclusivamente ao
símbolo oficial usado como ícone do software.

## Identidade Fanara no aplicativo

O arquivo fornecido `logoFanara Estudio SIMBOLO 2024.png` será convertido em
recurso mestre com transparência externa. Como o `ef` branco toca as bordas da
fonte, um flood-fill literal apagaria o próprio monograma. O alfa externo será
derivado por ajuste elíptico da silhueta convexa dos pixels rosa oficiais;
dentro dela, os RGB originais permanecem intactos e o monograma branco é
preservado mesmo quando conectado à borda.

A cor oficial do símbolo permanece RGB `218, 66, 101` (`#DA4265`).

Serão produzidos:

- PNG mestre transparente;
- ICO Windows multirresolução em 16, 20, 24, 32, 40, 48, 64, 128 e 256 px;
- ícone da janela e da barra de tarefas;
- marca de 32 px na barra superior, substituindo o “F” provisório;
- recursos correspondentes dentro do ZIP Windows.

O símbolo deve permanecer legível em 16 px, sem halo branco externo, serrilhado evidente ou alteração de cor.

## Persistência e migração

O schema de projeto será versionado para armazenar a fotografia e o recorte da Capa Clássica.

- projetos no schema atual migram sem alterar o plano interno, capa múltipla ou identidade;
- projetos antigos sem estilo continuam em Mosaico;
- novos projetos começam em Clássica;
- salvar e reabrir restaura estilo, fotografia, foco, zoom e modo de enquadramento;
- a migração é idempotente e não abre arquivos de imagem.

## Erros

- fotografia ilegível: aviso PT-BR e fallback automático, sem plano parcial;
- fonte ausente no pacote: verificador falha antes da execução distribuída;
- título impossível a 22 pt: erro PT-BR acionável e exportação atômica preservada;
- recorte inválido: normalização segura, sem áreas vazias;
- cancelamento do editor: nenhum campo do projeto é alterado;
- falha durante atualização da prévia: miniatura anterior permanece visível.

## Critérios de aceitação

1. Mudar entre Clássica, Mosaico e Curvas atualiza imediatamente a capa na prévia.
2. A primeira página do PDF corresponde pixel a pixel à prévia da capa para o mesmo tamanho de rasterização.
3. Projetos novos usam Clássica; projetos existentes mantêm o estilo salvo ou migram para Mosaico quando o campo não existe.
4. A foto automática prioriza horizontal; a escolha manual é respeitada.
5. Mosaico e Curvas mantêm sua seleção múltipla ao alternar estilos.
6. Arrastar, aplicar, cancelar, restaurar automático e zoom respeitam seus contratos.
7. Fotografias verticais e horizontais cobrem a moldura sem distorção ou áreas vazias.
8. Rostos próximos às bordas permanecem visíveis no enquadramento automático.
9. Títulos curtos, longos e acentuados obedecem margens e fitting tipográfico.
10. Salvar e reabrir preserva fotografia e recorte.
11. O ícone Fanara é legível e sem halo em todos os tamanhos exigidos.
12. Capturas visuais da capa, editor e UI em 1093 × 614 são inspecionadas.
13. Suíte completa, `verificar.py`, rebuild Windows, manifesto e execução fora da árvore passam antes da entrega.
14. O logotipo completo de Mosaico/Curvas mantém RGB e opacidade chapados,
    independentemente dos pixels claros ou escuros sob a marca.

## Ordem de implementação

1. corrigir a identidade do cache da capa;
2. implementar dados, migração e compositor Clássica;
3. implementar seleção única e editor de recorte;
4. aplicar a identidade Fanara e empacotamento;
5. executar E2E e QA visual;
6. retomar o ciclo determinístico das páginas internas na especificação separada `2026-08-09-ciclo-diagramacao-por-pagina-design.md`.

## Fora de escopo

- site ou logotipo sobre a Capa Clássica;
- múltiplas fotografias no estilo Clássica;
- apagar seleções dos outros estilos ao alternar;
- regeneração individual da capa pelo botão das páginas internas;
- versão macOS nesta etapa;
- ciclo de layouts das páginas internas, tratado em especificação própria.
