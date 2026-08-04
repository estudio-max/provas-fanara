"""Pipeline: lê a pasta da sessão e escreve o PDF de provas."""
from __future__ import annotations

import io
import os
import statistics
import tempfile
import threading
from weakref import WeakValueDictionary
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date

import pymupdf
from PIL import Image

from . import capas, documento, imagens, preview, tema
from .analise import AnalysisResult, analisar_fotos
from .compositor import compose, validate_plan
from .modelos import BookPlan, PhotoInfo
from .templates import catalog

QUALIDADES = {
    "leve":   (150, 78),
    "normal": (200, 85),
    "alta":   (300, 91),
}

LADO_MINIATURA = 320          # miniaturas usadas no mosaico da capa
DPI_MOSAICO = 150


class _PublicationLock:
    """Weak-referenceable holder for one destination's publication lock."""

    __slots__ = ("lock", "__weakref__")

    def __init__(self) -> None:
        self.lock = threading.Lock()


_PUBLICATION_LOCKS: WeakValueDictionary[str, _PublicationLock] = WeakValueDictionary()
_PUBLICATION_LOCKS_GUARD = threading.Lock()


@dataclass
class Config:
    pasta: str
    saida: str = ""
    titulo: str = ""
    subtitulo: str = ""
    por_pagina: int = 4
    paisagem: bool = False
    girar_horizontais: bool = True
    qualidade: str = "normal"
    marca_dagua: bool = True
    mostrar_codigos: bool = True     # desligue os dois para virar um álbum
    marca_opacidade: float = 0.20
    marca_largura: float = 0.62
    logo: str = ""
    estudio: str = ""                # usado no cabeçalho quando não há logotipo
    site: str = ""                   # aparece no rodapé das páginas e no pé da capa
    cor_fundo: str = tema.FUNDO_PADRAO
    recursivo: bool = False
    capa_mosaico: bool = True
    estilo_capa: str = "mosaico"
    chamada: str = "Escolha suas favoritas"
    limite: int = 0            # 0 = todas; útil para gerar uma amostra rápida
    modo: str = "prova"
    semente: int = 0
    cover_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.cover_ids = tuple(self.cover_ids)

    def com_padroes(self) -> "Config":
        """Preenche título, subtítulo e caminho de saída a partir da pasta."""
        pasta = os.path.abspath(self.pasta.rstrip("\\/"))
        nome = os.path.basename(pasta) or pasta
        titulo = self.titulo.strip() or nome
        subtitulo = self.subtitulo.strip() or date.today().strftime("%d.%m.%Y")
        saida = self.saida.strip() or os.path.join(pasta, f"{nome} - provas.pdf")
        return Config(**{**self.__dict__, "pasta": pasta, "titulo": titulo,
                         "subtitulo": subtitulo, "saida": saida})


@dataclass
class Resultado:
    saida: str
    fotos: int
    paginas: int
    falhas: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class PlanAnalysisResult:
    """Plan plus recoverable source details needed by the editing desk."""

    plan: BookPlan
    photos: tuple[PhotoInfo, ...]
    failures: tuple[tuple[str, str], ...]


class Cancelado(Exception):
    pass


@dataclass
class _Preparada:
    jpeg: bytes
    proporcao: float
    rotulo: str
    miniatura: Image.Image


def _codificar(imagem: Image.Image, qualidade: int) -> bytes:
    buffer = io.BytesIO()
    imagem.save(buffer, format="JPEG", quality=qualidade, optimize=True,
                progressive=False, subsampling=1)
    return buffer.getvalue()


def _cancelled(cancelar: object | None) -> bool:
    if cancelar is None:
        return False
    if callable(cancelar):
        return bool(cancelar())
    is_set = getattr(cancelar, "is_set", None)
    return bool(is_set()) if callable(is_set) else bool(cancelar)


def _avisar(progresso, feito: int, total: int, mensagem: str, cancelar: object | None) -> None:
    if _cancelled(cancelar):
        raise Cancelado()
    if progresso:
        progresso(feito, total, mensagem)


