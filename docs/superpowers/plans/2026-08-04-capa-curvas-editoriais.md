# Capa Curvas Editoriais Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar a capa A4 horizontal “Curvas editoriais — Órbita equilibrada” como opção ao mosaico atual, com enquadramento local, identidade persistente, prévia fiel e pacote Windows autônomo.

**Architecture:** O campo existente `Config.estilo_capa` será o contrato canônico (`mosaico` ou `curvas_editoriais`). Novos módulos isolam geometria, enquadramento e identidade; `capas.py` orquestra esses módulos e `motor.py` continua sendo a única fronteira usada por prévia e exportação. A detecção de rosto será local com OpenCV Haar Cascade, com fallback determinístico por área de interesse quando não houver detecção confiável.

**Tech Stack:** Python 3.10+, Pillow 10+, PyMuPDF 1.24+, PySide6 6.7+, OpenCV headless 4.10+, pytest 8+, PyInstaller/Windows.

## Global Constraints

- A capa é A4 horizontal; páginas internas continuam inteiras, sem corte nem distorção.
- `mosaico` permanece o padrão de projetos existentes; `curvas_editoriais` é uma opção adicional.
- A capa curva usa de 6 a 9 fotos quando disponíveis e nunca repete fotografia.
- Pastas com 1 a 5 fotos usam variantes reduzidas e não repetem conteúdo.
- Título, estúdio, site e logotipo opcional são persistidos por referência; nenhuma imagem é incorporada ao JSON.
- Detecção de rosto e análise de interesse são locais; nenhuma fotografia sai da máquina.
- Troca de estilo não recompõe nem reordena o miolo.
- Regeneração preserva estilo, identidade, logotipo e substituições manuais da capa.
- Prévia e PDF consomem o mesmo renderer de capa e devem coincidir pixel a pixel no tamanho comparado.
- Texto nunca é truncado silenciosamente; conteúdo que não cabe bloqueia exportação com mensagem em português.
- Logo ausente ou ilegível é ignorado com aviso não bloqueante.
- O pacote Windows deve funcionar fora da árvore do código e levar todos os dados necessários à detecção local.

---

### Task 1: Contrato de configuração e migração de projetos

**Files:**
- Modify: `provas/capas.py`
- Modify: `provas/motor.py`
- Modify: `provas/projeto.py`
- Modify: `tests/test_projeto.py`
- Modify: `tests/test_motor_editorial.py`

**Interfaces:**
- Consumes: `motor.Config.estilo_capa`, `estudio`, `site`, `logo`, `titulo`, `cover_ids`.
- Produces: `capas.COVER_STYLES == ("mosaico", "curvas_editoriais")`, schema v2 com migração v1 e `validate_cover_style(value: str) -> str`.

- [ ] **Step 1: Escrever testes de contrato e migração**

```python
def test_v1_project_migrates_to_mosaic_and_keeps_identity(tmp_path):
    payload = legacy_v1_payload(estudio="Fanara", site="fanara.com.br", logo="marca.png")
    path = write_json(tmp_path / "legacy.provas.json", payload)
    state = load_project(path)
    assert state.config.estilo_capa == "mosaico"
    assert (state.config.estudio, state.config.site, state.config.logo) == (
        "Fanara", "fanara.com.br", "marca.png"
    )

def test_config_rejects_unknown_cover_style(tmp_path):
    with pytest.raises(ValueError, match="Estilo de capa"):
        Config(str(tmp_path), estilo_capa="desconhecido").com_padroes()
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_projeto.py tests/test_motor_editorial.py -q`

Expected: FAIL porque schema v1 é rejeitado ou estilo desconhecido ainda cai silenciosamente no mosaico.

- [ ] **Step 3: Implementar contrato e migração explícita**

