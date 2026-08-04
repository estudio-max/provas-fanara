# Fotolivro editorial - especificação de design

Data: 3 de agosto de 2026
Status: aprovado em conversa, aguardando revisão do documento

## Objetivo

Evoluir o aplicativo Python `provas-fanara` para produzir fotolivros em PDF com qualidade editorial profissional. O aplicativo deve transformar uma pasta de fotografias em um PDF A4 horizontal, preservar integralmente o enquadramento 2:3 de cada imagem e oferecer duas modalidades de saída.

O trabalho reaproveitará o pipeline confiável já existente para leitura de JPG e RAW, orientação EXIF, marca d'água e exportação com PyMuPDF. O motor atual de grade fixa será substituído por um motor de sequência narrativa e templates editoriais curados.

## Público e plataforma

- Plataforma inicial: aplicativo Windows instalável.
- Público principal: fotógrafo trabalhando em monitor de mesa, frequentemente em ambiente de edição com pouca luz.
- Processamento totalmente local; nenhuma fotografia será enviada para serviços externos.
- A interface terá tema escuro, alto contraste e aparência de mesa de edição, não de formulário técnico.

## Modalidades de saída

### Prova para seleção

- Marca d'água gravada nos pixels de cada fotografia.
- Nome do arquivo, sem extensão, em uma faixa tipográfica reservada abaixo da imagem.
- A legenda nunca se sobrepõe à fotografia.
- A fotografia e sua legenda formam uma unidade visual.

### Fotolivro limpo

- Sem marca d'água.
- Sem nome do arquivo.
- O espaço da legenda desaparece e o template recalcula a área da fotografia.

As duas modalidades usam a mesma capa, sequência narrativa e família de templates. O usuário escolhe a modalidade antes de gerar a prévia e pode alterá-la sem analisar novamente a pasta.

## Formato e preservação das fotografias

- Página padrão: A4 horizontal, 297 × 210 mm.
- Fotografias esperadas: proporção 2:3, com orientação vertical ou horizontal; exemplos: 4016 × 6016 e 6016 × 4016.
- Nenhuma fotografia será distorcida, esticada, girada por efeito decorativo ou recortada.
- Uma fotografia horizontal em página A4 será exibida integralmente, mesmo que sobrem margens.
- Uma fotografia vertical nunca será ampliada ou cortada para simular uma imagem horizontal.
- Espaço negativo será tratado como elemento intencional da composição.
- Haverá margem de segurança para eventual impressão e encadernação. Rostos e elementos importantes não serão colocados junto à área central de dobra quando um template simular uma página dupla.

## Fluxo do usuário

1. Selecionar uma pasta de ensaio.
2. Analisar fotografias e exibir um resumo de arquivos válidos, ignorados, duplicados ou problemáticos.
3. Escolher `Prova para seleção` ou `Fotolivro limpo`.
4. Informar título, data e dados opcionais do estúdio.
5. Gerar automaticamente a capa e a sequência interna.
6. Visualizar miniaturas de todas as páginas.
7. Revisar a seleção automática da capa e substituir fotografias específicas, se necessário.
8. Usar `Gerar outra diagramação` para obter uma nova composição completa.
9. Exportar o PDF.

Não haverá editor livre de páginas na primeira versão. O usuário não moverá imagens nem trocará templates individualmente. Essa restrição preserva simplicidade e consistência editorial.

## Interface

A tela principal será uma mesa de edição com três regiões:

- Barra lateral esquerda: etapas do fluxo, tipo de saída e controles da capa.
- Área central: prévia paginada ou em grade, zoom e comando `Gerar outra diagramação`.
- Painel lateral direito: diagnóstico editorial, contagem de páginas, fotografias usadas, páginas de impacto, preservação aproximada da ordem e alertas.

A barra superior conterá nome do projeto, salvamento do projeto e `Exportar PDF`. A prévia será o elemento visual dominante. Ajustes avançados ficarão ocultos ou em uma seção secundária.

## Capa