def _analisar_config(
    config: Config,
    progresso=None,
    cancelar: object | None = None,
    *,
    require_photos: bool = True,
) -> AnalysisResult:
    fotos = imagens.listar_fotos(config.pasta, config.recursivo)
    if config.limite:
        fotos = fotos[:config.limite]
    if not fotos:
        raise ValueError("Nenhuma foto encontrada nessa pasta.")

    def progress(value: tuple[int, str]) -> None:
        percent, label = value
        _avisar(progresso, percent, 100, f"Analisando {label}", cancelar)

    result = analisar_fotos(fotos, cancelar=cancelar, progresso=progress)
    if _cancelled(cancelar):
        raise Cancelado()
    if require_photos and not result.photos:
        raise ValueError("Nenhuma foto pôde ser lida. Veja a lista de erros.")
    return result


def analisar_plano(
    config: Config,
    progresso=None,
    cancelar: object | None = None,
) -> PlanAnalysisResult:
    """Analyze once and retain recoverable details beside the composed plan."""
    config = config.com_padroes()
    if config.modo not in {"prova", "fotolivro"}:
        raise ValueError(f"Unsupported mode: {config.modo}")
    _avisar(progresso, 0, 100, "Procurando fotos…", cancelar)
    result = _analisar_config(config, progresso, cancelar)
    _avisar(progresso, 100, 100, "Compondo o fotolivro…", cancelar)
    plan = compose(result.photos, config.modo, config.semente, config.cover_ids)
    return PlanAnalysisResult(plan, result.photos, result.failures)


def gerar_plano(config: Config, progresso=None, cancelar: object | None = None) -> BookPlan:
    """Compatibility API returning only the motor-produced editorial plan."""
    return analisar_plano(config, progresso, cancelar).plan


def _proporcao_tipica(fotos, girar: bool, amostra: int = 8) -> float:
    """Razão largura/altura típica da sessão, para escolher a grade."""
    razoes = []
    for foto in fotos[:amostra]:
        try:
            imagem = imagens.abrir(foto) if foto.e_raw else Image.open(foto.caminho)
            largura, altura = imagem.size
            imagem.close()
        except Exception:
            continue
        if girar:
            razoes.append(min(largura, altura) / max(largura, altura))
        else:
            razoes.append(largura / altura)
    return statistics.median(razoes) if razoes else 2 / 3


def _prepare_render_assets(
    config: Config,
    plan: BookPlan,
    progresso=None,
    cancelar: object | None = None,
) -> tuple[dict[str, documento.RenderAsset], AnalysisResult]:
    """Load only plan-backed assets; never repair or recompose the supplied plan."""
    analysis = _analisar_config(config, progresso, cancelar, require_photos=False)
    by_id = {photo.id: photo for photo in analysis.photos}
    planned_ids = tuple(photo_id for page in plan.pages for photo_id in page.photo_ids)
    required_ids = tuple(dict.fromkeys((*planned_ids, *plan.cover_photo_ids)))
    missing = [photo_id for photo_id in required_ids if photo_id not in by_id]
    if missing:
        names = ", ".join(os.path.basename(photo_id) for photo_id in missing)
        raise ValueError(f"Fotos do plano não puderam ser lidas: {names}")

    planned_photos = [by_id[photo_id] for photo_id in planned_ids]
    errors = validate_plan(plan, planned_photos)
    if errors:
        raise ValueError("; ".join(errors))

    dpi, quality = QUALIDADES.get(config.qualidade, QUALIDADES["normal"])
    max_side = max(640, round(max(tema.A4_PAISAGEM) / 72 * dpi))
    watermark = None
    logo_path = config.logo.strip()
    if plan.mode == "prova" and config.marca_dagua and config.marca_opacidade > 0:
        if logo_path and os.path.exists(logo_path):
            logo = imagens.carregar_logo(logo_path)
            try:
                watermark = imagens.logo_branco(logo)
            finally:
                logo.close()
        else:
            fallback = f"{config.estudio} · PROVA" if config.estudio.strip() else "PROVA PARA SELEÇÃO"
            watermark = imagens.marca_textual(fallback)

    assets: dict[str, documento.RenderAsset] = {}
    total = len(required_ids)
    try:
        for index, photo_id in enumerate(required_ids, start=1):
            _avisar(progresso, index - 1, max(1, total), "Preparando fotos…", cancelar)
            info = by_id[photo_id]
            source = imagens.abrir(imagens.Foto(info.path, info.label))
            page_image = source
            resized = source
            try:
                resized = imagens.redimensionar(source, max_side)
                page_image = resized
                if watermark is not None:
                    page_image = imagens.aplicar_marca_dagua(
                        resized, watermark, config.marca_largura, config.marca_opacidade,
                    )
                assets[photo_id] = documento.RenderAsset(
                    photo_id, info.label, _codificar(page_image, quality),
                    page_image.width, page_image.height,
                )
            finally:
                seen: set[int] = set()
                for image in (page_image, resized, source):
                    if id(image) not in seen:
                        image.close()
                        seen.add(id(image))
            _avisar(progresso, index, max(1, total), f"Preparando fotos… {index}/{total}", cancelar)
    finally:
        if watermark is not None:
            watermark.close()
    return assets, analysis