```python
# provas/capas.py
COVER_STYLES = ("mosaico", "curvas_editoriais")
ESTILOS = COVER_STYLES

def validate_cover_style(value: str) -> str:
    if value not in COVER_STYLES:
        raise ValueError("Estilo de capa inválido. Use mosaico ou curvas_editoriais.")
    return value

# provas/projeto.py
PROJECT_SCHEMA_VERSION = 2

def _migrate_project(data: dict[str, object]) -> dict[str, object]:
    version = data.get("schema_version")
    if version == 1:
        migrated = dict(data)
        config = dict(migrated.get("config", {}))
        config.setdefault("estilo_capa", "mosaico")
        migrated["config"] = config
        migrated["schema_version"] = 2
        return migrated
    if version != 2:
        raise ProjectSchemaError(f"A versão do projeto {version!r} não é suportada.")
    return data
```

Em `Config.com_padroes()` e `ProjectConfig.__post_init__`, chamar `validate_cover_style`.

- [ ] **Step 4: Verificar GREEN e round-trip v2**

Run: `python -m pytest tests/test_projeto.py tests/test_motor_editorial.py -q`

Expected: PASS; v1 abre como mosaico e v2 preserva `curvas_editoriais`.

- [ ] **Step 5: Commit**

```powershell
git add provas/capas.py provas/motor.py provas/projeto.py tests/test_projeto.py tests/test_motor_editorial.py
git commit -m "feat: version curved cover configuration"
```

---

### Task 2: Geometria determinística da Órbita Equilibrada

**Files:**
- Create: `provas/capa_curvas.py`
- Create: `tests/test_capa_curvas.py`

**Interfaces:**
- Consumes: largura e altura positivas; quantidade de fotos entre 1 e 9.
- Produces: `CurveSlot`, `CurveLayout`, `layout_orbita(width: int, height: int, count: int) -> CurveLayout`, `render_mask(slot: CurveSlot, size: tuple[int, int]) -> Image.Image`.

- [ ] **Step 1: Escrever testes geométricos**

```python
@pytest.mark.parametrize("count", range(1, 10))
def test_orbit_layout_is_a4_landscape_safe_and_has_one_slot_per_photo(count):
    layout = layout_orbita(1600, 1131, count)
    assert len(layout.slots) == count
    assert layout.identity_safe_rect.x >= 0
    assert layout.identity_safe_rect.right <= 1600
    assert all(slot.bounds.intersection(layout.identity_safe_rect).area == 0 for slot in layout.slots)

def test_curve_masks_have_antialiased_non_rectangular_edges():
    mask = render_mask(layout_orbita(1600, 1131, 6).slots[0], (1600, 1131))
    values = set(mask.getdata())
    assert 0 in values and 255 in values and any(0 < value < 255 for value in values)
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_capa_curvas.py -q`

Expected: FAIL com `ModuleNotFoundError: provas.capa_curvas`.

- [ ] **Step 3: Implementar tipos e variantes normalizadas**

```python
@dataclass(frozen=True)
class PixelRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    def intersection(self, other: "PixelRect") -> "PixelRect":
        left, top = max(self.x, other.x), max(self.y, other.y)
        right, bottom = min(self.right, other.right), min(self.bottom, other.bottom)
        return PixelRect(left, top, max(0, right - left), max(0, bottom - top))

@dataclass(frozen=True)
class CurveSlot:
    id: str
    path: tuple[tuple[float, float], ...]
    bounds: PixelRect
    preferred_focus: tuple[float, float]

@dataclass(frozen=True)
class CurveLayout:
    slots: tuple[CurveSlot, ...]
    identity_safe_rect: PixelRect
    logo_rect: PixelRect
    site_rect: PixelRect

def layout_orbita(width: int, height: int, count: int) -> CurveLayout:
    if width <= height or not 1 <= count <= 9:
        raise ValueError("A órbita exige A4 horizontal e de 1 a 9 fotografias.")
    normalized = ORBIT_VARIANTS[count]
    return normalized.scale(width, height)
```