- Estilo padrão: mosaico editorial com aproximadamente 6 a 12 fotografias principais.
- A seleção inicial será automática.
- O usuário poderá substituir qualquer fotografia selecionada antes da exportação.
- A seleção considerará nitidez, exposição, presença de rostos, variedade visual, orientação e distribuição ao longo do ensaio.
- Fotografias muito semelhantes receberão penalidade para evitar repetição no mosaico.
- O mosaico reservará uma área limpa e legível para título e data.
- As fotografias da capa poderão ser recortadas apenas dentro das células do mosaico, pois a capa é um elemento gráfico distinto. As páginas internas nunca terão recortes.

## Princípios editoriais

### Design invisível

A fotografia é protagonista. Não serão usados rotações decorativas, recortes de pessoas, molduras ornamentais, formas arbitrárias, sobreposições tipográficas chamativas ou efeitos que disputem atenção com as imagens.

### Cada página como unidade narrativa

Cada página deve funcionar como uma frase visual autossuficiente. As fotografias agrupadas devem ter relação temporal, temática ou visual, e não apenas dimensões compatíveis.

### Estrutura narrativa

O álbum será organizado em três movimentos:

1. Abertura: estabelece pessoas, ambiente ou contexto.
2. Desenvolvimento: organiza ações, variações e episódios do ensaio.
3. Encerramento: cria sensação deliberada de conclusão.

O motor preferirá a ordem natural dos nomes de arquivos, normalmente cronológica, mas poderá fazer reagrupamentos locais para construir páginas melhores. O deslocamento deve ser limitado para não destruir a narrativa original.

### Ritmo

- Páginas densas serão alternadas com páginas mais calmas.
- Não haverá mais de duas páginas densas consecutivas.
- Páginas de uma fotografia funcionarão como pontos de impacto ou pausa.
- Fotografias ambientais ou detalhes tranquilos poderão criar uma pausa sem depender apenas de espaço em branco.
- A mesma estrutura não poderá aparecer em páginas consecutivas.
- A abertura e o encerramento usarão tratamentos distintos das páginas intermediárias.

### Densidade de informação

- Planos abertos e fotografias com muitos elementos receberão mais área.
- Retratos fechados e detalhes poderão ocupar áreas menores como imagens de apoio.
- Em composições assimétricas, a imagem principal deverá carregar a narrativa e as menores deverão complementá-la.

## Biblioteca de templates

Serão aceitas páginas com 1, 2 ou 4 fotografias.

### Uma fotografia

- Imagem integral centralizada.
- Variações de escala e alinhamento controladas por orientação e função narrativa.
- Margens editoriais intencionais.
- No modo Prova, faixa de legenda abaixo da imagem.

### Duas fotografias

- Duas verticais, duas horizontais ou combinação mista.
- Priorização de pares complementares: ação e reação, pessoa e ambiente, visão geral e detalhe, ou duas poses relacionadas.
- Áreas iguais para pares equivalentes; hierarquia assimétrica quando uma imagem tiver maior densidade narrativa.

### Quatro fotografias

- Grade equilibrada ou composição assimétrica controlada.
- Pode representar sequência temporal, conjunto de detalhes ou uma imagem principal acompanhada por três imagens de apoio.
- Nenhuma fotografia poderá ficar pequena a ponto de comprometer leitura ou identificação.

Cada template declarará orientações aceitas, áreas disponíveis, hierarquia visual, margens, posição da legenda e adequação narrativa. O motor escolherá apenas templates compatíveis com o grupo de fotografias.

## Construção automática da sequência

O pipeline seguirá esta ordem:

1. Inventariar e validar arquivos.
2. Extrair metadados, orientação e miniaturas.
3. Calcular sinais de qualidade e conteúdo.
4. Identificar fotografias semelhantes e possíveis sequências temporais.
5. Dividir o ensaio em blocos narrativos.
6. Escolher abertura, desenvolvimento, pausas e encerramento.
7. Formar grupos de 1, 2 ou 4 fotografias relacionadas.
8. Selecionar templates compatíveis.
9. Avaliar o ritmo global e reparar repetições ou desequilíbrios.
10. Renderizar a prévia.

A análise de conteúdo usará sinais locais e explicáveis. A primeira versão não dependerá de inteligência artificial remota. Quando não for possível inferir conteúdo com confiança, orientação, proximidade temporal, similaridade visual e ordem dos arquivos terão prioridade.

