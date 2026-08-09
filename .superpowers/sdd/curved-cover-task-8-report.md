# Curved Cover Task 8 — relatório de implementação

## Resultado

A gate final cobre capas `curvas_editoriais` com 1–9 fotografias nos modos
`prova` e `fotolivro`, sempre em A4 horizontal, sem repetição, com miolo
inalterado e primeira página do PDF pixel a pixel igual à prévia. Também cobre
os cinco cenários nomeados de logo inválido, identidade longa, logo ausente,
rosto junto ao limite seguro e escolha manual após nova diagramação.

O helper visual passou a aceitar
`--case curvas-editoriais --dpi 120 --output <pasta>` e gera 45 PDFs, 45 folhas
de contato e uma overview: quantidades 1/3/5/6/9 × tons claros/escuros/mistos ×
logo horizontal/vertical/ausente. Os PNGs permanecem em `tmp/` e não são
versionados.

## TDD e defeitos reproduzidos

- RED do novo contrato CLI visual: o helper antigo rejeitava
  `--case`, `--dpi` e `--output`; GREEN após o gerador determinístico.
- RED da overview: a matriz não produzia visão consolidada; GREEN após a folha
  mestre de 45 combinações.
- RED da fixture facial: o rosto geométrico não era detectável pelo Haar;
  GREEN com detector injetável exclusivo do QA. O Haar/OpenCV real e seus
  testes continuam separados e sem alteração.
- A inspeção original revelou rosto parcialmente cortado porque a fixture não
  entrava no caminho de proteção; a evidência foi regenerada com o detector
  explícito.
- A inspeção também reproduziu logo sobre um rosto confiante no slot superior
  esquerdo. Um teste falhou com a associação automática escolhendo a foto
  coberta. O compositor agora prefere outra candidata segura quando existe e
  mantém a ordem manual soberana; sem alternativa, preserva o warning PT-BR de
  área de risco.

## Evidência visual inspecionada

- `tmp/visual-qa/curvas-editoriais/curvas-editoriais-overview.png`, em resolução
  original, cobrindo as 45 combinações.
- Folhas individuais abertas em resolução original: 1 claro/logo vertical; 5
  misto/logo horizontal; 6 misto/sem logo; 9 claro/logo horizontal; 9
  escuro/logo vertical.
- Capas `page-001.png` abertas a 120 dpi para 1, 6 e 9 fotos, incluindo
  contraste claro/escuro e logo presente/ausente.
- Critérios observados: arcos antialias, núcleo central livre e legível,
  título/estúdio/site contidos, fotos únicas, áreas vazias intencionais,
  rostos dentro das máscaras e paridade de capa coberta automaticamente.

Seeds, fixtures e comando de reprodução estão registrados em
`tests/baselines/README.md`. Nenhum PNG foi adicionado ao Git.

## Verificação fresca

- `python -m pytest tests/test_end_to_end.py -q`: 39 passed em 279,3 s.
- `python -m pytest -v`: 336 passed em 259,85 s, sem warnings do projeto.
- `python verificar.py`: saída 0 para dependências, OpenCV 4.14, cascade Haar,
  fontes, escrita e pipeline A4.
- `python empacotar.py`: saída 0; ZIP Windows de 128.322.714 bytes, 301
  entradas.
- Testes pós-build de manifesto e execução fora da árvore: 2 passed em 16,8 s.
- Manifesto inspecionado: SHA-256 do EXE confere; nenhuma entrada privada
  (`config.json`, projeto, logo/foto do usuário, `.git`, `.codex` ou QA).
- `git diff --check`: saída 0.

O pacote será reconstruído novamente após o commit para que o campo
`git_commit` do manifesto referencie o HEAD definitivo desta Task.

## Correções da revisão independente

A primeira revisão encontrou dois findings Important, ambos reproduzidos com
RED antes da correção:

- logo ausente/corrompido influenciava a associação automática mesmo sem ser
  renderizado; um preflight raster alinhado ao renderer agora ativa a exclusão
  facial somente para logo realmente carregável. O loader/normalizador é único
  também para raster opaco totalmente branco, que se torna alpha vazio;
- a segurança do crop retangular não garantia a bbox facial dentro da curva;
  cada slot agora reutiliza sua máscara real e exige toda a bbox confiante em
  opacidade mínima 128. Sem candidata segura, o warning continua explícito.

O teste de rosto na borda verifica a cobertura real da bbox, estabilidade de
IDs e paridade PDF/prévia. Os casos de logo também registram estabilidade de
IDs. A linha extra no EOF deste relatório foi removida.
