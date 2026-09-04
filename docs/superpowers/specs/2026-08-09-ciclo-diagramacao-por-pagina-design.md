# Ciclo determinístico de diagramação por página

## Objetivo

Permitir que o fotógrafo altere a diagramação de uma página interna isoladamente, diretamente em sua miniatura de prévia, mantendo as mesmas fotografias e sem modificar a capa ou qualquer outra página do álbum.

O usuário poderá clicar repetidamente no ícone de recarregar até escolher a composição desejada. O sistema percorrerá alternativas compatíveis sem repetição e voltará à primeira após esgotar o ciclo.

## Escopo funcional

- O controle aparece somente em páginas internas.
- A capa continua usando seus controles próprios.
- Cada clique mantém exatamente o conjunto de fotografias da página.
- As fotografias podem trocar de posição dentro da página para melhorar o equilíbrio editorial.
- Número, função narrativa e posição da página no álbum permanecem inalterados.
- Capa, páginas vizinhas, seleção manual da capa, modo de saída e semente geral permanecem inalterados.
- O botão global **Gerar outra diagramação** continua disponível e mantém seu comportamento atual.

## Ciclo de alternativas

Cada página recebe um catálogo ordenado de alternativas compatíveis, determinado por:

- quantidade de fotografias;
- combinação de orientações vertical e horizontal;
- proporção original das fotografias;
- função narrativa da página;
- diversidade em relação às páginas vizinhas.

O ciclo é determinístico: o mesmo estado de projeto produz sempre a mesma sequência de alternativas. O layout atual identifica a posição no ciclo; não é necessário um contador volátil separado.

Cada alternativa contém:

- um `template_id` compatível;
- uma permutação determinística dos mesmos `photo_ids`;
- geometria que preserva a proporção original e mostra cada fotografia inteira.

O sistema não repete uma alternativa até percorrer todas as combinações elegíveis. Depois da última, retorna à primeira.

Páginas com uma fotografia só exibem o controle quando houver ao menos duas composições profissionais perceptivelmente diferentes, como página inteira e imagem com respiro editorial. Se não houver alternativa real, o botão fica oculto.

## Arquitetura

### Catálogo de layouts

O registro de templates expõe uma consulta de compatibilidade independente da interface. Ela recebe o `PagePlan`, metadados das fotografias e contexto mínimo das páginas vizinhas, retornando alternativas ordenadas e imutáveis.

Novos templates poderão ser adicionados futuramente ao catálogo sem alterar a UI ou a persistência.

### Operação de domínio

Uma operação específica recebe `BookPlan`, número da página e metadados das fotografias. Ela retorna um novo `BookPlan` no qual somente o `PagePlan` solicitado foi substituído.

São invariantes obrigatórias:

- os mesmos `photo_ids` permanecem na página;
- nenhuma fotografia aparece ou desaparece do álbum;
- todas as outras páginas são estruturalmente idênticas;
- `cover_photo_ids`, `seed` e `mode` permanecem idênticos;
- a operação é determinística;
- uma falha não altera o plano anterior.

### Renderização isolada

O motor oferece uma operação para renderizar a miniatura de uma única página usando o mesmo compositor e as mesmas regras do PDF. Ela não reanalisa fotografias, não renderiza a capa e não recompõe o álbum.

Somente a chave de cache da página alterada é invalidada. A exportação continua consumindo o `BookPlan` completo, garantindo igualdade entre a prévia aprovada e o PDF.

## Interface

Cada `LazyPageThumbnail` interno recebe um botão discreto de recarregar no canto superior direito.

- Tooltip: **Mudar diagramação da página N**.
- Nome acessível: **Mudar diagramação da página N**.
- Disponível por teclado na ordem natural de tabulação.
- Visível ao passar o mouse ou receber foco; não compete visualmente com a fotografia.
- Não aparece na capa nem em páginas sem alternativas.

Durante a alteração:

- somente o controle daquela página fica desabilitado;
- a miniatura apresenta um estado breve de processamento;
- outras páginas e ações permanecem disponíveis;
- rolagem e zoom permanecem exatamente onde estavam;
- cliques adicionais para a mesma página são ignorados até a conclusão;
- operações em páginas diferentes são serializadas pelo controlador para evitar estados concorrentes.

Ao concluir, a miniatura é substituída no mesmo lugar. Em caso de erro, o plano e a imagem anteriores permanecem visíveis e um aviso PT-BR não bloqueante é apresentado.

O ciclo individual não altera o histórico global de **Desfazer**, reservado à regeneração do álbum inteiro. Para voltar a uma alternativa anterior, o usuário continua o ciclo.

## Persistência

O formato atual já persiste `template_id` e `photo_ids` de cada `PagePlan`. A alternativa escolhida será salva sem criar estado paralelo.

Ao reabrir o `.provas.json`, a ordem das fotos, o layout de cada página e todas as escolhas individuais devem ser restaurados exatamente. Projetos existentes continuam compatíveis.

## Erros e concorrência

- Página inexistente ou capa: erro de domínio em PT-BR, sem mutação.
- Ausência de alternativa: operação sem efeito; a UI não oferece o botão.
- Arquivo fotográfico indisponível: mantém plano/miniatura anterior e apresenta aviso.
- Clique repetido durante renderização: ignorado para a página ativa.
- Fechamento da janela: worker é cancelado e recursos são fechados antes da saída.

## Critérios de aceitação

1. Páginas com 1, 2 e 4 fotografias verticais, horizontais e mistas percorrem todas as alternativas compatíveis sem repetição.
2. O próximo layout e a permutação das fotos são determinísticos.
3. As mesmas fotografias permanecem na página, embora possam trocar de posição.
4. Capa e demais páginas permanecem byte a byte equivalentes em sua representação de plano.
5. Nenhuma fotografia é cortada, esticada ou deformada.
6. A prévia individual corresponde à mesma página no PDF exportado.
7. Salvar e reabrir preserva todas as escolhas individuais.
8. Vários cliques rápidos não criam corrida, repetição indevida ou plano parcial.
9. O botão é ocultado quando não existe alternativa real.
10. A interface permanece acessível e sem clipping em 840×540 e 1093×614.
11. Uma captura visual em 1093×614 confirma hierarquia profissional e prévia dominante.
12. Suíte completa, verificador, rebuild Windows e testes externos passam antes da entrega.

## Fora de escopo

- Trocar fotografias entre páginas.
- Adicionar ou remover fotografias do álbum.
- Galeria modal de layouts.
- Histórico individual separado ou botão adicional de desfazer por página.
- Regeneração individual da capa.
- Versão macOS nesta etapa.

## Estimativa

Esforço previsto: três a quatro dias de desenvolvimento, incluindo domínio, renderização isolada, UI, persistência, testes, QA visual e novo pacote Windows.