## Regeneração

- Cada composição será identificada por uma semente aleatória.
- A mesma pasta, opções e semente devem reproduzir a mesma composição.
- `Gerar outra diagramação` criará uma nova semente e uma nova sequência válida.
- A composição anterior ficará disponível para desfazer.
- Regenerar não altera os arquivos originais nem a seleção manual da capa, salvo escolha explícita do usuário.

## Diagnóstico editorial

O painel de diagnóstico mostrará:

- número de fotografias encontradas e usadas;
- número estimado de páginas;
- distribuição entre páginas de 1, 2 e 4 fotos;
- percentual aproximado de preservação da ordem;
- alertas de imagens com baixa resolução, baixa nitidez ou erro de leitura;
- aviso quando a quantidade de fotografias produzir um álbum excessivamente longo.

O aplicativo não excluirá fotografias internas automaticamente por motivos estéticos. Alertas serão recomendações; por padrão, todas as fotografias válidas deverão aparecer exatamente uma vez nas páginas internas.

## Tratamento de erros

- Arquivos inválidos ou corrompidos serão listados sem interromper o restante do ensaio.
- RAW sem prévia incorporada será marcado como não processável.
- Duplicatas RAW + JPG com o mesmo nome-base continuarão aparecendo uma única vez, com preferência pelo JPG.
- A interface permanecerá responsiva durante análise e exportação.
- O usuário poderá cancelar operações longas.
- Arquivos temporários serão limpos após sucesso, cancelamento ou falha.
- Um PDF existente somente será substituído após confirmação.
- Falhas de exportação preservarão projeto, seleção de capa e composição.

## Persistência

Um arquivo de projeto armazenará pasta de origem, opções, dados da capa, seleção manual da capa, semente da composição e versão do esquema. O arquivo não duplicará as fotografias. Caso imagens sejam movidas ou removidas, o aplicativo indicará exatamente quais referências precisam ser corrigidas.

## Qualidade e testes

### Invariantes automáticos

- Todas as fotografias internas válidas aparecem exatamente uma vez.
- Nenhuma fotografia interna é cortada ou distorcida.
- Nenhuma legenda invade a imagem ou sai da página.
- Nenhum template recebe orientações incompatíveis.
- Não há templates iguais consecutivos.
- Não há mais de duas páginas densas consecutivas.
- A prévia e o PDF final usam a mesma especificação de layout.
- Regeneração com a mesma semente é determinística.

### Cenários de teste

- Pastas somente com JPG, somente com RAW e mistas.
- Fotografias verticais, horizontais e combinações variadas.
- Pastas pequenas, médias e com centenas de arquivos.
- Nomes longos, caracteres acentuados e numeração natural.
- Arquivos corrompidos, RAW sem prévia e duplicatas RAW + JPG.
- Modo Prova e modo Fotolivro limpo.
- Cancelamento durante análise e exportação.
- Regeneração, desfazer e reabertura de projeto.
- Exportação sobre arquivo existente.

### Verificação visual

PDFs representativos serão renderizados em imagens para verificar margens, proporções, legibilidade, ritmo, equilíbrio, capa, legendas e consistência entre prévia e saída. Casos de referência incluirão ensaios predominantemente verticais, predominantemente horizontais e mistos.

## Fora do escopo inicial

- Editor livre de páginas por arrastar e soltar.
- Ajuste manual de cada template.
- Sincronização em nuvem.
- Processamento remoto de fotografias.
- Versões web ou móveis.
- Formatos de página quadrados.
- Impressão direta ou integração com laboratórios.
- Seleção automática de quais fotografias internas devem ser excluídas.

## Critérios de sucesso

O projeto será considerado bem-sucedido quando um fotógrafo puder selecionar uma pasta, obter uma composição editorial coerente sem intervenção manual, revisar a capa e o álbum completo, regenerar uma alternativa e exportar os dois tipos de PDF. O resultado deverá parecer deliberadamente diagramado, preservar todas as fotografias internas e manter qualidade visual consistente em ensaios com diferentes combinações de orientação.
