# Aparência das páginas e nome do produto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar fundos Branco/Cinza/Preto e sombra suave opcional às páginas internas, persistir a escolha por álbum e renomear todos os pontos visíveis para Fanara - Fotolivro.

**Architecture:** O schema v4 guarda um identificador semântico de fundo separado de `cor_fundo`, que continua pertencendo à identidade das capas existentes. Um resolvedor puro entrega a paleta das páginas internas ao `Documento`; ele desenha sombra vetorial antes da foto. A UI apenas altera configuração e solicita a mesma fronteira de preview usada pelo PDF.

**Tech Stack:** Python 3.10+, PyMuPDF 1.24+, Pillow 10+, PySide6 6.7+, pytest, PyInstaller 6.x.

## Global Constraints

- Presets internos exatos: `branco=#FFFFFF`, `cinza=#D2D2D2`, `preto=#111215`.
- A capa e `Config.cor_fundo` não mudam ao escolher o fundo das páginas.
- Projetos novos e migrados usam `branco` e sombra desligada.
- Sombra: deslocamento máximo 5 pt, expansão máxima 3 pt, opacidade combinada abaixo de 16%.
- Sombra não altera fotografia, crop, proporção, marca d'água ou legenda e não invade outra foto.
- Preview e PDF usam o mesmo `Documento` e exibem pixels equivalentes.
- Nome visível exato: `Fanara - Fotolivro`.
- Artefatos Windows: `Fanara - Fotolivro.exe`, pasta `Fanara - Fotolivro`, ZIP `Fanara - Fotolivro-Windows.zip`.
- ZIP continua sem fotografias, logos, configs ou projetos do usuário.

---

### Task 1: Versionar aparência e resolver paletas internas

**Files:**
- Modify: `provas/motor.py`
- Modify: `provas/projeto.py`
- Modify: `provas/tema.py`
- Test: `tests/test_projeto.py`
- Test: `tests/test_motor_editorial.py`

**Interfaces:**
- Produces: `PAGE_BACKGROUNDS = MappingProxyType({"branco": "#FFFFFF", "cinza": "#D2D2D2", "preto": "#111215"})`.
- Produces: `tema.paleta_paginas(nome: str) -> Paleta`.
- Produces: `Config.fundo_paginas: str = "branco"` e `Config.sombra_fotos: bool = False`.

- [ ] **Step 1: Escrever REDs de defaults, validação e migração v3 → v4**

```python
def test_page_appearance_defaults_and_v3_migration(v3_payload):
    state = load_payload(v3_payload)
    assert state.config.fundo_paginas == "branco"
    assert state.config.sombra_fotos is False

@pytest.mark.parametrize("value", ["", "azul", "#fff"])
def test_page_background_rejects_unknown_values(value):
    with pytest.raises(ValueError, match="Fundo das páginas inválido"):
        Config(".", fundo_paginas=value)
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_projeto.py tests/test_motor_editorial.py -k "background or appearance or migration" -q`

Expected: FAIL por schema/campos/resolvedor ausentes.

- [ ] **Step 3: Implementar schema v4 e round-trip**

Elevar `PROJECT_SCHEMA_VERSION` para 4. Na migração v3, adicionar `fundo_paginas="branco"` e `sombra_fotos=False`; validar fundo por catálogo e normalizar sombra com `bool`. Preservar os campos no `asdict` já usado por `ProjectConfig`.

- [ ] **Step 4: Implementar paletas exatas e contraste**

```python
PAGE_BACKGROUNDS = MappingProxyType({
    "branco": "#FFFFFF", "cinza": "#D2D2D2", "preto": "#111215",
})

def paleta_paginas(nome: str) -> Paleta:
    try:
        return paleta(PAGE_BACKGROUNDS[nome])
    except KeyError as exc:
        raise ValueError("Fundo das páginas inválido.") from exc
```

Adicionar testes de razão WCAG: `texto`/`apagado` ≥4,5:1 no fundo; filete/moldura ≥3:1 quando usados como fronteira visual.

- [ ] **Step 5: Verificar e commit**

Run: `python -m pytest tests/test_projeto.py tests/test_motor_editorial.py tests/test_templates.py -q`

```powershell
git add provas/motor.py provas/projeto.py provas/tema.py tests/test_projeto.py tests/test_motor_editorial.py
git commit -m "feat: version internal page appearance"
```

