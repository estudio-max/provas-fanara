# Fotolivro Editorial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evoluir `provas-fanara` para um aplicativo Windows que cria fotolivros A4 horizontais com sequência narrativa, templates editoriais profissionais, prévia completa e dois modos de saída.

**Architecture:** O núcleo continuará em Python com Pillow/PyMuPDF. Novos módulos puros representarão análise, narrativa, templates e planos de página; o renderizador apenas consumirá esses planos. A interface migrará de Tkinter para PySide6 para suportar a mesa de edição, miniaturas e tarefas em segundo plano.

**Tech Stack:** Python 3.10+, Pillow, PyMuPDF, PySide6, pytest, PyInstaller, Git e GitHub CLI.

## Global Constraints

- Aplicativo Windows instalável; processamento totalmente local.
- Página padrão A4 horizontal, 297 × 210 mm.
- Fotografias internas 2:3 nunca são cortadas, esticadas, distorcidas ou giradas decorativamente.
- Todas as fotografias internas válidas aparecem exatamente uma vez.
- Templates internos aceitam somente 1, 2 ou 4 fotografias.
- `prova`: marca d'água e faixa com nome; `fotolivro`: nenhum dos dois.
- Mesma pasta, configuração e semente produzem a mesma composição.
- A interface permanece responsiva e operações longas podem ser canceladas.
- Prévia e PDF final consomem o mesmo `BookPlan`.

## File map

- Create `provas/modelos.py`: tipos compartilhados imutáveis.
- Create `provas/analise.py`: nitidez, exposição, densidade e similaridade.
- Create `provas/narrativa.py`: blocos narrativos e grupos de 1/2/4.
- Create `provas/templates.py`: catálogo declarativo e geometria sem recorte.
- Create `provas/compositor.py`: escolha determinística e reparo do ritmo.
- Create `provas/projeto.py`: JSON versionado e histórico de regeneração.
- Create `provas/preview.py`: miniaturas a partir de `BookPlan`.
- Create `provas/ui/`: mesa de edição PySide6.
- Modify `provas/imagens.py`, `capas.py`, `documento.py`, `motor.py`, `app.py`.
- Modify `provas_cli.py`, `verificar.py`, `empacotar.py`, `README.md`.
- Create `tests/`: testes unitários, integração, interface e regressão visual.

---

### Task 1: Repositório, dependências e testes

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: pacote existente `provas`.
- Produces: comando `python -m pytest` e fixtures `image_factory`/`photo_factory`.

- [ ] **Step 1: Inicializar Git sem incluir preferências locais**

```powershell
git init
```

Expected: repositório local vazio; `config.json` e `dist/` ainda não foram adicionados.

- [ ] **Step 2: Criar configuração do projeto**

Create `pyproject.toml`:

```toml
[project]
name = "fotolivro-editorial"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["Pillow>=10.0", "PyMuPDF>=1.24", "PySide6>=6.7"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

Create `.gitignore` containing `.venv/`, `__pycache__/`, `.pytest_cache/`, `dist/`, `build/`, `*.spec`, `config.json`, `tmp/`, `.superpowers/`, `*.pdf` and `*.fotolivro.json`.

- [ ] **Step 3: Criar fixtures sintéticas**

`tests/conftest.py` must create colored 2:3 JPGs, EXIF-oriented files and corrupt files under `tmp_path`, named `D61_0001.jpg`, `D61_0002.jpg`, etc.

- [ ] **Step 4: Criar e executar smoke test**

```python
def test_package_imports():
    from provas import capas, documento, imagens, motor, tema
    assert motor.QUALIDADES["normal"] == (200, 85)
```

Run: `python -m pytest tests/test_smoke.py -v`

Expected: `1 passed`.

- [ ] **Step 5: Criar o commit inicial seguro**

```powershell
git add .gitignore pyproject.toml provas assets Provas.pyw Provas.bat Provas.command provas_cli.py verificar.py empacotar.py README.md docs tests
git commit -m "chore: establish photobook project"
```

---

### Task 2: Modelo editorial e templates

**Files:**
- Create: `provas/modelos.py`
- Create: `provas/templates.py`
- Create: `tests/test_templates.py`

**Interfaces:**
- Produces: `PhotoInfo`, `Rect`, `Slot`, `Template`, `PagePlan`, `BookPlan`, `catalog()`, `compatible_templates()` e `fit_contain()`.

- [ ] **Step 1: Escrever testes geométricos que falham**

```python
def test_fit_contain_preserves_two_by_three():
    fitted = fit_contain(Rect(0, 0, 300, 180), ratio=1.5)
    assert fitted.width / fitted.height == pytest.approx(1.5)
    assert fitted.x >= 0 and fitted.right <= 300
    assert fitted.y >= 0 and fitted.bottom <= 180

