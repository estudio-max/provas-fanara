# Capa Clássica e identidade Fanara — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir a capa obsoleta na prévia, adicionar a Capa Clássica A4 horizontal com foto única e recorte manual, e aplicar o símbolo oficial Fanara ao aplicativo e pacote Windows.

**Architecture:** A identidade do cache da capa será separada do cache das páginas internas. Um novo módulo puro `capa_classica.py` concentrará geometria, seleção, crop e renderização; o motor continuará sendo a única fronteira usada por preview e PDF. A UI persistirá foto/foco/zoom no schema v3 e usará um editor dedicado que só grava ao aplicar.

**Tech Stack:** Python 3.10+, Pillow 10+, PyMuPDF 1.24+, PySide6 6.7+, OpenCV headless 4.10 até antes da versão 5, pytest, PyInstaller 6.x.

## Global Constraints

- Formato de página: A4 horizontal, 297 × 210 mm.
- Estilos válidos: `classica`, `mosaico`, `curvas_editoriais`.
- Novos projetos usam `classica`; projetos v1/v2 sem estilo migram para `mosaico`.
- Capa Clássica: margens laterais 8%; título Y 6,1%; estúdio Y 14,1%; foto de Y 18,7% a 91,6%.
- Título: Bodoni Moda Regular 34 pt, mínimo 22 pt; estúdio: Segoe UI Light 10 pt, tracking 0,26 em.
- Crop manual: foco X/Y em `[0, 1]`, zoom até `2.5`, nenhuma área vazia.
- A foto Clássica é independente de `cover_ids` usados por Mosaico/Curvas.
- Nenhuma fotografia, logo de cliente, `config.json` ou `.provas.json` pode entrar no ZIP.
- O símbolo oficial preserva `#DA4265` e o monograma branco; somente o branco conectado às bordas vira transparência.
- Preview e primeira página do PDF devem usar o mesmo renderer.

---

### Task 1: Corrigir a identidade do cache da capa

**Files:**
- Modify: `provas/ui/preview_grid.py`
- Test: `tests/test_ui_state.py`

**Interfaces:**
- Consumes: `PreviewGrid.set_previews(plan: BookPlan, images: Iterable[object])`.
- Produces: capa sempre atualizada; cache LRU permanece ativo para páginas internas.

- [ ] **Step 1: Escrever o RED que reproduz o defeito**

```python
def test_cover_preview_never_reuses_stale_pixels_for_same_plan(qapp, plan):
    grid = PreviewGrid()
    first = (Image.new("RGB", (420, 297), "red"), *internal_images(plan))
    second = (Image.new("RGB", (420, 297), "blue"), *internal_images(plan))
    grid.set_previews(plan, first)
    grid.set_previews(plan, second)
    assert grid._images[0].pixelColor(1, 1).name() == "#0000ff"
```

- [ ] **Step 2: Confirmar que o RED falha pela chave atual**

Run: `python -m pytest tests/test_ui_state.py::test_cover_preview_never_reuses_stale_pixels_for_same_plan -q`

Expected: FAIL com `#ff0000 != #0000ff`.

- [ ] **Step 3: Não reutilizar cache de páginas para a entrada `cover`**

```python
for page, source in zip(self._entries, sources):
    if page.role == "cover":
        image = _to_qimage(source)
    else:
        cache_key = (plan.seed, plan.mode, page.number, page.template_id, page.photo_ids)
        cached = self._pixmap_cache.get(cache_key)
        image = cached if cached is not None else _to_qimage(source)
        self._pixmap_cache[cache_key] = image
        self._pixmap_cache.move_to_end(cache_key)
    converted.append(image)
```

- [ ] **Step 4: Verificar capa nova e cache interno preservado**

Run: `python -m pytest tests/test_ui_state.py -q`

Expected: PASS; o teste de LRU/lazy loading existente continua verde.

- [ ] **Step 5: Commit**

```powershell
git add provas/ui/preview_grid.py tests/test_ui_state.py
git commit -m "fix: refresh changed cover previews"
```

---

### Task 2: Versionar configuração da Capa Clássica

