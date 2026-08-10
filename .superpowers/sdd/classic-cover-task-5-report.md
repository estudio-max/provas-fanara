# Capa Clássica — Task 5

## Status

Implementação concluída sobre a base `2259baa640d4321c19d53213ed8a6456e922d619`,
restrita à seleção única e ao editor transacional de recorte da Capa Clássica.

## RED → GREEN

- RED obrigatório: `python -m pytest tests/test_ui_state.py -k 'classic or crop' -q`
  falhou em 6 testes pelas APIs ausentes (`CropDialog`, métodos de estado e botão).
- RED de seleção única: `python -m pytest tests/test_ui_state.py -k 'single_selection' -q`
  falhou porque `CoverDialog.single_selection` ainda não existia.
- RED de clique rápido em worker: o segundo `run()` duplicava progresso e conclusão.
- RED de clique rápido no seletor: dois cliques programáticos em Escolher emitiam duas
  seleções.
- GREEN focado: 8 testes passaram com o filtro
  `classic or crop or single_selection or workers_publish`.
- GREEN da UI: `python -m pytest tests/test_ui_state.py -q` — 42 passaram.
- Regressões: `python -m pytest tests/test_capa_classica.py tests/test_projeto.py
  tests/test_motor_editorial.py -q` — 58 passaram.
- `python -m compileall -q provas/ui tests/test_ui_state.py` passou.
- `git diff --check` passou.

O lote que também incluía `tests/test_end_to_end.py` excedeu o timeout porque ficou
preso no caso legado `visual_qa.py --case curvas-editoriais`. Os dois processos exatos
foram encerrados; E2E visual/packaging final permanece fora do escopo desta task.

## Comportamento entregue

- A sidebar registra Clássica, Mosaico editorial e Curvas editoriais.
- `Ajustar enquadramento` só habilita para projeto com prévia pronta, estilo Clássica
  e operação ociosa.
- O seletor da Clássica escolhe uma foto sem slot e sem alterar `cover_ids`, plano,
  páginas, seed ou histórico de regeneração.
- Trocar a foto clássica restaura o recorte automático local dessa foto.
- O canvas usa `crop_box`/`resolve_classic_crop_box`, limita foco pela geometria,
  mantém a moldura preenchida e aceita arraste e setas.
- Zoom varia de 100% a 250%; o reset automático permanece em draft.
- Aplicar emite uma vez, persiste e solicita uma única prévia. Cancelar, Esc e fechar
  não alteram o projeto.
- Workers são single-shot e também honram interrupção de `QThread`; o protocolo de
  fechamento terminou com zero threads vivas no teste integrado.
- Falha de leitura da fotografia produz mensagem acionável em PT-BR sem alterar a
  prévia/projeto existente.

## QA visual real

Escala Qt `125%`, janela lógica `1093 × 614`, PNG físico `1366 × 768`. As fontes
`C:\Windows\Fonts\segoeui.ttf` e `segoeuil.ttf` foram registradas com sucesso via
`QFontDatabase` antes da captura offscreen.

Captura principal:

`C:\Users\estud\OneDrive\Imagens\RAW\provas-fanara\.worktrees\editorial-app\tmp\ui-qa\classic-cover-editor.png`

Captura auxiliar da mesa:

`C:\Users\estud\OneDrive\Imagens\RAW\provas-fanara\.worktrees\editorial-app\tmp\ui-qa\classic-cover-desk.png`

Inspeção via `view_image`:

- editor sem clipping; título, instrução, slider, percentual e ações integralmente
  visíveis;
- fotografia cobrindo toda a moldura a 165%, sem faixa vazia ou distorção;
- foco magenta visível no canvas e no controle ativo;
- hierarquia coerente com o desk escuro existente, Segoe UI e accent Fanara;
- mesa sem clipping: topo do bloco Capa a 10 px do viewport após scroll máximo;
- `Ajustar enquadramento` habilitado e acessível;
- `Exportar PDF` é a única ação visível com `objectName=primaryButton` na mesa;
- a prévia continua sendo a superfície dominante.

QA integrada adicional: setas alteraram o draft, Esc preservou o estado, reset
automático + Aplicar gerou exatamente uma solicitação de prévia e o fechamento deixou
`0` threads ativas.

## Considerações

- Quando não há `foto_capa_id` manual, o editor usa a primeira fonte válida da ordem
  persistida (seleção de capa/plano/projeto). A renderização final continua usando o
  seletor automático aprovado do motor. Expor o ID automático efetivamente renderizado
  no `PreviewResult` daria paridade explícita, mas alteraria o motor aprovado e ficou
  fora desta Task 5.
- Ícone Fanara, packaging e E2E final não foram implementados.