def _logo_document(config: Config) -> tuple[bytes | None, float, tema.Paleta]:
    palette = tema.paleta(config.cor_fundo)
    logo_path = config.logo.strip()
    if not logo_path or not os.path.exists(logo_path):
        return None, 1200 / 630, palette
    logo = imagens.carregar_logo(logo_path)
    version = logo if palette.claro else imagens.logo_bicolor(logo)
    try:
        buffer = io.BytesIO()
        version.save(buffer, format="PNG")
        return buffer.getvalue(), version.width / version.height, palette
    finally:
        if version is not logo:
            version.close()
        logo.close()


def _new_editorial_document(config: Config, mode: str) -> documento.Documento:
    logo, logo_ratio, palette = _logo_document(config)
    return documento.Documento(
        config.titulo,
        config.subtitulo,
        True,
        documento.Tipografia(),
        logo,
        logo_ratio,
        nota_capa="CADA FOTO TRAZ SEU CÓDIGO LOGO ABAIXO" if mode == "prova" else "",
        estudio=config.estudio,
        site=config.site,
        paleta=palette,
        modo=mode,
    )


def _render_style_fingerprint(config: Config, mode: str) -> tuple[object, ...]:
    """Describe every config input that can alter an internal rendered page."""
    logo_path = config.logo.strip()
    logo_state: tuple[object, ...] = (os.path.abspath(logo_path), None, None)
    if logo_path:
        try:
            stat = os.stat(logo_path)
            logo_state = (os.path.abspath(logo_path), stat.st_size, stat.st_mtime_ns)
        except OSError:
            pass
    return (
        mode,
        config.titulo,
        config.subtitulo,
        config.estudio,
        config.site,
        config.cor_fundo,
        config.qualidade,
        config.marca_dagua,
        config.marca_opacidade,
        config.marca_largura,
        logo_state,
    )