**Files:**
- Modify: `provas/capas.py`
- Modify: `provas/motor.py`
- Modify: `provas/projeto.py`
- Test: `tests/test_projeto.py`
- Test: `tests/test_motor_editorial.py`

**Interfaces:**
- Produces: `Config.foto_capa_id`, `capa_foco_x`, `capa_foco_y`, `capa_zoom`, `capa_enquadramento`.
- Produces: schema `PROJECT_SCHEMA_VERSION = 3` com migração v1/v2 idempotente.

- [ ] **Step 1: Escrever testes de defaults, validação e migração**

```python
def test_new_projects_default_to_classic_cover(tmp_path):
    config = ProjectConfig(pasta=str(tmp_path))
    assert config.estilo_capa == "classica"
    assert (config.capa_foco_x, config.capa_foco_y, config.capa_zoom) == (0.5, 0.5, 1.0)
    assert config.capa_enquadramento == "automatico"

def test_v2_project_keeps_mosaic_when_classic_fields_are_absent(tmp_path, v2_payload):
    v2_payload["config"]["estilo_capa"] = "mosaico"
    state = load_payload(tmp_path, v2_payload)
    assert state.config.estilo_capa == "mosaico"
    assert state.config.foto_capa_id == ""

def test_crop_values_are_normalized():
    config = ProjectConfig(pasta="x", capa_foco_x=-2, capa_foco_y=4, capa_zoom=8)
    assert (config.capa_foco_x, config.capa_foco_y, config.capa_zoom) == (0.0, 1.0, 2.5)
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_projeto.py tests/test_motor_editorial.py -q`

Expected: FAIL para estilo `classica`, campos e schema 3 ausentes.

- [ ] **Step 3: Ampliar estilos e campos serializáveis**

```python
COVER_STYLES = ("classica", "mosaico", "curvas_editoriais")

@dataclass
class Config:
    estilo_capa: str = "classica"
    foto_capa_id: str = ""
    capa_foco_x: float = 0.5
    capa_foco_y: float = 0.5
    capa_zoom: float = 1.0
    capa_enquadramento: str = "automatico"
```

Aplicar os mesmos campos em `ProjectConfig`; em `__post_init__`, usar `object.__setattr__` para limitar foco a `[0,1]`, zoom a `[1,2.5]` e rejeitar modo fora de `automatico|manual` com `ValueError("Enquadramento da capa inválido.")`.

- [ ] **Step 4: Implementar migração sequencial v1 → v2 → v3**

```python
PROJECT_SCHEMA_VERSION = 3

if version == 1:
    migrated_config.setdefault("estilo_capa", "mosaico")
    version = 2
if version == 2:
    migrated_config.setdefault("foto_capa_id", "")
    migrated_config.setdefault("capa_foco_x", 0.5)
    migrated_config.setdefault("capa_foco_y", 0.5)
    migrated_config.setdefault("capa_zoom", 1.0)
    migrated_config.setdefault("capa_enquadramento", "automatico")
    version = 3
migrated["schema_version"] = version
```

- [ ] **Step 5: Verificar round-trip e compatibilidade**

Run: `python -m pytest tests/test_projeto.py tests/test_motor_editorial.py -q`

Expected: PASS; `plan`, `previous_plan`, `cover_ids` e páginas permanecem iguais no round-trip.

- [ ] **Step 6: Commit**

```powershell
git add provas/capas.py provas/motor.py provas/projeto.py tests/test_projeto.py tests/test_motor_editorial.py
git commit -m "feat: version classic cover settings"
```

---

### Task 3: Adicionar fonte e compositor puro da Capa Clássica

**Files:**
- Create: `assets/fonts/BodoniModa[opsz,wght].ttf`
- Create: `assets/fonts/OFL-BodoniModa.txt`
- Create: `provas/capa_classica.py`
- Create: `tests/test_capa_classica.py`

**Interfaces:**
- Produces: `ClassicCrop`, `ClassicLayout`, `layout_classico()`, `crop_box()`, `render_classic_cover()`.
- Consumes: `enquadramento.detect_faces()` para o foco automático.

- [ ] **Step 1: Baixar os dois recursos oficiais, sem renomear a família**

