"""Pipeline: lê a pasta da sessão e escreve o PDF de provas."""
from __future__ import annotations

import io
import os
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date

from PIL import Image

from . import capas, documento, imagens, tema

QUALIDADES = {
    "leve":   (150, 78),
    "normal": (200, 85),
    "alta":   (300, 91),
}

LADO_MINIATURA = 320          # miniaturas usadas no mosaico da capa
DPI_MOSAICO = 150


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
    marca = imagens.logo_branco(logo_base) if (logo_base and usar_marca) else None
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
