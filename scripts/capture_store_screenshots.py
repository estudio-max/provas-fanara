r"""Capturas da janela do app para a ficha da Microsoft Store (1600x900 PNG).

    python scripts/capture_store_screenshots.py <pasta do ensaio> [logotipo]

Espera que os PDFs de demonstração já existam em `tmp/site-demo/`, gerados com
a mesma semente para que as capturas mostrem a mesma diagramação:

    python provas_cli.py "<pasta>" -o tmp/site-demo/classica-real-fotolivro.pdf \
        --modo fotolivro --capa classica --semente 71 -q alta --sobrescrever

Repita trocando `--modo prova` (para `classica-prova.pdf`) e
`--capa curvas_editoriais` (para `curvas.pdf`). Sai em `site/store/`.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "1")

import pypdfium2 as pdfium
from PIL import Image
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from provas.modelos import BookPlan, PagePlan
from provas.ui import MainWindow

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "site" / "store"
LARGURA, ALTURA = 1600, 900

# O ensaio e o logotipo da marca d'água vêm da linha de comando; os padrões são
# os que geraram as capturas publicadas.
ENSAIO = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\estud\OneDrive\Imagens\RAW\eu selfie"
LOGOTIPO = sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\estud\Downloads\logo transp grande.png"


def paginas(pdf: Path, quantas: int) -> tuple[Image.Image, ...]:
    documento = pdfium.PdfDocument(str(pdf))
    return tuple(
        documento[indice].render(scale=1.4).to_pil().convert("RGB")
        for indice in range(min(quantas, len(documento)))
    )


def plano(modo: str, quantidade: int) -> BookPlan:
    paginas_plano = tuple(
        PagePlan(
            numero,
            "solo-landscape",
            (f"page-{numero}.jpg",),
            "opening" if numero == 1 else "ending" if numero == quantidade else "narrative",
        )
        for numero in range(1, quantidade + 1)
    )
    return BookPlan(71, modo, ("cover.jpg",), paginas_plano)


def capturar(janela: MainWindow, nome: str) -> Path:
    for _ in range(6):
        QApplication.processEvents()
    caminho = SAIDA / nome
    janela.grab().save(str(caminho))
    return caminho


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    for fonte in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuil.ttf",
                  "C:/Windows/Fonts/seguisym.ttf"):
        QFontDatabase.addApplicationFont(fonte)
    app.setStyleSheet((RAIZ / "provas" / "ui" / "theme.qss").read_text(encoding="utf-8"))

    janela = MainWindow()
    janela.resize(LARGURA, ALTURA)
    janela.show()
    janela.select_folder(ENSAIO)
    identidade = {
        "titulo": "João Fanara",
        "estudio": "Estúdio Fanara",
        "site": "https://fanara.com.br",
        "logo": LOGOTIPO,
    }

    feitos = []
    for nome, modo, pdf in (
        ("01-mesa-de-edicao-fotolivro.png", "fotolivro", "classica-real-fotolivro.pdf"),
        ("02-modo-prova.png", "prova", "classica-prova.pdf"),
    ):
        previas = paginas(RAIZ / "tmp" / "site-demo" / pdf, 13)
        janela.set_mode(modo)
        janela.apply_analysis_result(plano(modo, len(previas) - 1))
        janela.set_cover_identity(identidade, request_preview=False)
        janela.apply_preview_ready(previas)
        feitos.append(capturar(janela, nome))

    previas = paginas(RAIZ / "tmp" / "site-demo" / "curvas.pdf", 13)
    janela.set_mode("fotolivro")
    janela.set_cover_style("curvas_editoriais")
    janela.apply_analysis_result(plano("fotolivro", len(previas) - 1))
    janela.set_cover_identity(identidade, request_preview=False)
    janela.apply_preview_ready(previas)
    feitos.append(capturar(janela, "03-capa-curvas.png"))

    janela.close()
    print("\n".join(str(caminho) for caminho in feitos))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