```powershell
Invoke-WebRequest 'https://raw.githubusercontent.com/google/fonts/main/ofl/bodonimoda/BodoniModa%5Bopsz%2Cwght%5D.ttf' -OutFile 'assets/fonts/BodoniModa[opsz,wght].ttf'
Invoke-WebRequest 'https://raw.githubusercontent.com/google/fonts/main/ofl/bodonimoda/OFL.txt' -OutFile 'assets/fonts/OFL-BodoniModa.txt'
```

Expected: TTF começa com assinatura válida e licença contém `SIL OPEN FONT LICENSE Version 1.1`.

- [ ] **Step 2: Escrever REDs de geometria, crop e fitting**

```python
def test_layout_matches_approved_a4_proportions():
    layout = layout_classico(1600, 1131)
    assert layout.photo.left == pytest.approx(128, abs=1)
    assert layout.photo.right == pytest.approx(1472, abs=1)
    assert layout.photo.top == pytest.approx(211, abs=1)
    assert layout.photo.bottom == pytest.approx(1036, abs=1)

def test_manual_crop_covers_frame_and_keeps_focus():
    box = crop_box((6016, 4016), (1344, 825), ClassicCrop(0.8, 0.3, 1.4, "manual"))
    assert box.width / box.height == pytest.approx(1344 / 825)
    assert 0 <= box.left < box.right <= 6016

def test_overlong_title_fails_atomically(photo):
    with pytest.raises(CoverTextOverflow, match="Abrevie o título"):
        render_classic_cover(photo, 1600, 1131, "W" * 180, "ESTÚDIO", ClassicCrop())
```

- [ ] **Step 3: Confirmar RED**

Run: `python -m pytest tests/test_capa_classica.py -q`

Expected: FAIL em coleta porque `provas.capa_classica` não existe.

- [ ] **Step 4: Implementar tipos e geometria imutáveis**

```python
@dataclass(frozen=True)
class ClassicCrop:
    focus_x: float = 0.5
    focus_y: float = 0.5
    zoom: float = 1.0
    mode: str = "automatico"

@dataclass(frozen=True)
class ClassicLayout:
    title: PixelRect
    studio: PixelRect
    photo: PixelRect

def layout_classico(width: int, height: int) -> ClassicLayout:
    return ClassicLayout(
        PixelRect(round(width * .08), round(height * .061), round(width * .84), round(height * .061)),
        PixelRect(round(width * .08), round(height * .141), round(width * .84), round(height * .030)),
        PixelRect(round(width * .08), round(height * .187), round(width * .84), round(height * (.916 - .187))),
    )
```

- [ ] **Step 5: Implementar crop automático/manual e renderer único**

`crop_box()` calcula primeiro o crop-to-fill mínimo, multiplica sua escala por `zoom`, limita o centro para nunca revelar vazio e retorna coordenadas fracionárias. `render_classic_cover()` usa `Image.Transform.EXTENT` para evitar distorção por arredondamento, desenha título com fitting 34→22 pt, subtítulo 10 pt com glyph-by-glyph tracking e devolve `Capa(identity_embedded=True, used_photo_ids=(photo_id,))`.

```python
font_sizes = range(round(34 * scale), round(22 * scale) - 1, -1)
for size in font_sizes:
    font = ImageFont.truetype(BODONI_PATH, size)
    if draw.textbbox((0, 0), title, font=font)[2] <= layout.title.width:
        break
else:
    raise CoverTextOverflow("O título da capa não cabe. Abrevie o título antes de exportar.")
```

- [ ] **Step 6: Verificar pixels, recursos e ownership**

Run: `python -m pytest tests/test_capa_classica.py -q`

Expected: PASS para vertical/horizontal, foco de borda, zoom 1–2.5, acentos, cancelamento lógico e imagens fechadas pelo chamador.

- [ ] **Step 7: Commit**

```powershell
git add assets/fonts provas/capa_classica.py tests/test_capa_classica.py
git commit -m "feat: render classic single-photo covers"
```

---

### Task 4: Integrar seleção automática, preview e PDF

**Files:**
- Modify: `provas/capas.py`
- Modify: `provas/motor.py`
- Modify: `provas/documento.py`
- Test: `tests/test_motor_editorial.py`
- Test: `tests/test_end_to_end.py`