---

### Task 2: Renderizar fundo e sombra vetorial

**Files:**
- Modify: `provas/motor.py`
- Modify: `provas/documento.py`
- Test: `tests/test_documento_editorial.py`
- Test: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: `tema.paleta_paginas(config.fundo_paginas)` e `config.sombra_fotos`.
- Produces: `Documento(..., sombra_fotos: bool = False)` aplicado somente às páginas internas.

- [ ] **Step 1: Escrever RED de seis combinações e invariantes**

Para os três fundos × sombra ligada/desligada, renderizar a mesma página e afirmar: fundo exato nos cantos; imagem JPEG e seu retângulo idênticos; capa idêntica; com sombra, desenhos aparecem somente atrás/ao redor da foto e não cruzam outro slot.

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_documento_editorial.py tests/test_end_to_end.py -k "page_background or photo_shadow" -q`

Expected: FAIL porque `Documento` usa uma única paleta e não desenha sombra.

- [ ] **Step 3: Separar paleta da capa e paleta interna**

Em motor, manter `tema.paleta(config.cor_fundo)` somente para capas existentes. Criar `page_palette = tema.paleta_paginas(config.fundo_paginas)` e passá-la ao `Documento` que renderiza páginas internas.

- [ ] **Step 4: Desenhar sombra antes de cada fotografia**

Criar helper privado que recebe o retângulo físico da foto e bounds seguros do slot. Desenhar três retângulos vetoriais sem borda, recortados aos bounds, antes de `insert_image`:

```python
layers = ((1.5, 1.5, .075), (3.0, 2.0, .045), (5.0, 3.0, .025))
for offset, expansion, opacity in layers:
    shadow = expanded_and_shifted(image_rect, expansion, offset).intersect(slot_bounds)
    page.draw_rect(shadow, color=None, fill=(0, 0, 0), fill_opacity=opacity)
```

Opacidade combinada é 14,5%; fundo preto não recebe brilho artificial. Aplicar também ao renderer legado.

- [ ] **Step 5: Verificar preview=PDF e commit**

Run: `python -m pytest tests/test_documento_editorial.py tests/test_motor_editorial.py tests/test_end_to_end.py -k "background or shadow or preview" -q`

```powershell
git add provas/motor.py provas/documento.py tests/test_documento_editorial.py tests/test_end_to_end.py
git commit -m "feat: render page backgrounds and photo shadows"
```

---

### Task 3: Adicionar controles de aparência na interface

**Files:**
- Modify: `provas/ui/sidebar.py`
- Modify: `provas/ui/main_window.py`
- Modify: `provas/ui/theme.qss`
- Test: `tests/test_ui_state.py`

**Interfaces:**
- Produces: `WorkflowSidebar.page_appearance_changed = Signal(str, bool)`.
- Produces: `MainWindow.set_page_appearance(background: str, shadow: bool) -> None`.

- [ ] **Step 1: Escrever RED de controles, estado e imutabilidade do plano**

Testar os três valores, acessibilidade, teclado, projeto não pronto, round-trip de UI e uma única solicitação de preview. A alteração preserva `BookPlan`, seed, capa, cover IDs, crop e scroll.

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_ui_state.py -k "page_appearance or shadow_control" -q`

Expected: FAIL por sinais/controles ausentes.

- [ ] **Step 3: Implementar seção compacta**

Adicionar `Aparência das páginas`, `QComboBox` com Branco/Cinza/Preto e `QCheckBox("Sombra suave nas fotos")`. Usar controles nativos, altura mínima 36 px, foco Fanara e estados disabled coerentes. Bloquear sinais em `set_page_appearance` para reabertura sem regeneração espúria.

- [ ] **Step 4: Atualizar projeto e preview**

`MainWindow.set_page_appearance` usa `replace` somente na config, zera previews e solicita preview uma vez quando o projeto está pronto e o valor realmente mudou.

- [ ] **Step 5: QA e commit**

Run: `python -m pytest tests/test_ui_state.py -q`

Capturar 1093×614 a 125% com Preto + sombra, confirmar scroll da sidebar, ausência de clipping e Exportar como única ação primária.

