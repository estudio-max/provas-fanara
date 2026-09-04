# Ciclo determinístico de diagramação por página — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que o usuário percorra, pelo ícone de recarregar de cada página interna, todas as diagramações compatíveis mantendo exatamente as mesmas fotos, com posições permutáveis, ciclo determinístico e persistência no projeto.

**Architecture:** Um módulo puro gerará a sequência finita de alternativas de uma página a partir do catálogo editorial, das proporções das fotos e da seed do álbum. O motor exporá uma operação isolada que altera e renderiza apenas uma página. A UI serializará pedidos, substituirá somente a miniatura afetada e manterá capa, scroll, zoom, histórico e demais páginas intactos. O `BookPlan` atualizado continuará sendo a fonte única para prévia, salvamento e PDF.

**Tech Stack:** Python 3.10+, Pillow 10+, PyMuPDF 1.24+, PySide6 6.7+, pytest.

## Global Constraints

- O controle existe somente em páginas internas; a capa nunca recebe o ícone.
- O conjunto de `photo_ids` da página não muda; a ordem pode mudar.
- Cada alternativa combina template compatível e uma permutação determinística das mesmas fotos.
- Nenhuma alternativa se repete antes de o ciclo completo terminar.
- O próximo estado depende somente de seed, página, fotos, proporções e estado atual.
- Templates futuros compatíveis entram automaticamente no ciclo pelo catálogo.
- Páginas com uma única alternativa não exibem controle ativo.
- Exportação e reabertura usam exatamente o `BookPlan` exibido.
- Enquanto uma troca está em processamento, cliques repetidos naquela página são ignorados.
- Operações globais que substituem o plano ficam desabilitadas durante a fila; zoom, scroll e visualização continuam disponíveis.

---

### Task 1: Criar o motor puro do ciclo de alternativas

**Files:**
- Create: `provas/ciclo_paginas.py`
- Test: `tests/test_ciclo_paginas.py`
- Read/Reuse: `provas/modelos.py`
- Read/Reuse: `provas/templates.py`

**Interfaces:**

- `alternativas_da_pagina(plan: BookPlan, page_number: int, aspect_ratios: Mapping[str, float])` retorna uma tupla imutável de `PagePlan`.
- `tem_alternativa(plan: BookPlan, page_number: int, aspect_ratios: Mapping[str, float]) -> bool`
- `ciclar_pagina(plan: BookPlan, page_number: int, aspect_ratios: Mapping[str, float]) -> BookPlan`

- [ ] **Step 1: Escrever REDs do contrato e invariantes**

Cobrir páginas com 1, 2 e 4 fotos; conjuntos vertical, horizontal e misto; template inexistente no estado inicial; página/capa inválida; ratio ausente.

```python
def test_cycle_keeps_exact_photo_set_and_may_change_order(case):
    states = walk_full_cycle(case.plan, case.page_number, case.ratios)
    expected = sorted(case.page.photo_ids)
    assert all(sorted(state.photo_ids) == expected for state in states)
    assert any(state.photo_ids != case.page.photo_ids for state in states)

def test_cycle_is_deterministic_and_has_no_repeat_before_wrap(case):
    first = alternativas_da_pagina(case.plan, case.page_number, case.ratios)
    second = alternativas_da_pagina(case.plan, case.page_number, case.ratios)
    assert first == second
    assert len(first) == len(set((p.template_id, p.photo_ids) for p in first))

def test_future_compatible_template_enters_cycle(monkeypatch, case):
    monkeypatch.setattr("provas.ciclo_paginas.catalogo", catalog_with_new_compatible_template())
    assert "future_four" in {
        p.template_id for p in alternativas_da_pagina(case.plan, case.page_number, case.ratios)
    }
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_ciclo_paginas.py -q`

Expected: FAIL na coleta porque `provas.ciclo_paginas` ainda não existe.

- [ ] **Step 3: Implementar compatibilidade e ordenação determinística**