**Interfaces:**
- Produces: `selecionar_foto_classica(photos, manual_id) -> str`.
- Produces: `_render_cover()` com dispatch explícito para `classica`.

- [ ] **Step 1: Escrever RED de seleção, fallback e paridade**

```python
def test_classic_cover_prefers_horizontal_and_respects_manual_id(photos):
    assert selecionar_foto_classica(photos, "") == best_horizontal(photos).id
    assert selecionar_foto_classica(photos, photos[-1].id) == photos[-1].id

def test_classic_preview_matches_pdf_first_page(case):
    preview = gerar_preview(case.config(estilo_capa="classica"), case.plan)
    exportar(case.config(estilo_capa="classica"), case.plan)
    assert first_pdf_page_rgb(case.output, preview[0].size) == preview[0].tobytes()
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_motor_editorial.py tests/test_end_to_end.py -k classica -q`

Expected: FAIL porque dispatch e seleção ainda não existem.

- [ ] **Step 3: Implementar seleção determinística**

Ordenar candidatos por: manual válido; orientação horizontal; segurança facial; `quality*0.60 + sharpness*0.18 + exposure*0.14 + density*0.08`; `index`; `id`. Não alterar `cover_photo_ids` do plano.

- [ ] **Step 4: Integrar o renderer sem duplicar identidade**

```python
if config.estilo_capa == "classica":
    photo_id = selecionar_foto_classica(tuple(by_id.values()), config.foto_capa_id)
    crop = ClassicCrop(config.capa_foco_x, config.capa_foco_y, config.capa_zoom, config.capa_enquadramento)
    cover = render_classic_cover(source, width, height, config.titulo, config.estudio, crop)
elif config.estilo_capa == "mosaico":
    cover = capas.gerar(
        "mosaico", cover_images, width, height, palette, identity=identity, seed=plan.seed
    )
else:
    cover = capas.gerar(
        "curvas_editoriais", cover_photos, width, height, palette,
        identity=identity, seed=plan.seed,
    )
```

`Documento.capa(identity_embedded=True)` deve inserir a imagem full-page e retornar antes de qualquer título/estúdio legado.

- [ ] **Step 5: Incluir todos os campos Clássica no fingerprint**

```python
(config.foto_capa_id, config.capa_foco_x, config.capa_foco_y,
 config.capa_zoom, config.capa_enquadramento)
```

- [ ] **Step 6: Verificar regressões dos três estilos**

Run: `python -m pytest tests/test_motor_editorial.py tests/test_capas_editoriais.py tests/test_capa_orbita.py tests/test_end_to_end.py -q`

Expected: PASS; páginas internas permanecem idênticas ao trocar somente o estilo da capa.

- [ ] **Step 7: Commit**

```powershell
git add provas/capas.py provas/motor.py provas/documento.py tests/test_motor_editorial.py tests/test_end_to_end.py
git commit -m "feat: integrate classic cover rendering"
```

---

### Task 5: Adicionar seleção única e editor de recorte

**Files:**
- Create: `provas/ui/crop_dialog.py`
- Modify: `provas/ui/cover_dialog.py`
- Modify: `provas/ui/sidebar.py`
- Modify: `provas/ui/main_window.py`
- Modify: `provas/ui/theme.qss`
- Modify: `provas/ui/workers.py`
- Test: `tests/test_ui_state.py`

**Interfaces:**
- Produces: `CropDialog.applied = Signal(float, float, float)`.
- Produces: o construtor de `CoverDialog` ganha o argumento nomeado `single_selection: bool = False`; o diálogo ganha `single_photo_selected = Signal(str)`.
- Produces: `MainWindow.set_classic_cover_photo()` e `set_classic_crop()`.

- [ ] **Step 1: Escrever REDs de seleção única e transação do crop**