```powershell
git add provas/ui/sidebar.py provas/ui/main_window.py provas/ui/theme.qss tests/test_ui_state.py
git commit -m "feat: control internal page appearance"
```

---

### Task 4: Renomear o produto e artefatos Windows

**Files:**
- Modify: `provas/ui/main_window.py`
- Modify: `provas_cli.py`
- Modify: `empacotar.py`
- Modify: `verificar.py`
- Modify: `README.md`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_ui_packaging.py`
- Modify: `tests/test_end_to_end.py`

**Interfaces:**
- Produces: constante compartilhada `PRODUCT_NAME = "Fanara - Fotolivro"` em `provas/recursos.py`.
- Produces: pasta/EXE/ZIP com o nome exato aprovado.

- [ ] **Step 1: Escrever RED de todos os pontos visíveis**

Testar título e marca da janela, ajuda CLI, diagnóstico, README/LEIA-ME, nome PyInstaller, caminhos esperados, manifesto e ZIP. Fazer busca mutante que falha se os artefatos públicos ainda contiverem `Fotolivro.exe` ou `Fotolivro-Windows.zip` isolados.

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_cli.py tests/test_ui_packaging.py tests/test_end_to_end.py -k "product_name or package_name" -q`

- [ ] **Step 3: Centralizar nome e atualizar superfícies**

Importar `PRODUCT_NAME` na UI/CLI/verificador/empacotador; evitar literais divergentes. Usar o nome exato com espaços e hífen nos artefatos. Atualizar filtros de projeto e texto acessível sem renomear a extensão `.provas.json`.

- [ ] **Step 4: Atualizar privacidade e manifesto**

O inspetor deve resolver o novo prefixo e manter a mesma allowlist de recursos oficiais e bloqueio geral de arquivos do usuário.

- [ ] **Step 5: Verificar e commit**

Run: `python -m pytest tests/test_cli.py tests/test_ui_packaging.py tests/test_end_to_end.py -k "product_name or package" -q`

```powershell
git add provas/recursos.py provas/ui/main_window.py provas_cli.py empacotar.py verificar.py README.md tests/test_cli.py tests/test_ui_packaging.py tests/test_end_to_end.py
git commit -m "feat: rename product to Fanara Fotolivro"
```

---

### Task 5: E2E, QA visual e build final

**Files:**
- Modify: `tests/test_end_to_end.py`
- Modify: `tests/visual_qa.py`
- Modify: `tests/baselines/README.md`
- Modify only reproduced defects in production files.

- [ ] **Step 1: Criar matriz visual e funcional**

Cobrir três fundos × sombra on/off × Prova/Fotolivro, fotos verticais/horizontais/mistas, legendas longas, marca d'água, capa Clássica/Mosaico/Curvas, preview=PDF, persistência e capa/plan invariáveis.

- [ ] **Step 2: Gerar QA reproduzível**

Run: `python tests/visual_qa.py --case aparencia-paginas --dpi 120 --output tmp/visual-qa/aparencia-paginas`

Inspecionar overview e originais: fundo exato, contraste, sombra curta sem banding/invasão, legenda centralizada, proporção e capa intactas.

- [ ] **Step 3: Gates integrais**

Run: `python -m pytest -q`

Run: `python verificar.py`

Run: `git diff --check`

- [ ] **Step 4: Commit QA**

```powershell
git add tests/test_end_to_end.py tests/visual_qa.py tests/baselines/README.md
git commit -m "test: verify page appearance and product identity"
```

- [ ] **Step 5: Rebuild e teste externo**

Run: `python empacotar.py`

Run: `python -m pytest tests/test_end_to_end.py::test_packaged_zip_contains_verifiable_source_manifest tests/test_end_to_end.py::test_packaged_executable_generates_both_modes_outside_source_tree -q`

Expected: `Fanara - Fotolivro-Windows.zip`, manifesto no HEAD, SHA do EXE correto, zero dados privados e execução externa verde ou bloqueio Windows `4551` documentado com caminho/hash exatos.

---

## Final Gate

- [ ] Revisão independente do range completo.
- [ ] Corrigir todo finding Critical/Important por RED→GREEN e repetir revisão.
- [ ] Repetir suíte completa, verificador, rebuild e pós-build no HEAD final.
- [ ] Atualizar o Pull Request privado existente e manter draft até aprovação do usuário.