def test_catalog_only_contains_supported_counts():
    assert {len(t.slots) for t in catalog()} <= {1, 2, 4}

def test_proof_slots_reserve_caption_space():
    template = next(t for t in catalog() if len(t.slots) == 2)
    assert all(slot.caption.height > 0 for slot in template.resolve("prova"))
```

Run: `python -m pytest tests/test_templates.py -v`

Expected: imports fail because the modules do not exist.

- [ ] **Step 2: Implementar tipos imutáveis**

```python
@dataclass(frozen=True)
class PhotoInfo:
    id: str
    path: str
    label: str
    width: int
    height: int
    index: int
    sharpness: float = 0.0
    exposure: float = 0.5
    density: float = 0.5
    quality: float = 0.5
    similarity_group: int | None = None

@dataclass(frozen=True)
class PagePlan:
    number: int
    template_id: str
    photo_ids: tuple[str, ...]
    role: str

@dataclass(frozen=True)
class BookPlan:
    seed: int
    mode: str
    cover_photo_ids: tuple[str, ...]
    pages: tuple[PagePlan, ...]
```

Also define `Rect`, `Slot` and `Template` with normalized page geometry, accepted orientations, hierarchy weight and density class.

- [ ] **Step 3: Implementar catálogo curado**

Create at least 12 templates: three single-photo, five two-photo and four four-photo. `fit_contain()` centers a proportion-preserving rectangle. `compatible_templates()` rejects orientation mismatch and the immediately previous template.

- [ ] **Step 4: Run tests and commit**

Run: `python -m pytest tests/test_templates.py -v`

Expected: all tests pass.

```powershell
git add provas/modelos.py provas/templates.py tests/test_templates.py
git commit -m "feat: add editorial layout model"
```

---

### Task 3: Análise local e narrativa

**Files:**
- Create: `provas/analise.py`
- Create: `provas/narrativa.py`
- Modify: `provas/imagens.py`
- Create: `tests/test_analise.py`
- Create: `tests/test_narrativa.py`

**Interfaces:**
- Consumes: `imagens.Foto`, `PhotoInfo`.
- Produces: `analisar_fotos(fotos, cancelar, progresso) -> AnalysisResult`, `agrupar_fotos(items, seed) -> tuple[PhotoGroup, ...]` and `score_cover(items) -> list[PhotoInfo]`.

- [ ] **Step 1: Escrever testes de análise**

Cover natural order, corrupt-file reporting, brightness bounds, sharpness ordering and perceptual similarity. Require `AnalysisResult.photos` to retain source index and `AnalysisResult.failures` to contain `(filename, message)`.

- [ ] **Step 2: Escrever testes narrativos**

Assert every photo ID occurs once, group sizes are in `{1, 2, 4}`, displacement is at most 8 source positions, opening and ending are single-photo groups, and at most two dense groups are consecutive.

- [ ] **Step 3: Confirmar que falham**

Run: `python -m pytest tests/test_analise.py tests/test_narrativa.py -v`

Expected: new module imports fail.

- [ ] **Step 4: Implementar análise sem dependência remota**

Use grayscale local variance for sharpness, histogram mean/clipping for exposure, edge density for informational density and a 16×16 RGB difference hash for similarity. Normalize every score to `0.0..1.0`; do not add OpenCV.

- [ ] **Step 5: Implementar agrupamento narrativo determinístico**

Define `PhotoGroup(photo_ids, role, density)`. Use `random.Random(seed)`, prefer adjacent complementary photographs, limit moves to an 8-photo window, reserve distinct strong images for opening/ending and split leftover count 3 as `1+2`.

- [ ] **Step 6: Run tests and commit**

Run: `python -m pytest tests/test_analise.py tests/test_narrativa.py -v`

Expected: all tests pass.

```powershell
git add provas/analise.py provas/narrativa.py provas/imagens.py tests/test_analise.py tests/test_narrativa.py
git commit -m "feat: build local narrative analysis"
```

---

### Task 4: Compositor determinístico e capa editorial

**Files:**
- Create: `provas/compositor.py`
- Modify: `provas/capas.py`
- Create: `tests/test_compositor.py`
- Create: `tests/test_capas_editoriais.py`

**Interfaces:**
- Produces: `compose(photos, mode, seed, cover_ids=()) -> BookPlan`, `validate_plan(plan, photos) -> tuple[str, ...]`, `selecionar_capa()` and `gerar_mosaico_editorial()`.

- [ ] **Step 1: Escrever testes do compositor**

Test deterministic seeds, distinct valid results for distinct seeds, exact one-time coverage, no repeated neighboring templates, at most two dense pages, opening/ending roles and unchanged manual cover IDs.

- [ ] **Step 2: Escrever testes da capa**

Assert 6-12 unique IDs, preservation of manual IDs, similarity penalty and distribution across the source sequence. Generate a 1600×1131 cover from colored fixtures and assert exact size, non-empty title-safe zone and occurrence of every chosen source color.

- [ ] **Step 3: Confirmar que falham**

Run: `python -m pytest tests/test_compositor.py tests/test_capas_editoriais.py -v`

Expected: missing APIs.

- [ ] **Step 4: Implementar composição e reparo**

Score templates by orientation, narrative role, density rhythm and recency. Use seeded weighted choice, run a final repair pass and raise `ValueError` whenever `validate_plan()` reports an invariant violation.

- [ ] **Step 5: Implementar capa padrão**

Use one editorial mosaic with 6-12 photos and a title-safe area. Crop-to-fill is allowed only inside cover cells. Manual replacements remain fixed across whole-book regeneration.

- [ ] **Step 6: Run tests and commit**

Run: `python -m pytest tests/test_compositor.py tests/test_capas_editoriais.py -v`

Expected: all tests pass.

```powershell
git add provas/compositor.py provas/capas.py tests/test_compositor.py tests/test_capas_editoriais.py
git commit -m "feat: compose editorial books and covers"
```

---

### Task 5: Renderizador, prévia e exportação atômica

**Files:**
- Modify: `provas/documento.py`
- Modify: `provas/motor.py`
- Create: `provas/preview.py`
- Create: `tests/test_documento_editorial.py`
- Create: `tests/test_motor_editorial.py`

**Interfaces:**
- Consumes: `BookPlan`, resolved templates and analyzed photo map.
- Produces: `Documento.render_page()`, `gerar_plano(config)`, `gerar_preview(config, plan)` and `exportar(config, plan)`.

- [ ] **Step 1: Escrever testes de PDF**

Generate single vertical, single horizontal, mixed pair and four-photo PDFs in both modes. Reopen with PyMuPDF and assert A4 landscape dimensions, expected image count, filename text only in `prova`, metadata and page count.

- [ ] **Step 2: Escrever teste de exportação atômica**

Monkeypatch `Documento.salvar` to fail after a temporary file is created. Assert an existing destination remains byte-for-byte unchanged and no `.tmp` survives.

- [ ] **Step 3: Confirmar que falham**

Run: `python -m pytest tests/test_documento_editorial.py tests/test_motor_editorial.py -v`

Expected: new render/export APIs are absent.

- [ ] **Step 4: Implementar renderização por slots**

Keep `Tipografia`; use template slots instead of `melhor_grade()` in the new path. Apply `fit_contain()` to every internal image. Render captions into independent rectangles with ellipsis for exceptionally long names. Embed watermark before JPEG encoding only in `prova` mode.

- [ ] **Step 5: Implementar pipeline e salvamento atômico**

Extend `Config`:

```python
modo: str = "prova"
semente: int = 0
cover_ids: tuple[str, ...] = ()
```

Write to `<output>.tmp`, close and reopen it for validation, then call `os.replace(temp, output)`. Remove temporary files in `finally`.

- [ ] **Step 6: Implementar prévia compartilhada**

`preview.render_page_thumbnail(plan, page_number, assets, width)` must use the same resolved template and caption rules as `Documento`; cache by `(seed, page_number, mode, width)`.

- [ ] **Step 7: Run tests and commit**

Run: `python -m pytest tests/test_documento_editorial.py tests/test_motor_editorial.py -v`

Expected: all tests pass.

```powershell
git add provas/documento.py provas/motor.py provas/preview.py tests/test_documento_editorial.py tests/test_motor_editorial.py
git commit -m "feat: render editorial plans to PDF"
```

---

### Task 6: Projetos, regeneração e diagnóstico

**Files:**
- Create: `provas/projeto.py`
- Create: `tests/test_projeto.py`

**Interfaces:**
- Consumes: `motor.Config`, `BookPlan`.
- Produces: `ProjectState`, `save_project(path, state)`, `load_project(path)`, `regenerate(state)` and `undo_regeneration(state)`.

- [ ] **Step 1: Escrever testes de round-trip**

Assert UTF-8 paths and accents survive, schema version equals `1`, missing source files are reported by exact path, regeneration retains manual cover IDs, and undo restores previous seed and plan.

- [ ] **Step 2: Confirmar que falham**

Run: `python -m pytest tests/test_projeto.py -v`

Expected: `ModuleNotFoundError: provas.projeto`.

- [ ] **Step 3: Implementar JSON versionado**

```python
@dataclass(frozen=True)
class ProjectState:
    schema_version: int
    source_folder: str
    config: dict[str, object]
    cover_photo_ids: tuple[str, ...]
    current_plan: BookPlan
    previous_plan: BookPlan | None = None
