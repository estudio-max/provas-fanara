# Curved Cover Task 5 — RED/GREEN e auto-revisão

## Status

Implementação concluída no worktree `editorial-app`, limitada a `capas.py`,
`motor.py`, `documento.py` e testes relevantes. Nenhuma alteração foi feita em
UI, CLI ou empacotamento.

## Baseline

- Worktree isolado confirmado: `GIT_DIR` em `.git/worktrees/editorial-app`,
  branch `feature/editorial-app`, sem submódulo.
- `python -m pytest tests/test_capa_curvas.py tests/test_enquadramento.py tests/test_identidade_capa.py -q`
  — 115 testes passaram em 13,7 s.
- `python -m pytest tests/test_capas_editoriais.py tests/test_motor_editorial.py -q`
  — 22 testes passaram em 7,4 s.
- `python -m pytest tests/test_end_to_end.py -q`
  — 13 testes passaram em 73,2 s.
- A primeira execução agregada excedeu 120 s. A investigação por arquivo
  demonstrou que não havia hang ou falha: o E2E isolado consumia cerca de 73 s.

## Ciclos RED → GREEN

1. **Contrato `CoverPhoto`**
   - RED: `ImportError: cannot import name 'CoverPhoto' from 'provas.capas'`.
   - GREEN: dataclass congelada mantém `id` e a imagem pertencente ao chamador.

2. **Composição 1–9 e layout correspondente**
   - RED: `capas.layout_orbita`/`gerar_curvas_editoriais` ausentes.
   - GREEN: nove parametrizações passaram; cada variante chama
     `layout_orbita(..., count)`, usa cada ID uma vez e marca
     `identity_embedded=True`.

3. **Associação segura e fallback**
   - RED: candidata insegura era mantida mesmo havendo alternativa segura e
     nenhum warning era emitido no fallback.
   - GREEN: candidatas seguras têm prioridade; quando nenhuma é segura, a
     melhor determinística é usada uma vez e produz
     `rosto_em_area_de_risco` em PT-BR.

4. **Ranking automático**
   - RED: orientação e metadados de qualidade/diversidade não alteravam a
     associação.
   - GREEN: o score considera proporção do slot, `quality`, `sharpness`,
     `exposure`, `density`, `similarity_group`, foco opcional e desempate
     estável com seed. Duas renderizações com a mesma seed produziram IDs,
     warnings e pixels idênticos.

5. **Ordem manual**
   - RED: uma foto posterior e segura deslocava a primeira escolha manual.
   - GREEN: miniaturas provenientes de `config.cover_ids` carregam a marca
     interna de ordem manual; essa ordem é autoritativa por slot, inclusive
     quando exige warning de rosto.

6. **IDs únicos e ownership**
   - RED: dois `CoverPhoto` com o mesmo ID geravam `used_photo_ids` repetido.
   - GREEN: IDs repetidos são rejeitados antes do render. Imagens fornecidas
     pelo chamador permanecem abertas e inalteradas; frames e máscaras
     temporárias são fechados nos caminhos normal e excepcional.

7. **Dispatch explícito**
   - RED: estilo desconhecido caía silenciosamente no mosaico e `gerar` não
     aceitava identidade/seed para curvas.
   - GREEN: dispatch somente `mosaico` ou `curvas_editoriais`; desconhecidos
     levantam a mensagem de validação já definida. O mosaico continua recebendo
     imagens Pillow simples e usa o mesmo compositor anterior.

8. **Documento sem identidade duplicada**
   - RED: `Documento.capa` não aceitava `identity_embedded`.
   - GREEN: a imagem continua full-page A4 horizontal e o método retorna antes
     de label, logo, título, subtítulo, contagem, chamada, nota e site legados.
     Metadados PDF (`title`, `author`, `subject`, `creator`) permanecem.

9. **Integração `_render_cover`**
   - RED: retornava `True`, descartava IDs/metadados/warnings e chamava sempre
     o mosaico.
   - GREEN: conserva `CoverPhoto`, injeta os metadados de `PhotoInfo`, usa
     `config.estilo_capa`, `IdentityData(config.titulo, config.estudio,
     config.site, config.logo)` e `plan.seed`, e retorna warnings ao motor.

10. **Regressão de fronteira bool/tuple**
    - RED reproduzido: a tupla vazia de warnings removia a capa da prévia e
      `int(tuple)` quebrava a exportação.
    - Causa raiz: consumidores ainda tratavam o novo retorno como booleano.
    - GREEN: presença da capa é testada por `is not None`; warnings vazios não
      alteram o page count.

11. **Diagnósticos, cache e fidelidade**
    - RED: preview era `tuple` sem warnings, `Resultado` não expunha warnings e
      o fingerprint não aceitava seed nem estilo.
    - GREEN: `PreviewResult` permanece compatível com tuple e carrega warnings;
      `Resultado.warnings` cobre exportação. Fingerprint inclui modo, seed,
      estilo, identidade e stat do logo. Prévia e PDF curvos são iguais pixel a
      pixel na largura comparada.