Usar uma tabela imutável `ORBIT_VARIANTS` indexada por 1–9. Cada entrada contém exatamente `count` paths normalizados. Para 1–5, usar respectivamente os slots dominantes `hero_left`, `hero_right`, `lower_left`, `lower_right` e `lower_arc`, escalados para absorver o espaço dos slots ausentes; para 6–9, acrescentar `upper_left`, `upper_right`, `side_right` e `lower_center` sem alterar o retângulo central `(0.38, 0.34, 0.24, 0.30)`. `render_mask` converte os pontos normalizados em pixels, desenha a 3x com `ImageDraw.rounded_rectangle` e arcos elípticos combinados por `ImageChops`, e reduz com LANCZOS. Os testes de snapshots geométricos armazenam bounds e área opaca de cada variante, não PNGs.

- [ ] **Step 4: Testar determinismo, bounds e ausência de sobreposição proibida**

Run: `python -m pytest tests/test_capa_curvas.py -q`

Expected: PASS para counts 1–9.

- [ ] **Step 5: Commit**

```powershell
git add provas/capa_curvas.py tests/test_capa_curvas.py
git commit -m "feat: define balanced orbit cover geometry"
```

---

### Task 3: Enquadramento local com proteção de rosto

**Files:**
- Create: `provas/enquadramento.py`
- Create: `tests/test_enquadramento.py`
- Modify: `pyproject.toml`
- Modify: `verificar.py`

**Interfaces:**
- Consumes: `PIL.Image.Image`, tamanho alvo, foco preferido e detector injetável.
- Produces: `FaceBox`, `FrameResult`, `detect_faces(image) -> tuple[FaceBox, ...]`, `frame_for_mask(image, target_size, preferred_focus, detector=detect_faces) -> FrameResult`.

- [ ] **Step 1: Criar fixtures de rosto e testes com detector injetável**

```python
def test_frame_keeps_confident_face_inside_safe_area(portrait):
    detector = lambda image: (FaceBox(0.38, 0.12, 0.24, 0.22, confidence=0.92),)
    result = frame_for_mask(portrait, (600, 900), (0.5, 0.35), detector=detector)
    assert result.faces_protected == 1
    assert result.crop.contains(result.face_boxes[0].center)

def test_frame_falls_back_deterministically_without_faces(portrait):
    a = frame_for_mask(portrait, (600, 900), (0.45, 0.4), detector=lambda _: ())
    b = frame_for_mask(portrait, (600, 900), (0.45, 0.4), detector=lambda _: ())
    assert a.crop == b.crop
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_enquadramento.py -q`

Expected: FAIL porque o módulo não existe.

- [ ] **Step 3: Implementar enquadramento e detector Haar local**

```python
@dataclass(frozen=True)
class CropRect:
    x: float
    y: float
    width: float
    height: float

    def contains(self, point: tuple[float, float]) -> bool:
        px, py = point
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height

@dataclass(frozen=True)
class FrameResult:
    image: Image.Image
    crop: CropRect
    face_boxes: tuple[FaceBox, ...]
    faces_protected: int
    safe: bool

@dataclass(frozen=True)
class FaceBox:
    x: float
    y: float
    width: float
    height: float
    confidence: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

def detect_faces(image: Image.Image) -> tuple[FaceBox, ...]:
    gray = cv2.cvtColor(numpy.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(cascade_path())
    boxes = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
    return tuple(FaceBox.from_pixels(box, image.size, 1.0) for box in boxes)
```

Adicionar `opencv-python-headless>=4.10` e `numpy>=1.26` às dependências. `frame_for_mask` calcula crop cover-style, desloca-o para conter faces confiáveis e retorna `safe=False` quando uma face não cabe na área segura.

- [ ] **Step 4: Atualizar diagnóstico de dependências**

`verificar.py` deve validar OpenCV, NumPy e o cascade local, mantendo mensagens PT-BR.

- [ ] **Step 5: Verificar GREEN**

Run: `python -m pytest tests/test_enquadramento.py tests/test_cli.py -q`

Expected: PASS; nenhuma chamada de rede.

- [ ] **Step 6: Commit**

```powershell
git add provas/enquadramento.py tests/test_enquadramento.py pyproject.toml verificar.py
git commit -m "feat: protect faces in cover framing"
```

---

### Task 4: Identidade, logotipo e validação tipográfica