def gerar_preview(
    config: Config,
    plan: BookPlan,
    width: int = 420,
    progresso=None,
    cancelar: object | None = None,
) -> tuple[Image.Image, ...]:
    """Render thumbnails for the supplied plan without composing a replacement."""
    config = config.com_padroes()
    assets, analysis = _prepare_render_assets(config, plan, progresso, cancelar)
    thumbnails = []
    if config.capa_mosaico and plan.cover_photo_ids:
        _avisar(progresso, 0, max(1, len(plan.pages) + 1), "Renderizando capa…", cancelar)
        cover_document = _new_editorial_document(config, plan.mode)
        try:
            rendered = _render_cover(
                cover_document,
                config,
                plan,
                {photo.id: photo for photo in analysis.photos},
            )
            if rendered:
                page = cover_document.pdf[0]
                scale = width / page.rect.width
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                thumbnails.append(
                    Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                )
        finally:
            cover_document.fechar()
    total = len(plan.pages) + len(thumbnails)
    style_fingerprint = _render_style_fingerprint(config, plan.mode)
    for index, page_plan in enumerate(plan.pages, start=1):
        offset = len(thumbnails)
        _avisar(progresso, offset + index - 1, max(1, total), "Renderizando prévia…", cancelar)
        thumbnails.append(
            preview.render_page_thumbnail(
                plan,
                page_plan.number,
                assets,
                width,
                document_factory=lambda: _new_editorial_document(config, plan.mode),
                style_fingerprint=style_fingerprint,
            )
        )
        _avisar(
            progresso,
            offset + index,
            max(1, total),
            f"Prévia… página {index}/{len(plan.pages)}",
            cancelar,
        )
    return tuple(thumbnails)


def _render_cover(
    doc: documento.Documento,
    config: Config,
    plan: BookPlan,
    photos: dict[str, PhotoInfo],
) -> bool:
    selected = [photos[photo_id] for photo_id in plan.cover_photo_ids if photo_id in photos]
    if not config.capa_mosaico or not selected:
        return False
    thumbnails: list[Image.Image] = []
    try:
        for info in selected:
            source = imagens.abrir(imagens.Foto(info.path, info.label))
            try:
                resized = imagens.redimensionar(source, LADO_MINIATURA)
                thumbnails.append(resized.copy() if resized is source else resized)
            finally:
                source.close()
        width = round(doc.tamanho[0] / 72 * DPI_MOSAICO)
        height = round(doc.tamanho[1] / 72 * DPI_MOSAICO)
        cover = capas.gerar_mosaico_editorial(thumbnails, width, height, doc.p)
        try:
            photo_count = len({photo_id for page in plan.pages for photo_id in page.photo_ids})
            doc.capa(_codificar(cover.imagem, 88), photo_count, config.chamada, cover.ancora)
        finally:
            cover.imagem.close()
    finally:
        for thumbnail in thumbnails:
            thumbnail.close()
    return True


def _validate_export(path: str, expected_pages: int) -> None:
    """Reopen a finished sibling file before it is allowed to replace the destination."""
    with pymupdf.open(path) as pdf:
        if pdf.page_count != expected_pages:
            raise ValueError(f"PDF inválido: esperado {expected_pages} páginas, obtido {pdf.page_count}")
        for page in pdf:
            if page.rect.width <= page.rect.height:
                raise ValueError("PDF inválido: página editorial não está em A4 horizontal")
            if (
                abs(page.rect.width - tema.A4_PAISAGEM[0]) > 0.2
                or abs(page.rect.height - tema.A4_PAISAGEM[1]) > 0.2
            ):
                raise ValueError("PDF inválido: página fora do tamanho A4")