```

Store configuration, paths, cache keys, cover IDs and plans; never duplicate photographs. Write UTF-8 JSON atomically with `ensure_ascii=False`.

- [ ] **Step 4: Implementar diagnóstico**

Expose counts for valid/failed photos, pages, 1/2/4 distribution, approximate preserved order, low-quality warnings and overly long album warning. Warnings never exclude internal photos automatically.

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest tests/test_projeto.py -v`

Expected: all tests pass.

```powershell
git add provas/projeto.py tests/test_projeto.py
git commit -m "feat: persist reversible photobook projects"
```

---

### Task 7: Mesa de edição PySide6

**Files:**
- Create: `provas/ui/__init__.py`
- Create: `provas/ui/main_window.py`
- Create: `provas/ui/sidebar.py`
- Create: `provas/ui/preview_grid.py`
- Create: `provas/ui/diagnostics.py`
- Create: `provas/ui/cover_dialog.py`
- Create: `provas/ui/workers.py`
- Create: `provas/ui/theme.qss`
- Modify: `provas/app.py`
- Create: `tests/test_ui_state.py`

**Interfaces:**
- Consumes: `ProjectState`, `motor.gerar_plano`, `preview.render_page_thumbnail`, `motor.exportar`.
- Produces: `MainWindow`, `AnalysisWorker`, `PreviewWorker`, `ExportWorker` and `provas.app.principal()`.