1. Encontrar a página interna por `number`; rejeitar capa e número ausente com `ValueError` PT-BR.
2. Filtrar o catálogo pelo número exato de slots.
3. Excluir templates que repetem imediatamente o template da página anterior ou seguinte e combinações que criariam mais de duas páginas `dense` consecutivas.
4. Gerar permutações dos `photo_ids` sem duplicatas.
5. Pontuar cada foto/slot pela distância absoluta entre `log(aspect_ratio_foto)` e `log(aspect_ratio_slot)`.
6. Para cada template, manter a permutação de menor custo; desempatar por BLAKE2b de `seed|page_number|template_id|photo_ids`. Isso mantém o ciclo curto e profissional, mas ainda permite trocas de posição entre layouts assimétricos.
7. Ordenar primeiro por adequação ao papel narrativo e densidade dos vizinhos, depois pelo mesmo hash estável; nunca usar `hash()` do Python. `opening`/`ending` favorecem hierarquia alta; `sequence`/`narrative` evitam repetir a classe de densidade dominante nos vizinhos.
8. Preservar `number` e `role`; mudar somente `template_id` e `photo_ids`.

- [ ] **Step 4: Implementar avanço e volta do ciclo**

Se o estado atual estiver na sequência, retornar o seguinte com módulo `len(sequence)`. Se não estiver (plano legado ou primeira entrada), retornar a primeira alternativa. `tem_alternativa` compara pares únicos `(template_id, photo_ids)` e só retorna `True` com pelo menos dois.

O estado atual é incluído na sequência quando continua compatível, mesmo se sua permutação não for a melhor calculada para aquele template. Assim o primeiro clique nunca volta silenciosamente ao próprio estado e o wrap sempre retorna a uma alternativa conhecida.

- [ ] **Step 5: Verificar propriedades e regressões do planejador**

Run: `python -m pytest tests/test_ciclo_paginas.py tests/test_planejador.py tests/test_templates.py -q`

Expected: PASS; o planejador global permanece inalterado.

- [ ] **Step 6: Commit**

```powershell
git add provas/ciclo_paginas.py tests/test_ciclo_paginas.py
git commit -m "feat: cycle compatible page layouts"
```

---

### Task 2: Expor troca e renderização isoladas no motor

**Files:**
- Modify: `provas/motor.py`
- Modify: `provas/ui/workers.py`
- Test: `tests/test_motor_editorial.py`
- Test: `tests/test_ui_state.py`

**Interfaces:**

- `PageCycleResult` é um dataclass congelado com `plan: BookPlan`, `page_number: int` e `thumbnail: Image.Image`.
- `ciclar_preview_pagina(config: Config, plan: BookPlan, page_number: int, preview_width: int) -> PageCycleResult`.

`PageCycleWorker(config, plan, page_number, preview_width)` emite `completed(PageCycleResult)` e `failed(str)`.

- [ ] **Step 1: Escrever RED da operação isolada**

```python
def test_page_cycle_renders_only_selected_page(case, monkeypatch):
    opened = []
    monkeypatch.setattr("provas.motor._open_photo", tracking_loader(opened))
    result = ciclar_preview_pagina(case.config, case.plan, 3, 720)
    assert set(opened) == set(case.plan.pages[2].photo_ids)
    assert result.plan.pages[:2] == case.plan.pages[:2]
    assert result.plan.pages[3:] == case.plan.pages[3:]
```

Adicionar casos `prova`/`limpo`, nomes longos, erro de arquivo, cancelamento e paridade visual com a mesma página do PDF.

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_motor_editorial.py -k page_cycle -q`

Expected: FAIL por API ausente.

- [ ] **Step 3: Implementar fronteira do motor**

- Carregar apenas fotos da página solicitada e extrair ratios de dimensões.
- Chamar `ciclar_pagina` para criar um novo `BookPlan` imutável.
- Renderizar a página com o mesmo compositor usado por preview completo/PDF.
- Aplicar marca d'água e legenda somente no modo prova.
- Fechar todas as imagens temporárias em `finally`.
- Nunca recalcular capa, análise, seleção de fotos ou outras páginas.

- [ ] **Step 4: Implementar worker cancelável**

O worker captura exceções em mensagem PT-BR, fecha recursos no próprio thread e não emite resultado depois de cancelado. O objeto resultado atravessa o sinal sem manter imagens-fonte abertas.

- [ ] **Step 5: Verificar motor e threads**

Run: `python -m pytest tests/test_motor_editorial.py tests/test_ui_state.py -k "page_cycle or worker" -q`

Expected: PASS, sem thread viva ao fechar a janela de teste.

- [ ] **Step 6: Commit**

```powershell
git add provas/motor.py provas/ui/workers.py tests/test_motor_editorial.py tests/test_ui_state.py
git commit -m "feat: render one cycled page preview"
```

---

### Task 3: Adicionar o ícone de recarregar aos cards internos

**Files:**
- Modify: `provas/ui/preview_grid.py`
- Modify: `provas/ui/theme.qss`
- Test: `tests/test_ui_state.py`

**Interfaces:**
- `PreviewGrid.page_layout_requested = Signal(int)`.
- `PreviewGrid.set_page_busy(page_number: int, busy: bool) -> None`.
- `PreviewGrid.replace_page_preview(page_number: int, image: Image.Image) -> None`.
- `PreviewGrid.set_page_alternatives(page_numbers: Collection[int]) -> None`.

- [ ] **Step 1: Escrever RED de estrutura, acesso e estado**

```python
def test_only_internal_pages_with_alternatives_have_reload_button(grid_with_cover):
    assert grid_with_cover.card(0).reload_button is None
    assert grid_with_cover.card(1).reload_button.isVisible()
    assert not grid_with_cover.card(2).reload_button.isEnabled()

