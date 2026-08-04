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