- [ ] **Step 1: Escrever testes de estado da interface**

With `QT_QPA_PLATFORM=offscreen`, assert initial disabled actions, mode switching, progress/cancel state, successful preview state, cover replacement, regeneration/undo and Portuguese failure banner. Call public controller methods, not pixel coordinates.

- [ ] **Step 2: Confirmar que falham**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_ui_state.py -v`

Expected: new UI modules are absent.

- [ ] **Step 3: Implementar shell aprovado**

Build the approved layout: 265 px workflow sidebar, fluid preview grid, 235 px diagnostic panel and 58 px top bar. Use QSS tokens `#111215`, `#191A1F`, `#F1F1F3`, `#9A9BA5`, and accent `#D84060`. Add visible focus rings, keyboard navigation and accessible contrast.

- [ ] **Step 4: Implementar workers canceláveis**

Workers emit:

```python
progress = Signal(int, str)
completed = Signal(object)
failed = Signal(str)
cancelled = Signal()
```

Each receives a `threading.Event`. Closing the window requests cancellation and waits without blocking Qt's event loop.

- [ ] **Step 5: Implementar prévia e capa**

Render thumbnails lazily, provide zoom, label page roles and preserve scroll position after regeneration. The cover dialog shows selected and remaining photographs; replacement preserves slot order and survives regeneration.

