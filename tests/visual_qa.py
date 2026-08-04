"""Render E2E PDFs at 120 dpi and build reproducible contact sheets."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw


def render_pdf(pdf_path: Path, *, dpi: int = 120) -> tuple[int, Path]:
    pages_dir = pdf_path.parent / pdf_path.stem
    pages_dir.mkdir(parents=True, exist_ok=True)
    pages: list[Image.Image] = []
    with pymupdf.open(pdf_path) as document:
        for number, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
            output = pages_dir / f"page-{number:03d}.png"
            pixmap.save(output)
            with Image.open(output) as rendered:
                pages.append(rendered.convert("RGB"))

    thumb_width = 360
    thumb_height = round(thumb_width * 210 / 297)
    caption_height = 30
    columns = 3
    rows = math.ceil(len(pages) / columns)
    sheet = Image.new("RGB", (columns * thumb_width, rows * (thumb_height + caption_height)), "white")
    drawing = ImageDraw.Draw(sheet)
    for index, page in enumerate(pages):
        thumbnail = page.copy()
        thumbnail.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        x = index % columns * thumb_width
        y = index // columns * (thumb_height + caption_height)
        sheet.paste(thumbnail, (x, y))
        drawing.text(
            (x + 8, y + thumb_height + 7),
            f"{pdf_path.parent.name} / {pdf_path.stem} / pagina {index + 1}",
            fill="black",
        )
        thumbnail.close()
        page.close()
    contact_sheet = pdf_path.parent / f"{pdf_path.stem}-contact-sheet.png"
    sheet.save(contact_sheet, optimize=True)
    sheet.close()
    return len(pages), contact_sheet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="diretório que contém os PDFs E2E")
    args = parser.parse_args(argv)
    pdfs = sorted(args.root.rglob("*.pdf"))
    if not pdfs:
        parser.error(f"nenhum PDF encontrado em {args.root}")
    for pdf_path in pdfs:
        count, sheet = render_pdf(pdf_path)
        print(f"{pdf_path}: {count} páginas -> {sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