```python
def test_classic_cover_dialog_selects_one_photo(qapp, window_with_project):
    window_with_project.set_cover_style("classica")
    window_with_project.set_classic_cover_photo("horizontal-02.jpg")
    assert window_with_project.project_state.config.foto_capa_id.endswith("horizontal-02.jpg")
    assert window_with_project.project_state.config.cover_ids == original_cover_ids

def test_crop_cancel_is_transactional(qapp, crop_dialog):
    before = crop_dialog.value
    drag_photo(crop_dialog, 80, -30)
    crop_dialog.reject()
    assert crop_dialog.committed_value == before
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_ui_state.py -k 'classic or crop' -q`

Expected: FAIL para diálogo, sinais e métodos ausentes.

- [ ] **Step 3: Implementar `CropCanvas` e diálogo**

`CropCanvas` guarda um draft local, converte deltas do mouse em foco normalizado, limita foco pela geometria de `crop_box()` e redesenha por `paintEvent`. O diálogo só emite no botão Aplicar.

```python
class CropDialog(QDialog):
    applied = Signal(float, float, float)

    def _apply(self) -> None:
        crop = self.canvas.crop
        self.applied.emit(crop.focus_x, crop.focus_y, crop.zoom)
        self.accept()
```

- [ ] **Step 4: Adaptar seletor e sidebar**

Adicionar botão `Ajustar enquadramento`, acessible name homônimo, habilitado somente quando estilo `classica` e projeto pronto. Em `CoverDialog`, `single_selection=True` troca a cópia para “Escolha a fotografia da capa” e não exige selecionar um slot.

- [ ] **Step 5: Atualizar estado e preview somente da capa**

```python
def set_classic_crop(self, focus_x: float, focus_y: float, zoom: float) -> None:
    config = replace(self.project_state.config, capa_foco_x=focus_x, capa_foco_y=focus_y,
                     capa_zoom=zoom, capa_enquadramento="manual")
    self.project_state = replace(self.project_state, config=config)
    self.previews = ()
    self.request_preview()
```

Não alterar `plan`, `previous_plan`, `seed`, `cover_ids` nem páginas.

- [ ] **Step 6: Validar teclado, cliques rápidos e 1093×614**

Run: `python -m pytest tests/test_ui_state.py -q`

Run: `python scripts/capture_ui.py --size 1093x614 --output tmp/ui-qa/classic-cover-editor.png`

Expected: PASS; sem clipping, foco visível, Exportar como única ação primária; captura inspecionada via `view_image`.

- [ ] **Step 7: Commit**

```powershell
git add provas/ui/crop_dialog.py provas/ui/cover_dialog.py provas/ui/sidebar.py provas/ui/main_window.py provas/ui/theme.qss provas/ui/workers.py tests/test_ui_state.py
git commit -m "feat: edit classic cover crop"
```

---

### Task 6: Aplicar símbolo oficial e empacotar recursos próprios

**Files:**
- Create: `assets/fanara-symbol-source.png`
- Create: `assets/fanara-symbol.png`
- Modify: `assets/icone.ico`
- Create: `provas/recursos.py`
- Modify: `provas/ui/main_window.py`
- Modify: `empacotar.py`
- Modify: `verificar.py`
- Test: `tests/test_ui_packaging.py`

**Interfaces:**
- Produces: `recursos.caminho(nome: str) -> Path` compatível com fonte e PyInstaller.
- Produces: ICO 16, 20, 24, 32, 40, 48, 64, 128 e 256 px.

- [ ] **Step 1: Copiar a fonte autorizada e escrever RED de transparência/hash**