12. **Overflow**
    - Preview e export levantam `CoverTextOverflow` com a mensagem exata
      `O texto da capa não cabe. Abrevie o conteúdo antes de exportar.`;
      nenhum PDF parcial ou fallback para mosaico permanece.

13. **Logo corrompido na fronteira do documento (finding de revisão)**
    - RED: `gerar_preview` falhava em `_logo_document` com
      `PIL.UnidentifiedImageError` antes de a capa produzir o warning.
    - Causa raiz: o documento tentava abrir o logo para o overlay legado antes
      de `_render_cover`, e a exceção escapava.
    - GREEN: leitura/conversão são toleradas, logo e versão derivada são
      fechados em `finally`, o documento segue sem logo e o warning
      `logo_ilegivel` é deduplicado no boundary. Preview/export geram PDF tanto
      em mosaico quanto em curvas.

14. **API pública legada `motor.gerar` (finding de revisão)**
    - RED: `Config(estilo_capa="curvas_editoriais")` chamava `capas.gerar` com
      `list[Image]` e sem identidade, levantando `A capa curvas_editoriais exige
      os dados de identidade.`
    - GREEN: o caminho cria `CoverPhoto` com ID, seleciona no máximo nove
      fontes, passa `IdentityData`, seed e `identity_embedded`, fecha capa e
      miniaturas e devolve os warnings no `Resultado`. Com a configuração
      legada padrão em retrato, somente a capa incorporada usa A4 horizontal;
      a página interna permanece retrato.

## Verificações finais

- Comando-alvo exato do brief:
  `python -m pytest tests/test_capa_orbita.py tests/test_motor_editorial.py tests/test_capas_editoriais.py tests/test_end_to_end.py -q`
  — 59 testes passaram, 0 falhas, em 130,8 s.
- Suíte completa: `python -m pytest -q`
  — 293 testes passaram, 0 falhas, em 101,8 s.
- Pós-review: `python -m pytest tests/test_capa_orbita.py tests/test_motor_editorial.py tests/test_capas_editoriais.py tests/test_cli.py -q`
  — 68 testes passaram, 0 falhas, em 17,5 s. O E2E já verde não foi repetido
  neste gate curto.
- `git diff --check` — exit 0, sem whitespace errors.
- A regressão existente de mosaico passou no comando-alvo.
- Proof e clean incorporaram exatamente os mesmos bytes da capa curva; marca
  d'água continua restrita às fotos internas da prova.
- Trocar `mosaico` por `curvas_editoriais` manteve o mesmo `BookPlan` e pixels
  internos idênticos; somente a capa mudou.
- PDF de integração: duas páginas A4 horizontais (capa + uma página interna),
  page count correto e primeira página idêntica à prévia.

## Inspeção visual e recursos

- QA reproduzível renderizado em
  `tmp/visual-qa/task5-curved-cover.png` (fora do Git), 1600×1131, seed 47,
  seis fontes sintéticas mistas.
- Inspeção: bordas curvas antialias, núcleo central livre, título/estúdio
  legíveis, site na área segura, ausência de repetição e espaço de logo
  preservado. O warning `logo_ausente` foi o único diagnóstico, como esperado.
- A inspeção visual usou retratos sintéticos; proteção facial real permanece
  coberta pelos testes do detector/enquadrador da Task 3 e pelos testes
  injetáveis desta orquestração. Nenhuma imagem de QA foi adicionada ao Git.
- Auditoria de recursos: fontes caller-owned não são fechadas; fontes abertas
  pelo motor, redimensionamentos, frames, crops de máscara, máscaras, logo e
  canvas em erro são fechados por `finally`/context manager.

## Auto-revisão de escopo e compatibilidade

- `Capa` mantém defaults compatíveis e o caminho mosaico não incorpora
  identidade.
- `Documento.capa(..., identity_embedded=False)` preserva o comportamento
  legado.
- `PreviewResult` é subclasse de tuple para preservar indexação, iteração e
  conversão já usadas pela UI, sem modificar a UI nesta tarefa.
- `Resultado.warnings` foi acrescentado após campos/defaults existentes, sem
  quebrar construções posicionais atuais.
- Nenhum fallback silencioso, truncamento de identidade, repetição de foto ou
  mutação de `BookPlan` foi introduzido.
- Nenhuma alteração em UI, CLI, README, dependências ou packaging.

## Revisão independente

- Primeira revisão: nenhum Critical; dois Important.
- Important 1: logo existente corrompido bloqueava a fronteira antes do warning.
  Resolvido pelo ciclo 13 e regressão pública mosaico/curvas.
- Important 2: `motor.gerar` legado não fornecia o contrato da capa curva.
  Resolvido pelo ciclo 14 e regressão da API pública.
- Re-review pelo mesmo revisor: nenhum Critical/Important remanescente;
  `logo_ilegivel` não bloqueante e propagado em ambos os estilos, recursos
  fechados, API legada com A4 horizontal somente na capa e miolo retrato
  preservado. Assessment final: **Ready — Yes**.