**Files:**
- Create: `provas/identidade_capa.py`
- Create: `tests/test_identidade_capa.py`
- Modify: `provas/capas.py`

**Interfaces:**
- Consumes: canvas Pillow, `IdentityData`, áreas seguras da `CurveLayout`.
- Produces: `IdentityData`, `CoverWarning`, `CoverTextOverflow`, `render_identity(canvas, layout, data, palette) -> tuple[CoverWarning, ...]`.

- [ ] **Step 1: Escrever testes de texto e logo**

```python
def test_identity_draws_title_studio_site_and_valid_logo(canvas, layout, logo_path):
    warnings = render_identity(canvas, layout, IdentityData(
        title="Sessão Aurora", studio="Estúdio Fanara",
        site="fanara.com.br", logo_path=str(logo_path)), palette)
    assert warnings == ()
    assert canvas.getbbox() is not None

def test_unreadable_logo_warns_but_does_not_block(canvas, layout, tmp_path):
    bad = tmp_path / "logo.png"
    bad.write_bytes(b"not an image")
    warnings = render_identity(canvas, layout, IdentityData("Aurora", "Fanara", "site", str(bad)), palette)
    assert warnings[0].code == "logo_ilegivel"

def test_text_that_cannot_fit_raises_in_portuguese(canvas, layout):
    with pytest.raises(CoverTextOverflow, match="Abrevie"):
        render_identity(canvas, layout, IdentityData("X" * 500, "Fanara", "site", ""), palette)
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_identidade_capa.py -q`

Expected: FAIL porque o módulo não existe.

- [ ] **Step 3: Implementar fitting com limites definidos**

```python
@dataclass(frozen=True)
class IdentityData:
    title: str
    studio: str
    site: str
    logo_path: str = ""

@dataclass(frozen=True)
class CoverWarning:
    code: str
    message: str

class CoverTextOverflow(ValueError):
    pass

TITLE_SIZES = range(54, 31, -2)
STUDIO_SIZES = range(26, 17, -1)
SITE_SIZES = range(18, 13, -1)

def fit_text(draw, text, font_factory, sizes, max_width):
    for size in sizes:
        font = font_factory(size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    raise CoverTextOverflow("O texto da capa não cabe. Abrevie o conteúdo antes de exportar.")
```

Normalizar logo para RGBA, conter sem distorção em `logo_rect` e nunca usar o logotipo como watermark da capa.

- [ ] **Step 4: Estender resultado de capa com warnings**

```python
@dataclass(frozen=True)
class Capa:
    imagem: Image.Image
    ancora: float
    identity_embedded: bool = False
    warnings: tuple[CoverWarning, ...] = ()
    used_photo_ids: tuple[str, ...] = ()
```

- [ ] **Step 5: Verificar GREEN e regressão do mosaico**

Run: `python -m pytest tests/test_identidade_capa.py tests/test_capas_editoriais.py -q`

Expected: PASS; mosaico continua com `identity_embedded=False`.

- [ ] **Step 6: Commit**

```powershell
git add provas/identidade_capa.py provas/capas.py tests/test_identidade_capa.py tests/test_capas_editoriais.py
git commit -m "feat: compose curved cover identity"
```

---

### Task 5: Orquestração da capa curva no motor

**Files:**
- Modify: `provas/capas.py`
- Modify: `provas/motor.py`
- Modify: `provas/documento.py`
- Create: `tests/test_capa_orbita.py`
- Modify: `tests/test_motor_editorial.py`

**Interfaces:**
- Consumes: `CurveLayout`, `frame_for_mask`, `render_identity`, `BookPlan.cover_photo_ids`.
- Produces: `CoverPhoto(id: str, image: Image.Image)`, `capas.gerar_curvas_editoriais(items: list[CoverPhoto], width: int, height: int, palette: Paleta, identity: IdentityData, seed: int) -> Capa`; motor usa `capas.gerar(estilo, ...)` para ambos estilos.

- [ ] **Step 1: Escrever testes do orquestrador**