def _new_sibling_temp(destination: str) -> str:
    """Reserve a unique, owned temporary beside the final PDF."""
    absolute = os.path.abspath(destination)
    directory = os.path.dirname(absolute)
    os.makedirs(directory, exist_ok=True)
    descriptor, path = tempfile.mkstemp(
        dir=directory,
        prefix=f".{os.path.basename(destination)}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    return path


def _canonical_destination(destination: str) -> str:
    """Collapse relative, symlink and Windows case aliases to one lock key."""
    return os.path.normcase(os.path.realpath(os.path.abspath(destination)))


def _publication_lock(destination: str) -> _PublicationLock:
    key = _canonical_destination(destination)
    with _PUBLICATION_LOCKS_GUARD:
        holder = _PUBLICATION_LOCKS.get(key)
        if holder is None:
            holder = _PublicationLock()
            _PUBLICATION_LOCKS[key] = holder
        return holder


def exportar(
    config: Config,
    plan: BookPlan,
    progresso=None,
    cancelar: object | None = None,
) -> Resultado:
    """Atomically export the exact supplied plan after save and reopen validation."""
    if _cancelled(cancelar):
        raise Cancelado()
    config = config.com_padroes()
    assets, analysis = _prepare_render_assets(config, plan, progresso, cancelar)
    destination = config.saida
    temporary = _new_sibling_temp(destination)
    doc: documento.Documento | None = None
    cover_rendered = False
    try:
        doc = _new_editorial_document(config, plan.mode)
        cover_rendered = _render_cover(
            doc, config, plan, {photo.id: photo for photo in analysis.photos},
        )
        templates = {template.id: template for template in catalog()}
        total = len(plan.pages)
        for index, page_plan in enumerate(plan.pages, start=1):
            _avisar(progresso, index - 1, max(1, total), "Diagramando o PDF…", cancelar)
            try:
                template = templates[page_plan.template_id].resolve(plan.mode)
            except KeyError as exc:
                raise ValueError(f"Unknown template: {page_plan.template_id}") from exc
            doc.render_page(page_plan, template, assets)
            _avisar(progresso, index, max(1, total), f"Diagramando… página {index}/{total}", cancelar)
        doc.salvar(temporary)
        _validate_export(temporary, len(plan.pages) + int(cover_rendered))
        if _cancelled(cancelar):
            raise Cancelado()
        publication = _publication_lock(destination)
        with publication.lock:
            if _cancelled(cancelar):
                raise Cancelado()
            os.replace(temporary, destination)
    finally:
        if doc is not None:
            doc.fechar()
        if os.path.exists(temporary):
            os.unlink(temporary)
    if progresso:
        progresso(len(plan.pages), max(1, len(plan.pages)), "Pronto.")
    photo_count = len({photo_id for page in plan.pages for photo_id in page.photo_ids})
    return Resultado(
        destination, photo_count, len(plan.pages), list(analysis.failures),
    )


def gerar(config: Config, progresso=None, cancelar: threading.Event | None = None) -> Resultado:
    """Gera o PDF. `progresso(feito, total, mensagem)` é chamado ao longo do caminho."""
    config = config.com_padroes()
    cancelar = cancelar or threading.Event()

    def avisar(feito: int, total: int, mensagem: str) -> None:
        if cancelar.is_set():
            raise Cancelado()
        if progresso:
            progresso(feito, total, mensagem)

    avisar(0, 1, "Procurando fotos…")
    fotos = imagens.listar_fotos(config.pasta, config.recursivo)
    if config.limite:
        fotos = fotos[:config.limite]
    if not fotos:
        raise ValueError("Nenhuma foto encontrada nessa pasta.")

    dpi, qualidade_jpeg = QUALIDADES.get(config.qualidade, QUALIDADES["normal"])
    cores = tema.paleta(config.cor_fundo)

    caminho_logo = config.logo.strip()
    logo_base = imagens.carregar_logo(caminho_logo) if caminho_logo and os.path.exists(caminho_logo) else None
    usar_marca = config.marca_dagua and config.marca_opacidade > 0
    marca = (
        imagens.logo_branco(logo_base)
        if logo_base is not None and usar_marca
        else imagens.marca_textual(f"{config.estudio} · PROVA" if config.estudio.strip() else "PROVA PARA SELEÇÃO")
        if usar_marca
        else None
    )
    logo_png, logo_proporcao = None, 1200 / 630
    if logo_base is not None:
        # em fundo escuro o preto do logotipo vira branco; em fundo claro ele fica como é
        versao = logo_base if cores.claro else imagens.logo_bicolor(logo_base)
        buffer = io.BytesIO()
        versao.save(buffer, format="PNG")
        logo_png = buffer.getvalue()
        logo_proporcao = versao.width / versao.height

    # sem código sob a foto o cartão fecha simétrico, e a foto cresce
    altura_legenda = tema.ALTURA_LEGENDA if config.mostrar_codigos else tema.RESPIRO_CARTAO

    proporcao = _proporcao_tipica(fotos, config.girar_horizontais)
    area = documento.area_util(config.paisagem)
    grade = documento.melhor_grade(config.por_pagina, area[2], area[3], proporcao,
                                   altura_legenda)
    grade, area = documento.ajustar_ao_conteudo(grade, area, proporcao)
    lado_alvo = max(320, round(max(grade.largura_foto, grade.altura_foto) / 72 * dpi))

    total = len(fotos)
    falhas: list[tuple[str, str]] = []
    preparadas: list[_Preparada | None] = [None] * total
    feitas = 0
    trava = threading.Lock()

    def preparar(indice_foto):
        indice, foto = indice_foto
        if cancelar.is_set():
            raise Cancelado()
        try:
            imagem = imagens.abrir(foto)
            if config.girar_horizontais and imagem.width > imagem.height \
                    and grade.altura_foto > grade.largura_foto:
                imagem = imagem.transpose(Image.Transpose.ROTATE_270)
            miniatura = imagens.redimensionar(imagem, LADO_MINIATURA)
            pagina = imagens.redimensionar(imagem, lado_alvo)
            if marca is not None:
                pagina = imagens.aplicar_marca_dagua(pagina, marca, config.marca_largura,
                                                     config.marca_opacidade)
            preparadas[indice] = _Preparada(
                jpeg=_codificar(pagina, qualidade_jpeg),
                proporcao=pagina.width / pagina.height,
                rotulo=foto.rotulo,
                miniatura=miniatura,
            )
        except Cancelado:
            raise
        except Exception as erro:                       # uma foto ruim não derruba o lote
            falhas.append((os.path.basename(foto.caminho), str(erro)))
        finally:
            nonlocal feitas
            with trava:
                feitas += 1
                atual = feitas
            avisar(atual, total, f"Preparando fotos… {atual}/{total}")

    with ThreadPoolExecutor(max_workers=min(6, (os.cpu_count() or 4))) as executor:
        list(executor.map(preparar, enumerate(fotos)))

    prontas = [p for p in preparadas if p is not None]
    if not prontas:
        raise ValueError("Nenhuma foto pôde ser lida. Veja a lista de erros.")

    avisar(total, total, "Diagramando o PDF…")
    tipografia = documento.Tipografia()
    doc = documento.Documento(
        config.titulo, config.subtitulo, config.paisagem, tipografia, logo_png, logo_proporcao,
        rodape="ANOTE OS CÓDIGOS DAS FOTOS ESCOLHIDAS" if config.mostrar_codigos else "",
        nota_capa="CADA FOTO TRAZ SEU CÓDIGO LOGO ABAIXO" if config.mostrar_codigos else "",
        estudio=config.estudio, site=config.site, paleta=cores)

    if config.capa_mosaico:
        avisar(total, total, "Montando a capa…")
        largura_px = round(doc.tamanho[0] / 72 * DPI_MOSAICO)
        altura_px = round(doc.tamanho[1] / 72 * DPI_MOSAICO)
        capa = capas.gerar(config.estilo_capa, [p.miniatura for p in prontas],
                           largura_px, altura_px, cores)
        doc.capa(_codificar(capa.imagem, 88), len(prontas), config.chamada, capa.ancora)

    por_pagina = config.por_pagina
    paginas = -(-len(prontas) // por_pagina)
    for numero in range(paginas):
        if cancelar.is_set():
            raise Cancelado()
        lote = prontas[numero * por_pagina:(numero + 1) * por_pagina]
        pagina = doc.nova_pagina()
        doc.moldura(pagina, numero + 1, paginas)
        for indice, preparada in enumerate(lote):
            doc.cartao(pagina, documento.celula(grade, indice, area, len(lote)),
                       preparada.jpeg, preparada.proporcao,
                       preparada.rotulo if config.mostrar_codigos else "", altura_legenda)
        avisar(total, total, f"Diagramando… página {numero + 1}/{paginas}")

    os.makedirs(os.path.dirname(config.saida) or ".", exist_ok=True)
    doc.salvar(config.saida)
    avisar(total, total, "Pronto.")
    return Resultado(config.saida, len(prontas), paginas, falhas)
