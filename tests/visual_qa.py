"""Render E2E PDFs at 120 dpi and build reproducible contact sheets."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw


CURVED_COUNTS = (1, 3, 5, 6, 9)
CURVED_TONES = ("claros", "escuros", "mistos")
CURVED_LOGOS = ("horizontal", "vertical", "ausente")
CLASSIC_CASES = (
    ("automatico-horizontal", "landscape", "automatico", 0.5, 0.5, 1.0, "MEMÓRIAS"),
    ("automatico-vertical", "portrait", "automatico", 0.5, 0.5, 1.0, "MEMÓRIAS"),
    ("manual-esquerda", "landscape", "manual", 0.18, 0.5, 1.5, "NOSSA HISTÓRIA"),
    ("manual-direita", "landscape", "manual", 0.82, 0.5, 1.5, "NOSSA HISTÓRIA"),
    ("zoom-100", "portrait", "manual", 0.5, 0.42, 1.0, "ÁLBUM DE FAMÍLIA"),
    ("zoom-250", "portrait", "manual", 0.5, 0.42, 2.5, "MEMÓRIAS DE UMA TARDE"),
)


def render_pdf(
    pdf_path: Path, *, dpi: int = 120, contact_sheet: Path | None = None
) -> tuple[int, Path]:
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
    contact_sheet = contact_sheet or pdf_path.parent / f"{pdf_path.stem}-contact-sheet.png"
    sheet.save(contact_sheet, optimize=True)
    sheet.close()
    return len(pages), contact_sheet


def _qa_photo(path: Path, index: int, tone: str) -> None:
    portrait = index % 2 == 0
    size = (400, 600) if portrait else (600, 400)
    if tone == "claros":
        base = (208 + index % 4 * 8, 198 + index % 3 * 9, 184 + index % 5 * 7)
    elif tone == "escuros":
        base = (28 + index % 4 * 10, 34 + index % 3 * 9, 42 + index % 5 * 8)
    else:
        base = (220, 200, 178) if index % 2 == 0 else (30, 42, 58)
    image = Image.new("RGB", size, base)
    draw = ImageDraw.Draw(image)
    # A face-like editorial subject gives the visual inspector a stable focal point.
    cx = round(size[0] * (0.31 if index % 3 == 0 else 0.78))
    cy = round(size[1] * 0.34)
    radius = round(min(size) * 0.12)
    skin = (202, 151, 122) if tone != "escuros" else (142, 94, 74)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=skin)
    draw.ellipse((cx - radius // 3, cy - radius // 6, cx - radius // 6, cy), fill=(35, 28, 28))
    draw.ellipse((cx + radius // 6, cy - radius // 6, cx + radius // 3, cy), fill=(35, 28, 28))
    draw.arc((cx - radius // 3, cy, cx + radius // 3, cy + radius // 2), 10, 170, fill=(90, 38, 42), width=3)
    draw.rectangle((22, size[1] - 54, min(size[0] - 22, 250), size[1] - 20), fill=(246, 244, 238))
    draw.text((32, size[1] - 44), path.stem, fill=(22, 24, 27))
    image.save(path, "JPEG", quality=94, subsampling=0)
    image.close()


def _synthetic_face_detector(image: Image.Image):
    """Locate the deliberately skin-coloured QA face without pretending Haar saw it."""
    from provas.enquadramento import FaceBox

    rgb = image.convert("RGB")
    try:
        coordinates = [
            (index % rgb.width, index // rgb.width)
            for index, (red, green, blue) in enumerate(rgb.get_flattened_data())
            if red - green >= 28 and green - blue >= 12 and red >= 115
        ]
    finally:
        rgb.close()
    if not coordinates:
        return ()
    left = min(x for x, _y in coordinates)
    right = max(x for x, _y in coordinates) + 1
    top = min(y for _x, y in coordinates)
    bottom = max(y for _x, y in coordinates) + 1
    return (
        FaceBox(
            left / image.width,
            top / image.height,
            (right - left) / image.width,
            (bottom - top) / image.height,
            confidence=1.0,
        ),
    )


def _qa_logo(path: Path, orientation: str) -> None:
    size = (420, 105) if orientation == "horizontal" else (140, 360)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    inset = 8
    draw.rounded_rectangle(
        (inset, inset, size[0] - inset, size[1] - inset),
        radius=18,
        fill=(248, 248, 244, 255),
        outline=(25, 28, 30, 255),
        width=5,
    )
    draw.text((size[0] * 0.18, size[1] * 0.42), "FANARA", fill=(20, 22, 24, 255))
    image.save(path)
    image.close()


def _build_overview(sheets: list[Path], output: Path, stem: str) -> Path:
    thumb_size = (300, 220)
    caption_height = 30
    columns = 5
    rows = math.ceil(len(sheets) / columns)
    overview = Image.new(
        "RGB",
        (columns * thumb_size[0], rows * (thumb_size[1] + caption_height)),
        (226, 224, 219),
    )
    drawing = ImageDraw.Draw(overview)
    for index, sheet_path in enumerate(sheets):
        with Image.open(sheet_path) as source:
            thumbnail = source.convert("RGB")
        thumbnail.thumbnail(thumb_size, Image.Resampling.LANCZOS)
        x = index % columns * thumb_size[0]
        y = index // columns * (thumb_size[1] + caption_height)
        overview.paste(thumbnail, (x, y))
        drawing.text(
            (x + 6, y + thumb_size[1] + 7),
            sheet_path.stem.removesuffix("-contact-sheet"),
            fill=(24, 25, 27),
        )
        thumbnail.close()
    path = output / f"{stem}-overview.png"
    overview.save(path, optimize=True)
    overview.close()
    return path


def build_curved_cases(output: Path, *, dpi: int = 120) -> tuple[Path, ...]:
    """Generate the approved curved-cover matrix and render every PDF at ``dpi``."""
    from provas import capas, motor
    from provas.enquadramento import frame_for_mask

    output.mkdir(parents=True, exist_ok=True)
    fixtures = output / "_fixtures"
    fixtures.mkdir(exist_ok=True)
    logos: dict[str, str] = {"ausente": ""}
    for orientation in ("horizontal", "vertical"):
        logo = fixtures / f"logo-{orientation}.png"
        _qa_logo(logo, orientation)
        logos[orientation] = str(logo)

    sheets: list[Path] = []
    for count in CURVED_COUNTS:
        for tone in CURVED_TONES:
            photos = fixtures / f"count-{count:02d}-{tone}"
            photos.mkdir(exist_ok=True)
            for index in range(count):
                photo = photos / f"RETRATO_{index + 1:02d}.jpg"
                _qa_photo(photo, index, tone)
            for logo_kind in CURVED_LOGOS:
                stem = f"count-{count:02d}-{tone}-{logo_kind}"
                pdf = output / f"{stem}.pdf"
                config = motor.Config(
                    str(photos),
                    saida=str(pdf),
                    titulo=f"Retratos {tone}",
                    estudio="Estúdio Fanara",
                    site="fanara.com.br",
                    logo=logos[logo_kind],
                    estilo_capa="curvas_editoriais",
                    modo="fotolivro",
                    qualidade="leve",
                    semente=8600 + count,
                )
                analysis = motor.analisar_plano(config)
                original_framer = capas.frame_for_mask
                capas.frame_for_mask = lambda image, size, focus: frame_for_mask(
                    image, size, focus, detector=_synthetic_face_detector
                )
                try:
                    motor.exportar(config, analysis.plan)
                finally:
                    capas.frame_for_mask = original_framer
                _page_count, sheet = render_pdf(
                    pdf, dpi=dpi, contact_sheet=output / f"{stem}-contact-sheet.png"
                )
                sheets.append(sheet)
    _build_overview(sheets, output, "curvas-editoriais")
    return tuple(sheets)


def build_classic_cases(output: Path, *, dpi: int = 120) -> tuple[Path, ...]:
    """Generate the approved single-photo classic-cover matrix."""
    from provas import capa_classica, motor

    output.mkdir(parents=True, exist_ok=True)
    fixtures = output / "_fixtures"
    fixtures.mkdir(exist_ok=True)
    sheets: list[Path] = []
    original_detector = capa_classica.enquadramento.detect_faces
    capa_classica.enquadramento.detect_faces = _synthetic_face_detector
    try:
        for index, (stem, orientation, mode, focus_x, focus_y, zoom, title) in enumerate(
            CLASSIC_CASES
        ):
            photos = fixtures / stem
            photos.mkdir(exist_ok=True)
            for photo_index in range(4):
                photo = photos / f"CAPA_{photo_index + 1:02d}.jpg"
                _qa_photo(photo, photo_index + index, "mistos")
                with Image.open(photo) as opened:
                    needs_rotation = (
                        orientation == "landscape" and opened.height > opened.width
                    ) or (
                        orientation == "portrait" and opened.width > opened.height
                    )
                    if needs_rotation:
                        landscape = opened.transpose(Image.Transpose.ROTATE_90)
                        landscape.save(photo, "JPEG", quality=94, subsampling=0)
                        landscape.close()
            manual_id = str(sorted(photos.glob("*.jpg"))[0]) if mode == "manual" else ""
            pdf = output / f"{stem}.pdf"
            config = motor.Config(
                str(photos), saida=str(pdf), titulo=title, estudio="ESTÚDIO FANARA",
                estilo_capa="classica", foto_capa_id=manual_id,
                capa_foco_x=focus_x, capa_foco_y=focus_y, capa_zoom=zoom,
                capa_enquadramento=mode, modo="fotolivro", qualidade="leve",
                semente=9100 + index,
            )
            analysis = motor.analisar_plano(config)
            motor.exportar(config, analysis.plan)
            _count, sheet = render_pdf(
                pdf, dpi=dpi, contact_sheet=output / f"{stem}-contact-sheet.png"
            )
            sheets.append(sheet)
    finally:
        capa_classica.enquadramento.detect_faces = original_detector
    _build_overview(sheets, output, "capa-classica")
    return tuple(sheets)


def build_page_cycle_case(output: Path, *, dpi: int = 120) -> Path:
    """Capture the per-page cycle affordance in its normal, busy and unavailable states."""
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    from provas.modelos import BookPlan, PagePlan
    from provas.ui import MainWindow

    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    for font_name in (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/segoeuil.ttf",
        "C:/Windows/Fonts/seguisym.ttf",
    ):
        QFontDatabase.addApplicationFont(font_name)
    app.setStyleSheet((Path(__file__).parents[1] / "provas" / "ui" / "theme.qss").read_text(encoding="utf-8"))
    plan = BookPlan(
        661, "prova", (),
        (
            PagePlan(1, "single-landscape", ("normal.jpg",), "opening"),
            PagePlan(2, "pair-asymmetric-left", ("ocupada-a.jpg", "ocupada-b.jpg"), "sequence"),
            PagePlan(3, "single-landscape", ("sem-alternativa.jpg",), "ending"),
        ),
    )
    previews = tuple(
        Image.new("RGB", (420, 297), color)
        for color in ("#f1ede4", "#c8d8e7", "#e6d1c5", "#d7dfd3")
    )
    window = MainWindow()
    window.resize(1093, 614)
    window.show()
    app.processEvents()
    try:
        window.select_folder(str(output))
        window.apply_analysis_result(plan)
        window.previews = previews
        window.preview_grid.set_previews(plan, previews)
        window.preview_grid.set_zoom(60)
        window.preview_grid.set_page_alternatives({1, 2})
        scrollbar = window.preview_grid.scroll_area.verticalScrollBar()
        scrollbar.setValue(min(24, scrollbar.maximum()))
        before_scroll = scrollbar.value()
        window.preview_grid.set_page_busy(2, True)
        app.processEvents()
        assert scrollbar.value() == before_scroll
        assert window.preview_grid.card(1).reload_button is not None
        assert window.preview_grid.card(1).reload_button.isEnabled()
        assert window.preview_grid.card(2).reload_button is not None
        assert not window.preview_grid.card(2).reload_button.isEnabled()
        assert window.preview_grid.card(2).reload_button.text() == "…"
        assert window.preview_grid.card(3).reload_button is not None
        assert not window.preview_grid.card(3).reload_button.isEnabled()
        target = output / "ui-1093x614-125.png"
        screenshot = window.grab()
        if screenshot.size().width() != 1093 or screenshot.size().height() != 614:
            screenshot = screenshot.scaled(1093, 614)
        assert screenshot.size().width() == 1093 and screenshot.size().height() == 614
        assert screenshot.save(str(target))
        render_pdf_contact = output / "ciclo-paginas-ui-capture.pdf"
        document = pymupdf.open()
        document.new_page(width=1093, height=614)
        document.save(render_pdf_contact)
        document.close()
        render_pdf(render_pdf_contact, dpi=dpi, contact_sheet=output / "ciclo-paginas-contact-sheet.png")
        return target
    finally:
        window.close()
        for image in previews:
            image.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, help="diretório que contém os PDFs E2E")
    parser.add_argument("--case", choices=("curvas-editoriais", "capa-classica", "ciclo-paginas"))
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.case == "curvas-editoriais":
        destination = args.output or args.root
        if destination is None:
            parser.error("--output é obrigatório para o caso curvas-editoriais")
        sheets = build_curved_cases(destination, dpi=args.dpi)
        print(f"Matriz curvas-editoriais: {len(sheets)} folhas -> {destination}")
        return 0
    if args.case == "capa-classica":
        destination = args.output or args.root
        if destination is None:
            parser.error("--output é obrigatório para o caso capa-classica")
        sheets = build_classic_cases(destination, dpi=args.dpi)
        print(f"Matriz capa-classica: {len(sheets)} folhas -> {destination}")
        return 0
    if args.case == "ciclo-paginas":
        destination = args.output or args.root
        if destination is None:
            parser.error("--output é obrigatório para o caso ciclo-paginas")
        screenshot = build_page_cycle_case(destination, dpi=args.dpi)
        print(f"QA ciclo-paginas: 1093x614 a 125% -> {screenshot}")
        return 0
    if args.root is None:
        parser.error("informe o diretório que contém os PDFs E2E")
    pdfs = sorted(args.root.rglob("*.pdf"))
    if not pdfs:
        parser.error(f"nenhum PDF encontrado em {args.root}")
    for pdf_path in pdfs:
        count, sheet = render_pdf(pdf_path, dpi=args.dpi)
        print(f"{pdf_path}: {count} páginas -> {sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