```python
@dataclass(frozen=True)
class CoverPhoto:
    id: str
    image: Image.Image

@pytest.mark.parametrize("count", range(1, 10))
def test_curved_cover_uses_every_supplied_photo_once(count, portraits):
    cover = gerar_curvas_editoriais(portraits[:count], 1600, 1131, palette, identity, seed=42)
    assert cover.identity_embedded
    assert cover.used_photo_ids == tuple(photo.id for photo in portraits[:count])

def test_preview_and_pdf_share_exact_curved_cover_pixels(tmp_path, image_factory):
    config, plan = curved_project(tmp_path, image_factory)
    preview = motor.gerar_preview(config, plan, width=842)[0]
    motor.exportar(config, plan)
    rendered = render_pdf_page(config.saida, 0, width=842)
    assert preview.tobytes() == rendered.tobytes()
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_capa_orbita.py tests/test_motor_editorial.py -q`

Expected: FAIL porque `curvas_editoriais` ainda renderiza mosaico.

- [ ] **Step 3: Implementar associação segura e fallback**

```python
def assign_photos(slots, photos, seed, framer=frame_for_mask):
    remaining = list(photos)
    assigned = []
    for slot in slots:
        candidates = sorted(remaining, key=lambda p: candidate_score(p, slot, seed), reverse=True)
        chosen = next((p for p in candidates if framer_for(p, slot).safe), candidates[0])
        assigned.append((slot, chosen))
        remaining.remove(chosen)
    return tuple(assigned)
```

Não duplicar fotos. Quando nenhuma candidata for segura, usar a melhor candidata com warning `rosto_em_area_de_risco`.

- [ ] **Step 4: Integrar documento sem duplicar identidade**

Adicionar `Documento.capa(..., identity_embedded: bool = False)`. Quando verdadeiro, inserir apenas a imagem full-page e metadados discretos já definidos; não redesenhar título/estúdio/site.

- [ ] **Step 5: Integrar `_render_cover` e cache fingerprint**

`_render_cover` chama `capas.gerar(config.estilo_capa, ...)`; `_render_style_fingerprint` inclui `estilo_capa` e estado do logo. Preview e export recebem os mesmos warnings.

- [ ] **Step 6: Verificar GREEN e modos prova/limpo**

Run: `python -m pytest tests/test_capa_orbita.py tests/test_motor_editorial.py tests/test_end_to_end.py -q`

Expected: PASS; a capa é igual nos dois modos e watermark continua apenas nas fotos internas da prova.

- [ ] **Step 7: Commit**

```powershell
git add provas/capas.py provas/motor.py provas/documento.py tests/test_capa_orbita.py tests/test_motor_editorial.py tests/test_end_to_end.py
git commit -m "feat: render balanced orbit covers"
```

---

### Task 6: Controles profissionais na interface

**Files:**
- Modify: `provas/ui/sidebar.py`
- Modify: `provas/ui/main_window.py`
- Modify: `provas/ui/theme.qss`
- Modify: `tests/test_ui_state.py`

**Interfaces:**
- Consumes: `ProjectConfig.estilo_capa`, `titulo`, `estudio`, `site`, `logo`.
- Produces: sinais `cover_style_changed(str)` e `cover_identity_changed(dict)`; métodos `set_cover_identity(config)` e `set_cover_style(style, emit=False)`.

- [ ] **Step 1: Escrever testes de estado UI**

```python
def test_sidebar_exposes_two_cover_styles_and_identity_fields(qapp):
    sidebar = WorkflowSidebar()
    assert [sidebar.cover_style.itemData(i) for i in range(sidebar.cover_style.count())] == [
        "mosaico", "curvas_editoriais"
    ]
    assert sidebar.studio_edit.accessibleName() == "Nome do fotógrafo ou estúdio"

def test_switching_cover_style_rerenders_only_cover(qapp, window_with_project, monkeypatch):
    with patch.object(window_with_project, "analyze_photos") as analyze, \
         patch.object(window_with_project, "request_preview") as preview:
        window_with_project.set_cover_style("curvas_editoriais")
        assert analyze.call_count == 0
        assert preview.call_count == 1
    assert window_with_project.project_state.plan.pages == window_with_project.original_pages
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_ui_state.py -q`

