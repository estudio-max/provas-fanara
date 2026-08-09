"""Estilos de capa: composições feitas com as fotos da própria sessão."""
from __future__ import annotations

import math
from collections.abc import Iterable
from hashlib import sha256
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

from . import imagens, tema
from .capa_curvas import layout_orbita, render_mask
from .enquadramento import MIN_FACE_CONFIDENCE, FrameResult, frame_for_mask
from .identidade_capa import CoverWarning, IdentityData, logo_is_renderable, render_identity
from .modelos import PhotoInfo

if TYPE_CHECKING:
    from .capa_classica import ClassicCrop

COVER_STYLES = ("classica", "mosaico", "curvas_editoriais")
ESTILOS = COVER_STYLES

SUPERAMOSTRAGEM = 3          # desenha a máscara ampliada e reduz, para borda lisa
_CLASSIC_PHOTO_TARGET = (1344, 825)


@dataclass(frozen=True)
class Capa:
    imagem: Image.Image
    ancora: float            # altura relativa (0..1) onde o bloco de texto começa
    identity_embedded: bool = False
    warnings: tuple[CoverWarning, ...] = ()
    used_photo_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoverPhoto:
    id: str
    image: Image.Image


def _classic_face_safe(photo: PhotoInfo, crop: ClassicCrop | None = None) -> bool:
    """Tell whether the exact classic crop keeps every confident face fully visible."""
    from . import capa_classica

    source = imagens.abrir(imagens.Foto(photo.path, photo.label))
    try:
        requested = crop or capa_classica.ClassicCrop()
        faces = tuple(capa_classica.enquadramento.detect_faces(source))
        box = capa_classica.resolve_classic_crop_box(
            source.size, _CLASSIC_PHOTO_TARGET, requested, faces
        )
        return all(
            face.x * source.width >= box.left
            and face.y * source.height >= box.top
            and (face.x + face.width) * source.width <= box.right
            and (face.y + face.height) * source.height <= box.bottom
            for face in faces
            if face.confidence >= MIN_FACE_CONFIDENCE
        )
    finally:
        source.close()


def selecionar_foto_classica(
    photos: Iterable[PhotoInfo],
    manual_id: str,
    crop: ClassicCrop | None = None,
) -> str:
    """Select one classic-cover photo without changing the caller-owned plan."""
    candidates = tuple(photos)
    by_id = {photo.id: photo for photo in candidates}
    if manual_id in by_id:
        return manual_id
    if not candidates:
        raise ValueError("A capa clássica exige ao menos uma fotografia válida.")

    def rank(photo: PhotoInfo) -> tuple[int, int, float, int, str]:
        quality = (
            photo.quality * 0.60
            + photo.sharpness * 0.18
            + photo.exposure * 0.14
            + photo.density * 0.08
        )
        return (
            -(photo.width > photo.height),
            -(_classic_face_safe(photo) if crop is None else _classic_face_safe(photo, crop)),
            -quality,
            photo.index,
            photo.id,
        )

    return min(candidates, key=rank).id


def _cover_metadata(photo: CoverPhoto, key: str, default: float) -> float:
    try:
        return float(photo.image.info.get(key, default))
    except (TypeError, ValueError):
        return default


def _candidate_score(
    photo: CoverPhoto,
    slot,
    seen_groups: set[object],
    seed: int,
    source_rank: int,
) -> tuple[float, float, int]:
    image_ratio = photo.image.width / photo.image.height
    slot_ratio = slot.bounds.width / slot.bounds.height
    orientation = -abs(math.log(image_ratio / slot_ratio)) * 0.45
    quality = (
        _cover_metadata(photo, "quality", 0.5) * 0.60
        + _cover_metadata(photo, "sharpness", 0.5) * 0.18
        + _cover_metadata(photo, "exposure", 0.5) * 0.14
        + _cover_metadata(photo, "density", 0.5) * 0.08
    )
    group = photo.image.info.get("similarity_group")
    diversity = 0.0
    if group is not None:
        diversity = 0.55 if group not in seen_groups else -0.35
    focus = photo.image.info.get("focus")
    focus_score = 0.0
    if isinstance(focus, (tuple, list)) and len(focus) == 2:
        try:
            focus_score = -math.dist(tuple(map(float, focus)), slot.preferred_focus) * 0.25
        except (TypeError, ValueError):
            pass
    has_metadata = any(
        key in photo.image.info
        for key in ("quality", "sharpness", "exposure", "density", "similarity_group", "focus")
    )
    seeded_tie = 0.0
    if has_metadata:
        digest = sha256(f"{seed}\0{slot.id}\0{photo.id}".encode("utf-8")).digest()
        seeded_tie = int.from_bytes(digest[:8], "big") / (2**64 - 1)
    return (orientation + quality + diversity + focus_score, seeded_tie, -source_rank)