def test_reload_button_emits_page_number(qtbot, grid):
    with qtbot.waitSignal(grid.page_layout_requested) as signal:
        qtbot.mouseClick(grid.card(3).reload_button, Qt.LeftButton)
    assert signal.args == [3]
```

Também testar nome acessível, tooltip, foco por teclado, busy spinner/disabled, troca pontual sem recriar cards e preservação do scroll.

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_ui_state.py -k "reload or replace_page" -q`

Expected: FAIL por controle e sinais ausentes.

- [ ] **Step 3: Implementar microinteração profissional**

- Botão circular de 28 px no canto superior direito, sobre uma placa branca translúcida.
- Ícone Unicode `↻` desenhado pela fonte de interface, sem novo arquivo gráfico.
- Tooltip e accessible name: `Mudar diagramação da página N`.
- Hover e foco com cor Fanara `#DA4265`; estado ocupado com rotação ou indicador discreto.
- Reservar área para o botão sem encobrir conteúdo essencial; continuar legível a 125% de escala.

- [ ] **Step 4: Substituir somente o bitmap do card**

`replace_page_preview` atualiza a imagem do card e a entrada LRU correspondente, preservando instância do widget, geometria, scroll, zoom e lazy-loading dos demais cards.

- [ ] **Step 5: Verificar UI focada**

Run: `python -m pytest tests/test_ui_state.py -q`

Expected: PASS; capa permanece sem botão e páginas sem alternativa ficam sem ação ativa.

- [ ] **Step 6: Commit**

```powershell
git add provas/ui/preview_grid.py provas/ui/theme.qss tests/test_ui_state.py
git commit -m "feat: add per-page layout controls"
```

---

### Task 4: Orquestrar fila, histórico e persistência na janela principal

**Files:**
- Modify: `provas/ui/main_window.py`
- Modify: `provas/projeto.py`
- Test: `tests/test_ui_state.py`
- Test: `tests/test_projeto.py`

**State:**

```python
self._page_cycle_queue: deque[int]
self._page_cycle_worker: PageCycleWorker | None
self._page_cycle_thread: QThread | None
self._page_cycle_busy: set[int]
```

- [ ] **Step 1: Escrever REDs de fluxo e corrida**

Cobrir clique simples, cliques rápidos na mesma página, pedidos em três páginas distintas, erro em uma página, fechamento durante operação, ação global durante fila, undo/regeneração posterior e reabertura.

```python
def test_three_page_requests_are_serialized_and_preserve_other_pages(window, qtbot):
    before = window.current_plan
    request_pages(window, qtbot, [2, 5, 8])
    wait_until_idle(window, qtbot)
    assert changed_page_numbers(before, window.current_plan) == {2, 5, 8}

def test_saved_project_reopens_exact_cycled_plan(window, project_path, qtbot):
    cycle_page(window, qtbot, 3, times=2)
    expected = window.current_plan.pages[2]
    window.save_project(project_path)
    reopened = open_project(project_path)
    assert reopened.plan.pages[2] == expected
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_ui_state.py tests/test_projeto.py -k "page_cycle or cycled" -q`

Expected: FAIL por orquestração ausente.

- [ ] **Step 3: Implementar fila serializada**

