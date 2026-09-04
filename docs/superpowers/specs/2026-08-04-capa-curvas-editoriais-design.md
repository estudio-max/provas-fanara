# Capa Curvas Editoriais — Órbita Equilibrada

## Objetivo

Adicionar ao Fotolivro Editorial uma segunda opção de capa inspirada em composições fotográficas com máscaras curvas entrelaçadas. O novo estilo será adaptado ao A4 horizontal e coexistirá com o mosaico editorial atual. A alteração não modifica a regra do miolo: fotografias internas continuam inteiras, sem corte nem distorção.

## Estilos disponíveis

O projeto oferecerá dois estilos selecionáveis:

1. **Mosaico editorial** — estilo atual e compatível com projetos existentes.
2. **Curvas editoriais — Órbita equilibrada** — novo estilo com fotografias distribuídas ao redor de um núcleo central de identidade.

Projetos antigos sem o novo campo continuarão abrindo com `mosaico` como padrão. Trocar o estilo não refaz a análise das fotografias nem altera a sequência do miolo.

## Composição visual

A composição ocupará uma página A4 horizontal. Entre seis e nove fotografias serão encaixadas em máscaras curvas complementares, distribuídas ao redor de uma área central de respiro. A geometria deverá produzir movimento circular e assimétrico sem parecer uma grade.

O fundo usará a cor escura da paleta ativa. A área central conterá:

- título do ensaio em maior destaque;
- nome do fotógrafo ou estúdio em segundo nível;
- logotipo opcional no canto superior esquerdo;
- site no canto inferior direito.

Quando o logotipo não for fornecido, a composição preservará o espaço negativo e não exibirá placeholder. O resultado deverá permanecer equilibrado.

## Fotografias e enquadramento

A capa poderá recortar fotografias dentro das máscaras, pois é um elemento gráfico distinto. Esse recorte nunca será aplicado ao miolo.

A seleção automática continuará priorizando qualidade, diversidade visual e baixa semelhança. O novo compositor também considerará a adequação da fotografia à máscara. O enquadrador deverá:

- preservar a proporção original antes do recorte de preenchimento;
- evitar cortar rostos detectados com confiança;
- deslocar o enquadramento para manter rostos dentro da área segura;
- substituir a fotografia por outra selecionada quando não houver enquadramento seguro;
- nunca repetir a mesma fotografia na capa.

A detecção de rosto será local e não enviará imagens para serviços externos. Quando nenhum rosto for detectado com confiança, o enquadramento usará centro visual e área de interesse calculados localmente.

## Quantidades reduzidas

Pastas com uma a cinco fotografias continuarão produzindo capa válida. O compositor escolherá uma variante geométrica com menos máscaras e áreas maiores. Fotografias não serão repetidas para completar espaços. Áreas restantes serão absorvidas pelo fundo e pela identidade visual.

## Campos e persistência

O projeto armazenará:

- `cover_style`: `mosaico` ou `curvas_editoriais`;
- nome do fotógrafo ou estúdio;
- título do ensaio;
- site;
- caminho do logotipo opcional;
- seleção manual das fotografias da capa;
- semente já usada pela composição.

O esquema do projeto será migrado de forma compatível. O arquivo continuará referenciando fotografias e logotipo por caminho, sem incorporá-los ao JSON.

## Interface e fluxo

A barra lateral terá um seletor de estilo de capa e campos para fotógrafo/estúdio, título, site e logotipo. O usuário poderá escolher ou remover o logotipo.

O diálogo “Trocar fotos da capa” continuará substituindo uma fotografia por posição, com miniaturas visuais. As substituições manuais serão preservadas quando:

- a prévia for atualizada;
- o estilo de capa for trocado;
- o álbum inteiro for regenerado;
- o projeto for salvo e reaberto.

Ao trocar o estilo, somente a capa será renderizada novamente. O plano e a sequência interna permanecerão idênticos.

“Gerar outra diagramação” preservará estilo, textos, logotipo e fotografias escolhidas manualmente para a capa.

## Texto e validação

O compositor reduzirá o corpo do texto dentro de limites tipográficos definidos. Título, estúdio e site não poderão invadir fotos nem sair da área segura.

Se um texto continuar sem caber no menor tamanho permitido, a prévia exibirá um aviso e a exportação solicitará que o usuário abrevie o conteúdo. Nenhum texto será truncado silenciosamente.

Logotipos ilegíveis, ausentes ou incompatíveis serão ignorados com aviso não bloqueante. A capa permanecerá exportável sem logotipo.

## Arquitetura

A implementação será dividida em componentes isolados:

1. **Gerador de máscaras curvas** — produz a geometria vetorial/raster das variantes A4 horizontais e suas áreas seguras.
2. **Enquadrador de fotografias** — preenche máscaras, calcula áreas de interesse e protege rostos quando a detecção for confiável.
3. **Compositor de identidade** — posiciona título, estúdio, site e logotipo, aplicando limites tipográficos.
4. **Orquestrador de capa** — seleciona variante, associa fotografias às máscaras e retorna a imagem final e diagnósticos.

O motor de prévia e o exportador consumirão o mesmo resultado renderizado. Nenhum segundo algoritmo de capa será mantido na interface.

## Determinismo e regeneração

Com as mesmas fotografias, dados de identidade, estilo, substituições manuais e semente, a capa deverá ser idêntica. A regeneração do álbum altera a semente da composição interna, mas preserva as escolhas manuais e os dados da capa. O gerador poderá variar a associação automática de fotos somente quando não houver seleção manual para aquela posição.

## Testes

Os testes automatizados cobrirão:

- coexistência dos estilos mosaico e curvas editoriais;
- migração de projetos antigos para o padrão mosaico;
- determinismo pela semente;
- seis a nove fotografias sem repetição;
- variantes com uma a cinco fotografias;
- preservação de rostos em enquadramentos confiáveis;
- fallback quando não houver rosto detectado;
- título, estúdio e site longos;
- logotipo válido, ausente, removido e ilegível;
- persistência dos novos campos;
- troca manual por posição e preservação após regeneração;
- igualdade pixel a pixel entre prévia e página de capa exportada;
- A4 horizontal;
- funcionamento no executável Windows fora da árvore do código.

A regressão visual renderizará capas com retratos claros, escuros e mistos. Contact sheets serão inspecionados para equilíbrio, legibilidade, recortes de rosto, áreas vazias e coerência com a direção “Editorial equilibrado”. Imagens de QA permanecerão fora do Git; fixtures e sementes aceitas serão documentadas.

## Critérios de aceitação

A funcionalidade será aceita quando o usuário puder escolher “Curvas editoriais”, preencher identidade e logotipo, revisar a capa completa, trocar fotografias por posição, regenerar o álbum sem perder escolhas e exportar os dois modos com a mesma capa vista na prévia. O estilo mosaico deverá continuar funcionando sem regressões.
