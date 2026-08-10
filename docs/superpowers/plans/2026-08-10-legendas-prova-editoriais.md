# Legendas editoriais do modo Prova — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remover a faixa de fundo dos nomes de arquivo e centralizar cada legenda em relação à própria fotografia no modo Prova.

**Architecture:** `Documento` continuará sendo a fronteira única de renderização usada por prévia e PDF. Os dois caminhos existentes de página interna receberão o mesmo contrato de legenda: nenhum preenchimento, fitting limitado à largura física da foto e escrita centralizada pelo eixo da foto.

**Tech Stack:** Python 3.10+, PyMuPDF 1.24+, Pillow 10+, pytest, Poppler/PyMuPDF para QA visual.

## Global Constraints

- A mudança vale somente para o modo `prova`; o fotolivro limpo continua sem nomes de arquivo.
- Cada nome é centralizado horizontalmente pelo eixo da própria fotografia.
- A área reservada abaixo da fotografia permanece e a proporção da imagem não muda.
- Não existe retângulo, faixa, cápsula ou preenchimento atrás da legenda.
- Nomes longos usam elipse e permanecem dentro da largura da própria fotografia.
- Prévia e PDF usam exatamente a mesma regra.

---

### Task 1: Renderizar legendas individuais limpas e centralizadas

**Files:**
- Modify: `provas/documento.py:286-312`
- Modify: `provas/documento.py:356-380`
- Modify: `tests/test_documento_editorial.py`
- Modify: `tests/visual_qa.py` somente se necessário para gerar o caso de inspeção

**Interfaces:**
- Consumes: `Documento.render_page(page_plan, template, assets)` e `Documento.cartao(...)`.
- Produces: a mesma API pública, com aparência consistente entre renderer editorial e renderer legado.

- [ ] **Step 1: Escrever RED geométrico e estrutural**

Criar um PDF de prova com duas fotos de proporções diferentes. Inspecionar `page.get_drawings()` e `page.get_text("words")`: não deve existir desenho preenchido cobrindo os retângulos de legenda; o centro horizontal de cada palavra deve coincidir, com tolerância de 0,75 pt, com o centro do retângulo físico da foto correspondente.

```python
assert not any(
    drawing.get("fill") is not None and drawing["rect"].intersects(caption_rect)
    for drawing in page.get_drawings()
)
word_rect = pymupdf.Rect(*caption_words[0][:4])
assert (word_rect.x0 + word_rect.x1) / 2 == pytest.approx(image_rect.x0 + image_rect.width / 2, abs=.75)
```

- [ ] **Step 2: Confirmar o RED pela faixa e alinhamento atuais**

Run: `python -m pytest tests/test_documento_editorial.py -k "caption and centered" -q`

Expected: FAIL porque `render_page` desenha `self.p.painel` e escreve a partir de `caption_rect.x0 + 4.0`.

- [ ] **Step 3: Implementar a legenda limpa no renderer editorial**

Remover apenas o `draw_rect(... fill=self.p.painel)` da legenda. Calcular fitting pela largura física da foto menos 8 pt e escrever pelo centro da foto:

```python
available_width = max(1.0, image_rect.width - 8.0)
label = self.tipo.encaixar(asset.label, NOME_SANS_MEDIO, font_size, available_width, 0.25)
center_x = (image_rect.x0 + image_rect.x1) / 2
self.tipo.escrever(
    page, center_x, baseline, label,
    NOME_SANS_MEDIO, font_size, self.p.apagado, 0.25, "centro",
)
```

- [ ] **Step 4: Alinhar o renderer legado sem alterar a fotografia**

Em `Documento.cartao`, deixar de preencher o cartão inteiro com `self.p.painel`; manter inserção, moldura e altura reservada. O fitting continua limitado a `foto.width - 8.0` e a escrita permanece em `centro_x` com `alinhamento="centro"`.

- [ ] **Step 5: Verificar elipse, modo limpo e paridade**

Run: `python -m pytest tests/test_documento_editorial.py tests/test_templates.py tests/test_motor_editorial.py -q`

Expected: PASS; nomes longos contidos, nenhuma legenda em `fotolivro`, fotos com proporção preservada e thumbnails derivados do mesmo PDF.

- [ ] **Step 6: Gerar e inspecionar PDF real**

Gerar um caso Prova com duas fotos e renderizar a página em `tmp/pdfs/legendas-prova/`. Inspecionar o PNG: fundo contínuo, legenda centralizada sob cada foto, espaçamento uniforme, contraste discreto e ausência da faixa.

- [ ] **Step 7: Commit**

```powershell
git add provas/documento.py tests/test_documento_editorial.py tests/visual_qa.py
git commit -m "fix: center clean proof captions"
```