- Ignorar clique se a mesma página estiver em `_page_cycle_busy` ou já enfileirada.
- Processar uma página por vez; ao concluir, trocar `current_plan`, thumbnail e estado do projeto antes de iniciar a próxima.
- Em erro, restaurar botão, exibir diagnóstico e continuar a fila.
- Desabilitar `Gerar outra diagramação`, abrir pasta/projeto e troca de modo/estilo durante a fila; manter zoom/scroll.
- Cancelar worker/thread no fechamento usando o mesmo protocolo seguro dos workers existentes.

- [ ] **Step 4: Calcular disponibilidade sem análise completa**

Após preview completo ou reabertura, derive ratios do diagnóstico já existente e chame `tem_alternativa` por página. Ao trocar uma página, recalcule somente sua disponibilidade.

- [ ] **Step 5: Persistir pelo `BookPlan` existente**

Não criar contador separado de cliques. `template_id` e `photo_ids` do `PagePlan` já representam o estado escolhido e devem ser serializados. Acrescentar apenas validação de que todas as fotos de cada página pertencem ao projeto e que o template existe/tem a aridade correta.

- [ ] **Step 6: Verificar integração e reabertura**

Run: `python -m pytest tests/test_ui_state.py tests/test_projeto.py tests/test_motor_editorial.py -q`

Expected: PASS; salvar/reabrir preserva a alternativa exata e operações globais continuam funcionando depois da fila.

- [ ] **Step 7: Commit**

```powershell
git add provas/ui/main_window.py provas/projeto.py tests/test_ui_state.py tests/test_projeto.py
git commit -m "feat: persist per-page layout choices"
```

---

### Task 5: E2E, QA visual, documentação e pacote

**Files:**
- Modify: `tests/test_end_to_end.py`
- Modify: `tests/visual_qa.py`
- Modify: `README.md`
- Modify if required by source fingerprint: `empacotar.py`

- [ ] **Step 1: Escrever matriz E2E**

Casos mínimos: 1/2/4 fotos; todas verticais, todas horizontais e mistas; modo prova/limpo; primeira alternativa, ciclo completo e wrap; três páginas alteradas em álbum de dez; persistência; preview=PDF; capa imutável.

- [ ] **Step 2: Confirmar que o teste mata mutações reais**

Aplicar temporariamente mutações locais e reverter cada uma depois do RED:
- ordenar com `hash()` em vez de BLAKE2b;
- descartar a permutação de fotos;
- reusar o estado anterior antes do wrap;
- renderizar novamente o álbum inteiro.

- [ ] **Step 3: GREEN da matriz**

Run: `python -m pytest tests/test_end_to_end.py -k page_cycle -q`

Expected: PASS com fingerprint perceptual/stream da página alterada e igualdade exata das demais páginas.

- [ ] **Step 4: Documentar uso**

Adicionar ao README: ícone `↻`, mesmas fotos, posições permutáveis, ciclo compatível, somente páginas internas, persistência e comportamento de páginas sem alternativa.

- [ ] **Step 5: Gerar QA visual real**

Run: `python tests/visual_qa.py --case ciclo-paginas --dpi 120 --output tmp/visual-qa/ciclo-paginas`

Capturar a interface em 1093×614 e 125%, com uma página normal, uma ocupada e uma sem alternativa. Inspecionar botão, contraste, clipping, hierarquia e preservação do scroll.

- [ ] **Step 6: Gates integrais**

Run: `python -m pytest -q`

Run: `python verificar.py`

Run: `git diff --check`

Expected: 100%, exit code 0, sem warnings próprios.

- [ ] **Step 7: Commit**

```powershell
git add tests/test_end_to_end.py tests/visual_qa.py README.md empacotar.py
git commit -m "test: verify per-page layout cycling"
```

- [ ] **Step 8: Rebuild e teste externo**

Run: `python empacotar.py`

Run: `python -m pytest tests/test_end_to_end.py::test_packaged_zip_contains_verifiable_source_manifest tests/test_end_to_end.py::test_packaged_executable_generates_both_modes_outside_source_tree -q`

Expected: manifesto aponta HEAD; SHA do EXE confere; ZIP sem fotos/logos/projetos do usuário; executável funciona fora da árvore.

---

## Final Gate

- [ ] Revisão independente do merge-base até HEAD.
- [ ] Corrigir todos os findings Critical/Important por RED→GREEN e repetir a revisão.
- [ ] Repetir suíte completa, `verificar.py`, rebuild e testes pós-build sobre o HEAD final.
- [ ] Atualizar o Pull Request privado existente, mantendo-o como draft até a aprovação do usuário.