Expected: FAIL porque os controles e sinais não existem.

- [ ] **Step 3: Implementar controles compactos e roláveis**

Usar `QComboBox` para estilo; `QLineEdit` para título, estúdio e site; linha de logo com “Escolher…” e “Remover”. Colocar o conteúdo da sidebar em `QScrollArea` sem alterar a largura de 265 px; manter botões importantes com altura mínima 44 px e inputs com 36 px.

```python
self.cover_style.addItem("Mosaico editorial", "mosaico")
self.cover_style.addItem("Curvas editoriais", "curvas_editoriais")
self.cover_style.currentIndexChanged.connect(
    lambda: self.cover_style_changed.emit(self.cover_style.currentData())
)
```

- [ ] **Step 4: Atualizar estado sem recompor o miolo**

```python
def set_cover_style(self, style: str) -> None:
    config = replace(self.project_state.config, estilo_capa=validate_cover_style(style))
    self.project_state = replace(self.project_state, config=config)
    self.request_preview()
```

Alterações de identidade fazem debounce de 250 ms antes da nova prévia. Logo ilegível gera banner warning e não bloqueia.

- [ ] **Step 5: Testar 840×540 e 1366×768@125%**

Run: `python -m pytest tests/test_ui_state.py -q`

Expected: PASS sem clipping e com navegação por teclado/accessible names.

- [ ] **Step 6: Capturar e inspecionar UI**

Run: `python scripts/capture_ui.py --size 1093x614 --output tmp/ui-qa/curved-cover-controls.png`

Expected: preview dominante; sidebar rolável; somente “Exportar PDF” como ação primária no estado pronto.

- [ ] **Step 7: Commit**

```powershell
git add provas/ui/sidebar.py provas/ui/main_window.py provas/ui/theme.qss tests/test_ui_state.py
git commit -m "feat: add curved cover controls"
```

---

### Task 7: CLI, documentação e pacote Windows

**Files:**
- Modify: `provas_cli.py`
- Modify: `README.md`
- Modify: `empacotar.py`
- Modify: `verificar.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_ui_packaging.py`

**Interfaces:**
- Consumes: novo estilo e dependências locais.
- Produces: `--capa {mosaico,curvas_editoriais}` e ZIP Windows com OpenCV/cascade.

- [ ] **Step 1: Escrever testes CLI/pacote**

```python
def test_cli_accepts_curved_cover_identity(tmp_path, photos):
    result = run_cli(photos, "--capa", "curvas_editoriais", "--estudio", "Fanara",
                     "--site", "fanara.com.br", "--logo", str(valid_logo),
                     "--saida", str(tmp_path / "curvas.pdf"))
    assert result.returncode == 0

def test_package_contains_face_detector_assets(zip_names):
    assert any(name.endswith("haarcascade_frontalface_default.xml") for name in zip_names)
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/test_cli.py tests/test_ui_packaging.py -q`

Expected: FAIL para `curvas_editoriais` ou cascade ausente.

- [ ] **Step 3: Atualizar CLI e README**

Definir `--capa` com `metavar="{mosaico,curvas_editoriais}"` e o validador PT-BR existente; documentar comandos completos para ambos os estilos. Acrescentar ao README as frases: “A detecção de rosto é executada localmente; nenhuma fotografia é enviada pela internet”, “Projetos v1 abrem como mosaico” e “Logotipo inválido é ignorado com aviso”.

- [ ] **Step 4: Atualizar PyInstaller**

Incluir módulos OpenCV necessários e o XML do cascade com `--add-data`; excluir módulos OpenCV não utilizados. `BUILD-MANIFEST.json` continua cobrindo fontes e SHA-256 do executável.

- [ ] **Step 5: Verificar, empacotar e inspecionar**

Run: `python verificar.py`

Expected: Python/Pillow/PyMuPDF/PySide6/NumPy/OpenCV/cascade/fontes/escrita: `OK`.

Run: `python empacotar.py`

