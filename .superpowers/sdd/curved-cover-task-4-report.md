# Curved Cover Task 4 — relatório RED/GREEN/self-review

## Escopo entregue

- Criado `provas/identidade_capa.py` com `IdentityData`, `CoverWarning`,
  `CoverTextOverflow` e `render_identity`.
- Estendida `capas.Capa` de forma compatível com `identity_embedded=False`,
  `warnings=()` e `used_photo_ids=()`.
- Nenhuma integração com motor, UI, fotos ou exportação foi adicionada.

## RED

Os testes foram escritos antes de cada comportamento de produção e observados
falhando pelo motivo esperado:

1. `python -m pytest tests/test_identidade_capa.py::test_identity_records_are_immutable_and_overflow_is_a_value_error -q`
   — `ModuleNotFoundError: No module named 'provas.identidade_capa'`.
2. `python -m pytest tests/test_identidade_capa.py::test_each_text_field_is_deterministic_and_stays_inside_its_safe_rect -q`
   — três falhas por `ImportError: cannot import name 'render_identity'`.
3. `python -m pytest tests/test_identidade_capa.py::test_title_and_studio_have_distinct_balanced_lines_and_empty_optional_fields_are_omitted -q`
   — sobreposição detectada (`intersection.area == 5382`).
4. `python -m pytest tests/test_identidade_capa.py -k 'logo' -q`
   — quatro falhas: logo corrupto ainda classificado ausente e logos válidos
   ainda não renderizados.
5. `python -m pytest tests/test_capas_editoriais.py::test_legacy_cover_constructor_remains_valid_with_identity_metadata_defaults -q`
   — `AttributeError: 'Capa' object has no attribute 'identity_embedded'`.
6. `python -m pytest tests/test_identidade_capa.py::test_opaque_white_logo_background_uses_the_existing_cutout_behavior -q`
   — fundo branco permaneceu opaco (`(255, 255, 255) != (0, 0, 0)`).

## GREEN e verificação

Comando exigido:

```text
python -m pytest tests/test_identidade_capa.py tests/test_capas_editoriais.py -q
......................                                                   [100%]
22 passed
```

Regressões relevantes:

```text
python -m pytest tests/test_capa_curvas.py tests/test_compositor.py tests/test_smoke.py -q
..................................................                       [100%]
50 passed
```

Suíte completa (segunda execução, com timeout de 300 s):

```text
python -m pytest -q
........................................................................ [ 31%]
........................................................................ [ 62%]
........................................................................ [ 93%]
..............                                                           [100%]
230 passed em 105,8 s
```

Integridade do diff:

```text
git diff --check
exit 0
```

O Git apenas avisou que dois arquivos existentes serão normalizados de LF para
CRLF quando voltar a tocá-los; não houve erro de whitespace.

## Self-review

- Fontes usam `tema.SERIF` e `tema.SANS_MEDIO`, com fallback determinístico do
  Pillow. As sequências verificadas são título 54..32 (`-2`), estúdio 26..18
  (`-1`) e site 18..14 (`-1`), escaladas a partir de 1600×1131.
- Todo texto é medido antes do primeiro desenho; overflow usa a mensagem exata e
  não deixa renderização parcial nem reticências/truncamento.
- Título/estúdio ficam no `identity_safe_rect`, site no `site_rect` e logo no
  `logo_rect`; título e estúdio formam linhas centrais sem interseção.
- Logos locais recebem EXIF transpose, recorte alfa compatível com o projeto,
  contenção proporcional e `imagens.logo_bicolor` em paleta escura. Temporários
  e arquivos são fechados, enquanto o canvas do chamador permanece aberto.
- Ausência/caminho inexistente gera exatamente `logo_ausente`; formato corrupto
  ou ilegível gera exatamente `logo_ilegivel`; falhas não inserem placeholder.
- Pixels determinísticos, alfa, orientação horizontal/vertical, EXIF e contraste
  claro/escuro estão cobertos.
- O mosaico continua usando o construtor legado `Capa(image, anchor)` e a suíte
  completa passou sem alteração de comportamento.

## Commit

Mensagem: `feat: compose curved cover identity`.

## Preocupações

Nenhuma preocupação funcional aberta. A primeira execução da suíte completa
atingiu o timeout operacional de 120 s sem falha; repetida com 300 s, concluiu
verde em 105,8 s.

## Anexo — correções da revisão

### RED

1. `python -m pytest tests/test_capa_curvas.py::test_every_orbit_mask_keeps_the_lower_right_site_region_empty -q`
   reproduziu a invasão de `site_rect`: variantes 2–9 falharam com pixels dos
   slots `hero_right`, `right_lower` ou `lower_right` dentro da faixa reservada.
2. `python -m pytest tests/test_identidade_capa.py::test_logo_content_keeps_alpha_and_reaches_4_5_contrast -q`
   falhou para logo branco sobre fundo claro com contraste `1.097 < 4.5`.
3. `python -m pytest tests/test_identidade_capa.py::test_logo_contrast_is_measured_against_canvas_pixels_under_its_alpha -q`
   falhou nos dois cenários em que a paleta e os pixels locais divergiam,
   provando que a implementação ainda media apenas `palette.fundo`.

### GREEN

- `render_mask` agora subtrai a faixa normalizada de `site_rect` de qualquer
  slot. Isso cobre todos os nomes usados pelas variantes 1–9 sem alterar
  `identity_safe_rect`, `logo_rect` ou os bounds dos slots. Os snapshots de
  cobertura do `lower_right` foram atualizados em 1600×1131 e 800×566.
- Um teste de composição cola fotos reais pelas máscaras e confirma que o site
  é desenhado no fundo, sem qualquer pixel fotográfico sob o texto.
- O logo é medido no conteúdo não transparente contra os pixels reais do canvas
  sob seu alfa. A luminância relativa usa conversão sRGB linear; abaixo de
  `4.5:1`, uma versão preta ou branca (a de maior contraste) substitui somente o
  RGB e conserva o alfa. Logos já contrastantes permanecem inalterados.

Verificação final solicitada:

```text
python -m pytest tests/test_identidade_capa.py tests/test_capa_curvas.py tests/test_capas_editoriais.py -q
......................................................................   [100%]
70 passed

git diff --check
exit 0
```

O único output adicional foi o aviso de normalização LF→CRLF do Git; não houve
erro de whitespace. Nenhuma integração com motor, UI ou fotos foi adicionada.