def _face_overlaps_identity_rect(frame: FrameResult, slot, rect) -> bool:
    """Tell whether an identity overlay would hide a confidently detected face."""
    if slot.bounds.intersection(rect).area == 0:
        return False
    crop = frame.crop
    for face in frame.face_boxes:
        if face.confidence < MIN_FACE_CONFIDENCE:
            continue
        left = slot.bounds.x + (face.x - crop.x) / crop.width * slot.bounds.width
        top = slot.bounds.y + (face.y - crop.y) / crop.height * slot.bounds.height
        right = left + face.width / crop.width * slot.bounds.width
        bottom = top + face.height / crop.height * slot.bounds.height
        if left < rect.right and right > rect.x and top < rect.bottom and bottom > rect.y:
            return True
    return False


def _faces_inside_curve_mask(frame: FrameResult, slot, mask: Image.Image) -> bool:
    """Require every confident face box to remain in the opaque mask interior."""
    crop = frame.crop
    for face in frame.face_boxes:
        if face.confidence < MIN_FACE_CONFIDENCE:
            continue
        box = (
            math.floor(slot.bounds.x + (face.x - crop.x) / crop.width * slot.bounds.width),
            math.floor(slot.bounds.y + (face.y - crop.y) / crop.height * slot.bounds.height),
            math.ceil(
                slot.bounds.x
                + (face.x + face.width - crop.x) / crop.width * slot.bounds.width
            ),
            math.ceil(
                slot.bounds.y
                + (face.y + face.height - crop.y) / crop.height * slot.bounds.height
            ),
        )
        if box[0] < 0 or box[1] < 0 or box[2] > mask.width or box[3] > mask.height:
            return False
        with mask.crop(box) as region:
            if region.width <= 0 or region.height <= 0 or region.getextrema()[0] < 128:
                return False
    return True


def validate_cover_style(value: str) -> str:
    """Return a supported cover style or explain the valid choices in PT-BR."""
    if value not in COVER_STYLES:
        raise ValueError("Estilo de capa inválido. Use classica, mosaico ou curvas_editoriais.")
    return value


