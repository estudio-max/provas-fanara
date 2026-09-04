# Curved Cover Task 3 — relatório RED/GREEN

Data: 2026-08-04
Escopo: enquadramento local e proteção facial, sem integração ao renderer/UI e sem empacotamento.

## Resultado

Status final: `DONE`.

Foram implementados:

- `FaceBox`, `CropRect` e `FrameResult` imutáveis;
- crop cover-style normalizado, com transformação fracionária direta e sem distorção;
- proteção da caixa facial completa dentro do inset seguro de 8%;
- melhor crop determinístico quando nem todos os rostos cabem;
- fallback local determinístico por contraste e foco preferido limitado a `[0, 1]`;
- detector OpenCV Haar local com parâmetros fixos, normalização e ordenação;
- diagnóstico PT-BR de NumPy, OpenCV e cascade;
- testes geométricos com detector injetável e smoke test do detector real.

## RED inicial

Comando:

```text
python -m pytest tests/test_enquadramento.py -q
```

Saída relevante:

```text
FFFFFFFFFFFFFFFFsFF [100%]
18 failed, 1 skipped
ModuleNotFoundError: No module named 'provas.enquadramento'
AttributeError: module 'verificar' has no attribute 'diagnosticar_cascade'
```

As falhas eram as esperadas: módulo, API e diagnósticos ainda não existiam. O smoke real foi ignorado porque `cv2` ainda não estava instalado.

## Dependências e investigação do ambiente

Estado inicial:

```text
PIL OK 12.3.0
numpy OK 2.5.1
cv2 ERRO ModuleNotFoundError No module named 'cv2'
pytest OK 9.1.1
```

Primeira instalação autorizada para desenvolvimento:

```text
python -m pip install "opencv-python-headless>=4.10"
Successfully installed opencv-python-headless-5.0.0.93
```

O wheel ABI3 instalou sem build, mas o binding OpenCV 5.0.0 carregado não expôs `CascadeClassifier`, embora declarasse o módulo `objdetect` compilado. A reprodução foi direta:

```text
version=5.0.0
CascadeClassifier=False
```

Verificação mínima com a linha 4.x:

```text
python -m pip install --force-reinstall "opencv-python-headless>=4.10,<5"
Successfully installed numpy-2.5.1 opencv-python-headless-4.14.0.94
```

Não houve build local. O OpenCV 4.14.0.94 expôs o Haar esperado e foi a versão usada nas verificações finais.

## GREEN intermediário e revisão

Após a implementação mínima, o primeiro GREEN revelou duas falhas:

```text
python -m pytest tests/test_enquadramento.py -q
2 failed, 17 passed
```

- a fixture de rostos inviáveis também os tornava inviáveis individualmente por estarem dentro do próprio inset da imagem; a fixture foi corrigida;
- OpenCV 5.0.0 não expunha `CascadeClassifier`; a linha 4.x confirmou a hipótese ambiental.

Depois dos ajustes:

```text
python -m pytest tests/test_enquadramento.py -q
19 passed
```

A revisão independente encontrou quantização da janela fracionária por `Image.crop()` antes do resize. Foram escritos dois novos testes RED:

```text
python -m pytest tests/test_enquadramento.py -q
2 failed, 19 passed
```

As falhas reproduziram:

- divergência de pixels entre crop inteiro + resize e amostragem fracionária direta;
- mensagem em inglês para imagem PIL fechada.

A correção usa `Image.Transform.EXTENT` com amostragem bicúbica diretamente no tamanho alvo e normaliza imagem fechada/ilegível para `ValueError` PT-BR.

GREEN focal final:

```text
python -m pytest tests/test_enquadramento.py -q
21 passed
```

O follow-up independente retornou zero findings Critical, Important ou Minor e `Ready: Yes`.

## Verificação final

Comando obrigatório:

```text
python -m pytest tests/test_enquadramento.py tests/test_cli.py -q
........................................ [100%]
40 passed
```