Copiar `C:\Users\estud\Downloads\logoFanara Estudio SIMBOLO 2024.png` para `assets/fanara-symbol-source.png` sem alteração. O teste deve afirmar cor dominante `(218, 66, 101)`, alpha zero nos quatro cantos do derivado e branco opaco no monograma.

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_ui_packaging.py -k fanara -q`

Expected: FAIL porque recursos derivados não existem.

- [ ] **Step 3: Gerar transparência por flood-fill externo e ICO**

Usar flood-fill iniciado nos quatro cantos com tolerância RGB 8; nunca tornar transparentes pixels brancos não conectados às bordas. Redimensionar em 3×/LANCZOS com safe area de 4% e salvar o ICO com todos os tamanhos exigidos.

- [ ] **Step 4: Usar recurso na janela**

```python
self.setWindowIcon(QIcon(str(recursos.caminho("icone.ico"))))
mark.setPixmap(QPixmap(str(recursos.caminho("fanara-symbol.png"))).scaled(
    32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation
))
```

- [ ] **Step 5: Empacotar fonte, licença, PNG e ICO sem enfraquecer privacidade**

Adicionar `--add-data` apenas para caminhos oficiais. `inspecionar_pacote()` mantém bloqueio geral de imagens, mas aceita somente a allowlist exata quando o SHA-256 no ZIP coincide com o recurso rastreado.

```python
OFFICIAL_ASSETS = {
    "fanara-symbol.png": sha256(Path(RAIZ, "assets/fanara-symbol.png").read_bytes()).hexdigest(),
    "icone.ico": sha256(Path(RAIZ, "assets/icone.ico").read_bytes()).hexdigest(),
}
```

- [ ] **Step 6: Verificar recursos e privacidade**

Run: `python verificar.py`

Run: `python -m pytest tests/test_ui_packaging.py -q`

Expected: fontes/ícones presentes, hashes válidos; mutantes `marca-cliente.png`, BMP, WebP, RAW e `.provas.json` continuam rejeitados.

- [ ] **Step 7: Commit**

```powershell
git add assets provas/recursos.py provas/ui/main_window.py empacotar.py verificar.py tests/test_ui_packaging.py
git commit -m "feat: apply official Fanara app identity"
```

---

### Task 7: E2E, QA visual e pacote final

**Files:**
- Modify: `tests/test_end_to_end.py`
- Modify: `tests/visual_qa.py`
- Modify: `tests/baselines/README.md`
- Modify: `README.md`
- Modify: only production defects reproduced by this gate.

**Interfaces:**
- Produces: caso `classica` reproduzível em QA e evidência final do ZIP.

- [ ] **Step 1: Adicionar matriz E2E da Capa Clássica**

Cobrir modo Prova/Fotolivro × foto vertical/horizontal × automático/manual × título curto/longo. Cada caso afirma A4 horizontal, preview=PDF, uma foto usada, páginas internas invariáveis e warning PT-BR exato.

- [ ] **Step 2: Ampliar `visual_qa.py`**

Adicionar `--case capa-classica`, seeds fixas e saídas para automático, foco esquerdo/direito, zoom 1/1.5/2.5, título acentuado e foto vertical/horizontal. Gerar contact sheet sem commitar PNG/PDF.

- [ ] **Step 3: Rodar gates de fonte e UI**

Run: `python -m pytest tests/test_capa_classica.py tests/test_motor_editorial.py tests/test_ui_state.py tests/test_ui_packaging.py -q`

Expected: PASS.

- [ ] **Step 4: Rodar suíte completa e verificador**

Run: `python -m pytest -q`

Run: `python verificar.py`

Expected: 100%, exit code 0, sem warnings próprios.

- [ ] **Step 5: Gerar e inspecionar QA**

Run: `python tests/visual_qa.py --case capa-classica --dpi 120 --output tmp/visual-qa/capa-classica`

Inspecionar overview e originais via `view_image`: margens, tipografia, rosto, crop, ausência de branco externo no ícone e paridade.

- [ ] **Step 6: Rebuild e teste externo**

Run: `python empacotar.py`

Run: `python -m pytest tests/test_end_to_end.py::test_packaged_zip_contains_verifiable_source_manifest tests/test_end_to_end.py::test_packaged_executable_generates_both_modes_outside_source_tree -q`

Expected: PASS; manifesto aponta HEAD, SHA do EXE confere e conteúdo privado é zero.

- [ ] **Step 7: Commit**

```powershell
git add tests/test_end_to_end.py tests/visual_qa.py tests/baselines/README.md README.md
git commit -m "test: verify classic covers end to end"
```

---

## Final Gate

- [ ] Gerar patch do merge-base até HEAD para revisão independente.
- [ ] Corrigir todos os findings Critical/Important por RED→GREEN e repetir a revisão.
- [ ] Repetir suíte completa, `verificar.py`, rebuild e dois testes pós-build sobre o HEAD final.
- [ ] Atualizar o Pull Request privado existente sem remover o worktree.
