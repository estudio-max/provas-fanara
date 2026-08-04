# Curved Cover — Task 2 Report

## Escopo entregue

- Criados `PixelRect`, `CurveSlot` e `CurveLayout` em
  `provas.capa_curvas`.
- Definida a tabela pública e imutável `ORBIT_VARIANTS`, indexada de 1 a 9,
  com exatamente uma região curva nomeada por fotografia.
- Implementado `layout_orbita(width, height, count)` com validação PT-BR,
  escala determinística, bounds dentro do canvas e núcleo central protegido.
- Implementado `render_mask(slot, size)` somente com Pillow, rasterizando os
  caminhos Bézier a 3× e reduzindo com LANCZOS.
- Variantes de 1 a 5 usam formas dominantes maiores e mantêm fundo deliberado;
  variantes de 6 a 9 preservam o núcleo normalizado
  `(0.38, 0.34, 0.24, 0.30)` e subdividem a órbita em regiões nomeadas.

Não foram implementados enquadramento, detecção de rostos, associação de
fotos, identidade, textos, motor, exportação ou interface.

## TDD

RED executado antes da criação do código de produção:

```text
python -m pytest tests/test_capa_curvas.py -q
ERROR tests/test_capa_curvas.py
ModuleNotFoundError: No module named 'provas.capa_curvas'
1 error (exit 1)
```

A falha ocorreu pelo motivo esperado: o contrato importado pelo teste ainda
não existia.

GREEN após a implementação mínima:

```text
python -m pytest tests/test_capa_curvas.py -q
24 passed (exit 0)
```

A primeira execução GREEN exibiu avisos de depreciação de `Image.getdata`
no próprio teste. O teste foi refatorado, ainda em estado verde, para usar
`get_flattened_data`; a execução fresca terminou sem warnings.

Cobertura adicionada:

- propriedades e interseção de `PixelRect`;
- counts 1–9, IDs únicos, slots visíveis e bounds seguros;
- imutabilidade da tabela e de cada definição;
- rejeição de dimensões não positivas, retrato, quadrado e count inválido;
- núcleo central exato nas variantes densas;
- máscara não retangular com pixels 0, 255 e antialias;
- determinismo byte a byte;
- snapshots de IDs, bounds e razão opaca em 1600×1131 para 6 e 9 fotos;
- snapshot proporcional menor em 800×566.

## Regressão e verificação

```text
python -m pytest tests/test_capas_editoriais.py -q
2 passed (exit 0)

python -m compileall -q provas/capa_curvas.py
exit 0

git diff --check
exit 0
```

## Autorrevisão

- Os caminhos são tuplas normalizadas pré-calculadas a partir de quatro
  segmentos Bézier; nenhuma fonte de aleatoriedade ou estado global mutável
  participa do layout ou da máscara.
- `MappingProxyType`, tuplas e dataclasses congelados impedem alteração das
  variantes publicadas.
- A escala arredonda as duas bordas de cada retângulo, evitando acumular erro
  entre origem e dimensão.
- A região central não é protegida apenas pela silhueta: os próprios bounds
  dos slots têm interseção de área zero, garantindo margem segura também para
  consumidores futuros.
- O diff cria somente o módulo geométrico, seus testes e este relatório; não
  altera o mosaico ou o miolo existente.

## Preocupações

- Nenhum bloqueio técnico conhecido nesta tarefa.
- A geometria deliberadamente não resolve enquadramento nem ordem de colagem;
  esses comportamentos pertencem às tarefas posteriores do plano.

## Correções após revisão

Commit-base revisado: `563f1b1`.

### RED/GREEN 1 — slots invisíveis em canvas mínimo

A investigação reproduziu bounds com largura ou altura zero em 2×1 e 3×2,
causados pelo arredondamento das frações normalizadas. O RED foi criado antes
da validação de produção:

```text
python -m pytest tests/test_capa_curvas.py -q
4 failed, 25 passed
```

Falharam exatamente os casos 2×1, 3×2, 15×11 e 16×10, que ainda retornavam
layout. Foram definidos `MIN_ORBIT_WIDTH = 16` e `MIN_ORBIT_HEIGHT = 11`;
dimensões menores agora são rejeitadas com mensagem PT-BR. O boundary 16×11
foi testado nas nove variantes: os 45 bounds têm área positiva e todas as
máscaras possuem pixels visíveis.

```text
python -m pytest tests/test_capa_curvas.py -q
29 passed
```

### RED/GREEN 2 — halo LANCZOS fora dos bounds

A redução LANCZOS espalhava pixels não zero até três pixels além do retângulo
declarado. O teste novo percorreu os 45 slots em 1600×1131 e 800×566:

```text
python -m pytest tests/test_capa_curvas.py::test_every_mask_antialias_halo_is_clipped_to_its_pixel_bounds -q
2 failed
```

O renderer passou a recortar o resultado reduzido estritamente ao
`slot.bounds`, preservando antialias interno e zerando o halo externo.

```text
python -m pytest tests/test_capa_curvas.py -q
31 passed
```

### RED/GREEN 3 — snapshots sensíveis à silhueta

A métrica de snapshot foi alterada de contagem de pixels totalmente opacos,
arredondada a uma casa, para soma de todas as intensidades dividida por
`255 * bounds.area`, arredondada a quatro casas. Antes de atualizar os valores
aprovados, os dois testes de snapshot falharam como esperado:

```text
python -m pytest tests/test_capa_curvas.py::test_representative_a4_geometry_snapshot tests/test_capa_curvas.py::test_nine_photo_and_smaller_proportional_geometry_snapshots -q
2 failed
```

Os snapshots agora preservam diferenças reais de shape, orientação,
arredondamento e tamanho (por exemplo, `0.7834`, `0.7840`, `0.7803`). Um guard
de sensibilidade substitui a folha por um retângulo mutante e exige diferença
de cobertura superior a 0,15; uma alteração substancial da silhueta aprovada
faz esse teste ou os snapshots precisos falharem.

### Verificação final da correção

```text
python -m pytest tests/test_capa_curvas.py -q
32 passed

python -m pytest tests/test_capas_editoriais.py -q
2 passed

git diff --check
exit 0
```

Autorrevisão da correção: o mínimo é validado antes da escala; nenhum slot
dummy foi introduzido; o clipping ocorre depois de 3×/LANCZOS; a métrica usa
todo o sinal antialias; e as mudanças continuam limitadas ao módulo
geométrico, seus testes e este relatório. Não restam preocupações conhecidas.