- [ ] **Step 6: Run tests and inspect**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_ui_state.py -v`

Expected: all UI tests pass.

Run: `python Provas.pyw`

Expected: approved mesa de edição at 1366×768 and 1920×1080, with no clipped controls at 125% Windows scaling.

- [ ] **Step 7: Commit**

```powershell
git add provas/ui provas/app.py tests/test_ui_state.py
git commit -m "feat: build professional editing desk"
```

---

### Task 8: CLI, documentação e pacote Windows

**Files:**
- Modify: `provas_cli.py`
- Modify: `verificar.py`
- Modify: `empacotar.py`
- Modify: `README.md`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: new `motor.Config`, project persistence and export pipeline.
- Produces: supported CLI and `dist/Fotolivro-Windows.zip`.

- [ ] **Step 1: Escrever testes CLI**

Test `--modo prova`, `--modo fotolivro`, `--semente 42`, invalid mode, project save/load and successful sample export. Assert exit codes and Portuguese output.

- [ ] **Step 2: Confirmar que falham**

Run: `python -m pytest tests/test_cli.py -v`

Expected: parser rejects new options.

- [ ] **Step 3: Atualizar CLI e diagnóstico**

Replace `--album` as documented interface with `--modo {prova,fotolivro}`, retaining `--album` as deprecated alias. Default to A4 horizontal and disable decorative rotation. Add `--semente`, `--salvar-projeto`, and `--abrir-projeto`. `verificar.py` reports Python, Pillow, PyMuPDF, PySide6, fonts and write permission.

- [ ] **Step 4: Atualizar documentação**

Document installation, two modes, narrative engine, cover replacement, regeneration, privacy, supported formats, RAW limitations, CLI, project files and migration from the old Provas app.

- [ ] **Step 5: Atualizar empacotamento**

Include QSS, icon and PySide6 platform plugins; exclude user `config.json` and logo. Output `dist/Fotolivro-Windows.zip` with executable and `LEIA-ME.txt`.

- [ ] **Step 6: Run tests, build and commit**

Run: `python -m pytest tests/test_cli.py -v`

Expected: all tests pass.

Run: `python verificar.py`

Expected: every required dependency reports `OK`.

Run: `python empacotar.py`

Expected: `dist/Fotolivro-Windows.zip` exists.

```powershell
git add provas_cli.py verificar.py empacotar.py README.md tests/test_cli.py
git commit -m "docs: ship editorial photobook workflow"
```

---

### Task 9: Verificação integral e regressão visual

**Files:**
- Create: `tests/test_end_to_end.py`
- Create: `tests/baselines/README.md`
- Modify: only defects discovered in prior modules.

**Interfaces:**
- Consumes: complete application.
- Produces: evidence that PDFs and packaged executable satisfy the spec.

- [ ] **Step 1: Criar ensaios sintéticos**

Generate 24 vertical, 24 horizontal and 32 mixed photographs with distinct colors, labels, broad/detail patterns and controlled duplicates.

- [ ] **Step 2: Escrever end-to-end test**

For every fixture and both modes: analyze, compose, preview, export, reopen PDF and verify A4 landscape size, page count, exact one-time internal coverage from the plan, captions only in proof mode, deterministic seed and zero unexpected failures.

- [ ] **Step 3: Executar suíte completa**

Run: `python -m pytest -v`

Expected: all tests pass with no warnings caused by project code.

- [ ] **Step 4: Renderizar para inspeção visual**

Use PyMuPDF at 120 dpi to render every generated page into `tmp/visual-qa/<case>/` and build contact sheets. Inspect cover, opening, dense sequences, pauses, ending, long labels and mixed orientations. Record accepted fixture names and seeds in `tests/baselines/README.md`; do not commit binary screenshots.

- [ ] **Step 5: Testar pacote fora da árvore de código**

Extract `dist/Fotolivro-Windows.zip` into a fresh temporary directory. Launch it with a synthetic folder and generate both modes. Confirm no dependency on source-tree paths.

- [ ] **Step 6: Commit**

```powershell
git add tests/test_end_to_end.py tests/baselines/README.md
git commit -m "test: verify editorial photobook end to end"
```

---

### Task 10: Publicar no GitHub

**Files:**
- Create: `.github/workflows/tests.yml`
- Create: `LICENSE` only if the user selects a public license.
- Modify: `README.md`

**Interfaces:**
- Consumes: green suite and final local Git history.
- Produces: GitHub repository `fotolivro-editorial` and pushed default branch.

- [ ] **Step 1: Confirmar visibilidade e licença**

Ask whether the repository is private or public. For public visibility, ask whether to use MIT or no open-source license. Never publish source publicly without explicit approval.

- [ ] **Step 2: Criar CI Windows**

Create `.github/workflows/tests.yml`:

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: windows-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install -e ".[dev]"
      - run: python -m pytest -v
        env:
          QT_QPA_PLATFORM: offscreen
```

- [ ] **Step 3: Executar verificação pré-publicação**

```powershell
git status --short
python -m pytest -v
git log --oneline --decorate -12
```

Expected: only intended CI/license files are uncommitted, all tests pass and history contains focused task commits.

- [ ] **Step 4: Commit da CI**

```powershell
git add .github/workflows/tests.yml README.md
git commit -m "ci: test photobook application on Windows"
```

If a `LICENSE` exists, include it in the same commit.

- [ ] **Step 5: Criar e enviar o repositório**

Private, safe default:

```powershell
gh repo create fotolivro-editorial --private --source . --remote origin --push
```

Use `--public` only after explicit approval.

- [ ] **Step 6: Verificar publicação**

Run: `gh repo view --web=false` and `gh run list --limit 3`.

Expected: repository metadata is accessible and the Windows workflow is queued or passing.