Expected: `dist/Fotolivro-Windows.zip` recriado, sem `config.json`/logo do usuário.

- [ ] **Step 6: Testar ZIP fora da árvore**

Run: `python -m pytest tests/test_ui_packaging.py tests/test_end_to_end.py::test_packaged_executable_generates_both_modes_outside_source_tree -q`

Expected: PASS com `PYTHONPATH` vazio.

- [ ] **Step 7: Commit**

```powershell
git add provas_cli.py README.md empacotar.py verificar.py pyproject.toml tests/test_cli.py tests/test_ui_packaging.py
git commit -m "docs: ship curved editorial covers"
```

---

### Task 8: Regressão E2E e inspeção visual

**Files:**
- Modify: `tests/test_end_to_end.py`
- Modify: `tests/visual_qa.py`
- Modify: `tests/baselines/README.md`
- Modify: only defects found by the gate.

**Interfaces:**
- Consumes: aplicação e ZIP completos.
- Produces: evidência automática e visual da capa curva.

- [ ] **Step 1: Adicionar matriz E2E**

```python
@pytest.mark.parametrize("count", range(1, 10))
@pytest.mark.parametrize("mode", ["prova", "fotolivro"])
def test_curved_cover_end_to_end(case_factory, count, mode):
    case = case_factory(count=count, orientations="mixed")
    config = case.config(mode=mode, estilo_capa="curvas_editoriais")
    preview = motor.gerar_preview(config, case.plan)
    motor.exportar(config, case.plan)
    assert_pdf_a4_landscape(config.saida)
    assert_cover_matches_preview(config.saida, preview[0])
    assert len(set(case.plan.cover_photo_ids)) == count
```

- [ ] **Step 2: Adicionar casos de identidade e falha**

Adicionar cinco testes nomeados: `test_invalid_logo_warns_and_exports`, `test_overlong_identity_blocks_export`, `test_missing_logo_keeps_balanced_cover`, `test_edge_face_is_kept_inside_mask` e `test_manual_cover_choice_survives_regeneration`. Cada teste deve afirmar o warning/erro PT-BR exato, igualdade dos `cover_ids` antes/depois e paridade da primeira página com a prévia.

- [ ] **Step 3: Rodar suíte completa**

Run: `python -m pytest -v`

Expected: todos os testes passam, sem warnings do projeto.

- [ ] **Step 4: Gerar QA visual reproduzível**

Run: `python tests/visual_qa.py --case curvas-editoriais --dpi 120 --output tmp/visual-qa/curvas-editoriais`

Expected: PNGs e contact sheets para counts 1, 3, 5, 6, 9; retratos claros, escuros e mistos; logos horizontal/vertical/ausente.

- [ ] **Step 5: Inspecionar visualmente**

Verificar bordas antialias, rostos, contraste, núcleo central, título/estúdio/site, logo, áreas vazias, ausência de repetição e paridade preview/PDF. Registrar fixtures/seeds aceitas em `tests/baselines/README.md`; não commitar PNGs.

- [ ] **Step 6: Rebuild final e teste pós-build**

Run: `python empacotar.py`

Run: `python -m pytest tests/test_end_to_end.py::test_packaged_zip_contains_verifiable_source_manifest tests/test_end_to_end.py::test_packaged_executable_generates_both_modes_outside_source_tree -q`

Expected: PASS; manifesto referencia HEAD e SHA-256 do executável.

- [ ] **Step 7: Commit**

```powershell
git add tests/test_end_to_end.py tests/visual_qa.py tests/baselines/README.md
git commit -m "test: verify curved covers end to end"
```

---

## Final Review Gate

- [ ] Gerar pacote de revisão do merge-base até HEAD.
- [ ] Executar revisão independente de conformidade e qualidade.
- [ ] Corrigir todos os findings Critical/Important e repetir a revisão.
- [ ] Aplicar `verification-before-completion` com suíte completa, `verificar.py`, rebuild, testes pós-build e inspeção visual mais recente.
- [ ] Aplicar `finishing-a-development-branch` antes de publicar no GitHub.