Suíte completa:

```text
python -m pytest -q
........................................................................ [ 34%]
........................................................................ [ 69%]
..............................................................           [100%]
206 passed
```

Diagnóstico:

```text
python verificar.py
[  ok ] NumPy 2.5.1 (mínimo 1.26)
[  ok ] OpenCV 4.14.0 (mínimo 4.10)
[  ok ] cascade Haar local carregado: haarcascade_frontalface_default.xml
[  ok ] pipeline editorial: PDF A4 paisagem, sem rotação decorativa
Tudo pronto.
```

Higiene do diff:

```text
git diff --check
exit 0
```

O Git emitiu apenas avisos informativos de que `pyproject.toml` e `verificar.py` serão convertidos de LF para CRLF quando tocados; não houve erro de whitespace.

## Impacto de dependência

- Runtime acrescentado: `opencv-python-headless>=4.10,<5` e `numpy>=1.26`.
- A detecção usa somente o cascade distribuído pelo OpenCV instalado localmente.
- Nenhuma imagem, métrica ou telemetria é enviada; não há chamadas de rede no código.
- A instalação via rede ocorreu somente no ambiente de desenvolvimento, após autorização explícita.

## Correção pós-revisão oficial

O finding oficial confirmou que o requisito aberto ainda permitiria reinstalar o wheel 5.0.0.93 incompatível. A correção foi aplicada em três ciclos TDD.

RED do pin de metadado:

```text
python -m pytest tests/test_enquadramento.py::test_project_pins_opencv_to_the_supported_4x_line -q
1 failed
AssertionError: assert '"opencv-python-headless>=4.10,<5"' in metadata
```

GREEN após fixar `opencv-python-headless>=4.10,<5`:

```text
python -m pytest tests/test_enquadramento.py::test_project_pins_opencv_to_the_supported_4x_line -q
1 passed
```

RED do diagnóstico de major incompatível:

```text
python -m pytest tests/test_enquadramento.py::test_verifier_lists_numpy_opencv_and_diagnoses_cascade tests/test_enquadramento.py::test_verifier_rejects_opencv_5_or_newer_even_if_cascade_api_is_present -q
2 failed
AssertionError: limite superior 5 ausente em DEPENDENCIAS
AssertionError: diagnosticar_dependencias() retornou 0 para OpenCV 5.0.0
```

GREEN após declarar suporte 4.x e rejeitar `major >= 5`:

```text
python -m pytest tests/test_enquadramento.py::test_verifier_lists_numpy_opencv_and_diagnoses_cascade tests/test_enquadramento.py::test_verifier_rejects_opencv_5_or_newer_even_if_cascade_api_is_present -q
2 passed
```

RED adicional para interpretar `major >= 5` literalmente, inclusive pré-release:

```text
python -m pytest tests/test_enquadramento.py::test_verifier_rejects_opencv_5_or_newer_even_if_cascade_api_is_present -q
.F. [100%]
1 failed, 2 passed
OpenCV 5.0.0rc1 foi aceito por ser menor que Version("5") segundo PEP 440
```

GREEN após comparar a release major antes do estado de pré-release:

```text
python -m pytest tests/test_enquadramento.py::test_verifier_rejects_opencv_5_or_newer_even_if_cascade_api_is_present -q
... [100%]
3 passed
```

Verificação combinada final:

```text
python -m pytest tests/test_enquadramento.py tests/test_cli.py -q
............................................ [100%]
44 passed

python verificar.py
[  ok ] OpenCV 4.14.0 (suporte: 4.10 até antes da versão 5)
[  ok ] cascade Haar local carregado: haarcascade_frontalface_default.xml
Tudo pronto.

git diff --check
exit 0
```

## Preocupações remanescentes

Nenhuma dentro da Task 3. Empacotamento e execução fora da árvore continuam deliberadamente não testados porque pertencem à Task 7.