def _amostrar(itens: list, quantidade: int) -> list:
    """Escolhe `quantidade` itens distribuídos ao longo da lista inteira.

    Quando a malha tem mais células do que fotos, as fotos se repetem — mas
    percorridas em passo largo, para que cópias não caiam lado a lado.
    """
    total = len(itens)
    if total == 0:
        return []
    if quantidade <= total:
        passo = total / quantidade
        return [itens[min(total - 1, int(i * passo))] for i in range(quantidade)]
    passo = next((p for p in range(max(2, total // 3), total)
                  if math.gcd(p, total) == 1), 1)
    return [itens[(i * passo) % total] for i in range(quantidade)]


def _mascara_losango(largura: int, altura: int, vao: float) -> Image.Image:
    """Máscara suave de um losango inscrito, encolhido por `vao` pixels."""
    escala = SUPERAMOSTRAGEM
    mascara = Image.new("L", (largura * escala, altura * escala), 0)
    meia_largura = largura * escala / 2
    meia_altura = altura * escala / 2
    recuo = vao * escala
    ImageDraw.Draw(mascara).polygon(
        [(meia_largura, recuo), (largura * escala - recuo, meia_altura),
         (meia_largura, altura * escala - recuo), (recuo, meia_altura)], fill=255)
    return mascara.resize((largura, altura), Image.Resampling.LANCZOS)


def _centros_losango(largura: int, altura: int, passo_x: float, passo_y: float):
    """Centros de uma malha de losangos que cobre a página inteira."""
    linha = -1
    while (linha - 1) * passo_y / 2 <= altura:
        y = linha * passo_y / 2
        deslocamento = 0.0 if linha % 2 == 0 else passo_x / 2
        coluna = -1
        while (coluna - 1) * passo_x + deslocamento <= largura:
            yield (coluna * passo_x + deslocamento, y)
            coluna += 1
        linha += 1


def _malha_losangos(quantidade: int, largura: int, altura: int,
                    proporcao: float = 1.0) -> tuple[list, float, float]:
    """Escolhe o tamanho do losango cuja malha chega mais perto de `quantidade`.

    Abaixo de 3 colunas os losangos ficam grandes demais e o recorte engole a
    foto, então essa é a malha mais grossa permitida.
    """
    melhor = None
    for colunas in range(3, 26):
        passo_x = largura / colunas
        passo_y = passo_x * proporcao
        centros = list(_centros_losango(largura, altura, passo_x, passo_y))
        distancia = abs(len(centros) - quantidade)
        if melhor is None or distancia < melhor[0]:
            melhor = (distancia, centros, passo_x, passo_y)
    _, centros, passo_x, passo_y = melhor
    return centros, passo_x, passo_y


def _colar_losango(tela: Image.Image, miniatura: Image.Image, centro: tuple[float, float],
                   passo_x: float, passo_y: float, vao: float) -> None:
    largura = max(2, round(passo_x))
    altura = max(2, round(passo_y))
    x = round(centro[0] - largura / 2)
    y = round(centro[1] - altura / 2)
    # recorte alto: no losango a parte visível é a faixa do meio, onde o rosto deve cair
    recorte = imagens.recortar_para_preencher(miniatura, largura, altura, centro=(0.5, 0.12))
    tela.paste(recorte, (x, y), _mascara_losango(largura, altura, vao))


def _mosaico(miniaturas: list[Image.Image], largura: int, altura: int,
             paleta: tema.Paleta) -> Image.Image:
    return imagens.montar_mosaico(miniaturas, largura, altura, paleta)


def gerar_mosaico_editorial(items: list[Image.Image], width: int, height: int,
                            palette: tema.Paleta) -> Capa:
    """Render a crop-to-fill cover mosaic with a calm, solid title field.

    Unlike internal pages, cover cells may crop.  The reserved field is kept
    untextured so title rendering needs no decorative mask or contrast guess.
    """
    if width <= 0 or height <= 0:
        raise ValueError("Cover dimensions must be positive")
    anchor = 0.72
    mosaic_height = max(1, round(height * 0.66))
    canvas = Image.new("RGB", (width, height), palette.fundo_rgb)
    if items:
        mosaic = imagens.montar_mosaico(items, width, mosaic_height, palette)
        canvas.paste(mosaic, (0, 0))
    return Capa(canvas, anchor)


def gerar_curvas_editoriais(
    items: list[CoverPhoto],
    width: int,
    height: int,
    palette: tema.Paleta,
    identity: IdentityData,
    seed: int,
) -> Capa:
    """Compose one caller-owned photo into each slot of the balanced orbit."""
    if len({photo.id for photo in items}) != len(items):
        raise ValueError("A capa curva exige identificadores únicos para todas as fotos.")
    layout = layout_orbita(width, height, len(items))
    canvas = Image.new("RGB", (width, height), palette.fundo_rgb)
    remaining = list(items)
    manual_order = bool(items) and all(
        photo.image.info.get("manual_order") is True for photo in items
    )
    has_renderable_logo = logo_is_renderable(identity.logo_path)
    assigned_ids: list[str] = []
    seen_groups: set[object] = set()
    cover_warnings: list[CoverWarning] = []
    try:
        for slot in layout.slots:
            candidates = []
            mask = render_mask(slot, (width, height))
            try:
                eligible = remaining[:1] if manual_order else remaining
                for source_rank, photo in enumerate(eligible):
                    candidates.append(
                        (
                            photo,
                            frame_for_mask(
                                photo.image,
                                (slot.bounds.width, slot.bounds.height),
                                slot.preferred_focus,
                            ),
                            _candidate_score(photo, slot, seen_groups, seed, source_rank),
                        )
                    )
                ranked = (
                    candidates
                    if manual_order
                    else sorted(candidates, key=lambda candidate: candidate[2], reverse=True)
                )

                def is_safe_candidate(candidate) -> bool:
                    frame = candidate[1]
                    return frame.safe and _faces_inside_curve_mask(frame, slot, mask) and not (
                        has_renderable_logo
                        and _face_overlaps_identity_rect(frame, slot, layout.logo_rect)
                    )

                photo, framed, _ = (
                    ranked[0]
                    if manual_order
                    else next(
                        (candidate for candidate in ranked if is_safe_candidate(candidate)),
                        ranked[0],
                    )
                )
                if not is_safe_candidate((photo, framed, ())):
                    cover_warnings.append(
                        CoverWarning(
                            "rosto_em_area_de_risco",
                            "Um rosto pode ficar próximo à área de risco desta máscara; revise a capa.",
                        )
                    )
                crop_box = (
                    slot.bounds.x,
                    slot.bounds.y,
                    slot.bounds.right,
                    slot.bounds.bottom,
                )
                with mask.crop(crop_box) as local_mask:
                    canvas.paste(framed.image, crop_box[:2], local_mask)
            finally:
                for _, result, _ in candidates:
                    result.image.close()
                mask.close()
            remaining.remove(photo)
            assigned_ids.append(photo.id)
            group = photo.image.info.get("similarity_group")
            if group is not None:
                seen_groups.add(group)
        cover_warnings.extend(render_identity(canvas, layout, identity, palette))
        return Capa(
            canvas,
            0.34,
            identity_embedded=True,
            warnings=tuple(cover_warnings),
            used_photo_ids=tuple(assigned_ids),
        )
    except BaseException:
        canvas.close()
        raise


def _losango(miniaturas: list[Image.Image], largura: int, altura: int,
             paleta: tema.Paleta) -> Image.Image:
    centros, passo_x, passo_y = _malha_losangos(len(miniaturas), largura, altura)
    escolhidas = _amostrar(miniaturas, len(centros))
    tela = Image.new("RGB", (largura, altura), paleta.fundo_rgb)
    vao = 1.5
    for miniatura, centro in zip(escolhidas, centros):
        _colar_losango(tela, miniatura, centro, passo_x, passo_y, vao)
    return tela


def _destaque(miniaturas: list[Image.Image], largura: int, altura: int,
              heroi: Image.Image, paleta: tema.Paleta) -> Image.Image:
    """Mosaico esmaecido com um losango grande, aceso, no centro."""
    fundo = imagens.veu_para_texto(_mosaico(miniaturas, largura, altura, paleta),
                                   paleta, opacidade_base=0.66)
    lado_x = round(largura * 0.62)
    lado_y = round(lado_x * 1.06)
    if lado_y > altura * 0.50:
        lado_y = round(altura * 0.50)
        lado_x = round(lado_y / 1.06)
    centro = (largura // 2, round(altura * 0.36))

    # o filete é um losango um pouco maior colado por baixo da foto
    borda = max(2, round(largura * 0.0035))
    largura_borda, altura_borda = lado_x + 2 * borda, lado_y + 2 * borda
    cor_borda = (28, 28, 32) if paleta.claro else (236, 237, 240)
    fundo.paste(Image.new("RGB", (largura_borda, altura_borda), cor_borda),
                (centro[0] - largura_borda // 2, centro[1] - altura_borda // 2),
                _mascara_losango(largura_borda, altura_borda, 0))

    recorte = imagens.recortar_para_preencher(heroi, lado_x, lado_y, centro=(0.5, 0.32))
    fundo.paste(recorte, (centro[0] - lado_x // 2, centro[1] - lado_y // 2),
                _mascara_losango(lado_x, lado_y, 0))
    return fundo


def gerar(
    estilo: str,
    miniaturas: list[Image.Image] | list[CoverPhoto],
    largura: int,
    altura: int,
    paleta: tema.Paleta,
    *,
    identity: IdentityData | None = None,
    seed: int = 0,
) -> Capa:
    """Monta a capa no estilo pedido e diz onde o texto deve começar."""
    validate_cover_style(estilo)
    if estilo == "mosaico":
        return gerar_mosaico_editorial(miniaturas, largura, altura, paleta)  # type: ignore[arg-type]
    if identity is None:
        raise ValueError("A capa curvas_editoriais exige os dados de identidade.")
    return gerar_curvas_editoriais(
        miniaturas, largura, altura, paleta, identity, seed  # type: ignore[arg-type]
    )
