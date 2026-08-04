"""Diagramação e escrita do PDF de provas."""
from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from . import tema

NOME_SERIF = "fanSerif"
NOME_SERIF_ITALICO = "fanSerifIt"
NOME_SANS = "fanSans"
NOME_SANS_MEDIO = "fanSansM"

_PAPEIS = {
    NOME_SERIF: tema.SERIF,
    NOME_SERIF_ITALICO: tema.SERIF_ITALICO,
    NOME_SANS: tema.SANS,
    NOME_SANS_MEDIO: tema.SANS_MEDIO,
}


class Tipografia:
    """Fontes do documento, com medição e entreletra manual.

    Cada papel usa um arquivo do sistema quando existe; não existindo (ou não
    sendo legível), cai para a fonte base 14 correspondente, que já vem em
    qualquer leitor de PDF. Assim o app funciona em qualquer sistema.
    """

    def __init__(self) -> None:
        self._fontes: dict[str, pymupdf.Font] = {}
        self._arquivos: dict[str, str | None] = {}
        self._nomes: dict[str, str] = {}
        for papel, fonte in _PAPEIS.items():
            objeto = None
            if fonte.arquivo:
                try:
                    objeto = pymupdf.Font(fontfile=fonte.arquivo)
                except Exception:            # arquivo corrompido ou formato exótico
                    objeto = None
            if objeto is not None:
                self._fontes[papel] = objeto
                self._arquivos[papel] = fonte.arquivo
                self._nomes[papel] = papel
            else:
                self._fontes[papel] = pymupdf.Font(fonte.embutida)
                self._arquivos[papel] = None
                self._nomes[papel] = fonte.embutida

    @property
    def usando_fontes_do_sistema(self) -> bool:
        return any(self._arquivos.values())

    def registrar(self, pagina: pymupdf.Page) -> None:
        for papel, arquivo in self._arquivos.items():
            if arquivo:
                pagina.insert_font(fontname=papel, fontfile=arquivo)

    def largura(self, texto_: str, fonte: str, tamanho: float, entreletra: float = 0.0) -> float:
        base = self._fontes[fonte].text_length(texto_, tamanho)
        return base + entreletra * max(0, len(texto_) - 1)

    def encaixar(self, texto_: str, fonte: str, tamanho: float, limite: float,
                 entreletra: float = 0.0) -> str:
        """Corta o texto com reticências para caber em `limite` pontos."""
        if self.largura(texto_, fonte, tamanho, entreletra) <= limite:
            return texto_
        while texto_ and self.largura(texto_ + "…", fonte, tamanho, entreletra) > limite:
            texto_ = texto_[:-1]
        return texto_ + "…"

    def escrever(self, pagina: pymupdf.Page, x: float, y: float, texto_: str, fonte: str,
                 tamanho: float, cor, entreletra: float = 0.0, alinhamento: str = "esq") -> None:
        if not texto_:
            return
        largura = self.largura(texto_, fonte, tamanho, entreletra)
        if alinhamento == "centro":
            x -= largura / 2
        elif alinhamento == "dir":
            x -= largura
        nome = self._nomes[fonte]
        if entreletra == 0:
            pagina.insert_text((x, y), texto_, fontname=nome, fontsize=tamanho, color=cor)
            return
        fonte_obj = self._fontes[fonte]
        for caractere in texto_:
            pagina.insert_text((x, y), caractere, fontname=nome, fontsize=tamanho, color=cor)
            x += fonte_obj.text_length(caractere, tamanho) + entreletra


# --- grade ----------------------------------------------------------------

@dataclass(frozen=True)
class Grade:
    colunas: int
    linhas: int
    largura_celula: float
    altura_celula: float
    altura_legenda: float = tema.ALTURA_LEGENDA   # faixa do código sob a foto

    @property
    def largura_foto(self) -> float:
        return self.largura_celula - 2 * tema.RESPIRO_CARTAO

    @property
    def altura_foto(self) -> float:
        return self.altura_celula - tema.RESPIRO_CARTAO - self.altura_legenda


def melhor_grade(por_pagina: int, largura: float, altura: float, proporcao: float,
                 altura_legenda: float = tema.ALTURA_LEGENDA) -> Grade:
    """Escolhe colunas x linhas que deixam cada foto o maior possível.

    `proporcao` é a razão largura/altura típica das fotos da sessão.
    """
    melhor: tuple[float, Grade] | None = None
    for colunas in range(1, por_pagina + 1):
        linhas = -(-por_pagina // colunas)
        if colunas * linhas - por_pagina >= colunas:   # sobraria uma linha vazia
            continue
        largura_celula = (largura - tema.VAO_X * (colunas - 1)) / colunas
        altura_celula = (altura - tema.VAO_Y * (linhas - 1)) / linhas
        grade = Grade(colunas, linhas, largura_celula, altura_celula, altura_legenda)
        if grade.largura_foto <= 8 or grade.altura_foto <= 8:
            continue
        escala = min(grade.largura_foto / proporcao, grade.altura_foto)
        area = escala * escala * proporcao
        if melhor is None or area > melhor[0]:
            melhor = (area, grade)
    if melhor is None:                                  # fallback defensivo
        return Grade(1, 1, largura, altura, altura_legenda)
    return melhor[1]


def ajustar_ao_conteudo(grade: Grade, area: tuple[float, float, float, float],
                        proporcao: float) -> tuple[Grade, tuple[float, float, float, float]]:
    """Encolhe as linhas à altura real das fotos e centraliza o bloco na página.

    Sem isso, uma grade com folga vertical (6 retratos em A4, por exemplo)
    espalharia as fotos com vãos enormes entre as linhas.
    """
    altura_foto = min(grade.largura_foto / proporcao, grade.altura_foto)
    altura_celula = altura_foto + tema.RESPIRO_CARTAO + grade.altura_legenda
    encolhida = Grade(grade.colunas, grade.linhas, grade.largura_celula, altura_celula,
                      grade.altura_legenda)
    bloco = grade.linhas * altura_celula + (grade.linhas - 1) * tema.VAO_Y
    x, y, largura, altura = area
    return encolhida, (x, y + max(0.0, (altura - bloco) / 2), largura, altura)


def area_util(paisagem: bool) -> tuple[float, float, float, float]:
    """(x, y, largura, altura) da região onde a grade é desenhada."""
    largura_pagina, altura_pagina = tema.A4_PAISAGEM if paisagem else tema.A4
    x = tema.MARGEM_LATERAL
    y = tema.Y_CONTEUDO
    return (x, y,
            largura_pagina - 2 * tema.MARGEM_LATERAL,
            altura_pagina - tema.Y_CONTEUDO - tema.ALTURA_RODAPE - 14)


def celula(grade: Grade, indice: int, area: tuple[float, float, float, float],
           total_na_pagina: int) -> pymupdf.Rect:
    """Retângulo do cartão nº `indice` da página, com a última linha centralizada."""
    x0, y0, _, _ = area
    coluna, linha = indice % grade.colunas, indice // grade.colunas
    na_linha = min(grade.colunas, total_na_pagina - linha * grade.colunas)
    sobra = (grade.colunas - na_linha) * (grade.largura_celula + tema.VAO_X) / 2
    x = x0 + sobra + coluna * (grade.largura_celula + tema.VAO_X)
    y = y0 + linha * (grade.altura_celula + tema.VAO_Y)
    return pymupdf.Rect(x, y, x + grade.largura_celula, y + grade.altura_celula)


# --- desenho --------------------------------------------------------------

class Documento:
    def __init__(self, titulo: str, subtitulo: str, paisagem: bool, tipografia: Tipografia,
                 logo: bytes | None, logo_proporcao: float = 1200 / 630,
                 rodape: str = "", nota_capa: str = "", estudio: str = "",
                 site: str = "", paleta: tema.Paleta | None = None) -> None:
        self.pdf = pymupdf.open()
        self.rodape = rodape
        self.nota_capa = nota_capa
        self.estudio = estudio
        self.site = site
        self.p = paleta or tema.paleta()
        self.titulo = titulo
        self.subtitulo = subtitulo
        self.paisagem = paisagem
        self.tipo = tipografia
        self.logo = logo
        self.logo_proporcao = logo_proporcao
        self.tamanho = tema.A4_PAISAGEM if paisagem else tema.A4

    def nova_pagina(self) -> pymupdf.Page:
        pagina = self.pdf.new_page(width=self.tamanho[0], height=self.tamanho[1])
        pagina.draw_rect(pymupdf.Rect(0, 0, *self.tamanho), color=None, fill=self.p.fundo)
        self.tipo.registrar(pagina)
        return pagina

    # cabeçalho e rodapé -------------------------------------------------
    def moldura(self, pagina: pymupdf.Page, numero: int, total: int) -> None:
        largura, altura = self.tamanho
        direita = largura - tema.MARGEM_LATERAL

        if self.logo:
            altura_logo = tema.ALTURA_CABECALHO
            retangulo = pymupdf.Rect(tema.MARGEM_LATERAL, tema.TOPO_CABECALHO,
                                     tema.MARGEM_LATERAL + altura_logo * self.logo_proporcao,
                                     tema.TOPO_CABECALHO + altura_logo)
            pagina.insert_image(retangulo, stream=self.logo, keep_proportion=True)
        elif self.estudio:
            self.tipo.escrever(pagina, tema.MARGEM_LATERAL, tema.TOPO_CABECALHO + 10,
                               self.estudio.upper(), NOME_SANS_MEDIO, 8, self.p.texto, 1.6)

        rotulo = self.tipo.encaixar(self.titulo, NOME_SERIF_ITALICO, 9.5, largura * 0.55)
        self.tipo.escrever(pagina, direita, tema.TOPO_CABECALHO + 12, rotulo,
                           NOME_SERIF_ITALICO, 9.5, self.p.apagado, alinhamento="dir")

        y = tema.Y_FILETE_TOPO
        pagina.draw_line((tema.MARGEM_LATERAL, y), (direita, y), color=self.p.filete, width=0.6)
        pagina.draw_line((tema.MARGEM_LATERAL, y), (tema.MARGEM_LATERAL + 30, y),
                         color=self.p.acento, width=1.2)

        y_rodape = altura - tema.ALTURA_RODAPE
        pagina.draw_line((tema.MARGEM_LATERAL, y_rodape), (direita, y_rodape),
                         color=self.p.filete, width=0.6)
        # o site vai à esquerda quando não há recado; havendo os dois, ele centraliza
        if self.rodape:
            self.tipo.escrever(pagina, tema.MARGEM_LATERAL, y_rodape + 15, self.rodape,
                               NOME_SANS, 6.2, self.p.apagado, 1.4)
            if self.site:
                self.tipo.escrever(pagina, largura / 2, y_rodape + 15, self.site,
                                   NOME_SANS_MEDIO, 6.4, self.p.acento, 1.2, "centro")
        elif self.site:
            self.tipo.escrever(pagina, tema.MARGEM_LATERAL, y_rodape + 15, self.site,
                               NOME_SANS_MEDIO, 6.4, self.p.acento, 1.2)
        self.tipo.escrever(pagina, direita, y_rodape + 15, f"{numero:02d} / {total:02d}",
                           NOME_SERIF, 8.5, self.p.apagado, alinhamento="dir")

    # cartão de uma foto --------------------------------------------------
    def cartao(self, pagina: pymupdf.Page, retangulo: pymupdf.Rect, jpeg: bytes,
               proporcao: float, rotulo: str, altura_legenda: float) -> None:
        """Desenha uma foto (e, se houver, seu código) na célula da grade.

        O cartão é ajustado ao formato real da foto (em vez de ocupar a célula
        inteira), de modo que retratos e paisagens fiquem igualmente enquadrados.
        """
        caixa = pymupdf.Rect(retangulo.x0 + tema.RESPIRO_CARTAO,
                             retangulo.y0 + tema.RESPIRO_CARTAO,
                             retangulo.x1 - tema.RESPIRO_CARTAO,
                             retangulo.y1 - altura_legenda)
        escala = min(caixa.width / proporcao, caixa.height)
        largura, altura = escala * proporcao, escala
        centro_x = (caixa.x0 + caixa.x1) / 2
        topo = caixa.y0 + (caixa.height - altura) / 2
        foto = pymupdf.Rect(centro_x - largura / 2, topo, centro_x + largura / 2, topo + altura)

        cartao = pymupdf.Rect(foto.x0 - tema.RESPIRO_CARTAO, foto.y0 - tema.RESPIRO_CARTAO,
                              foto.x1 + tema.RESPIRO_CARTAO, foto.y1 + altura_legenda)
        pagina.draw_rect(cartao, color=None, fill=self.p.painel)
        pagina.insert_image(foto, stream=jpeg, keep_proportion=True)
        pagina.draw_rect(foto, color=self.p.moldura, width=0.5)

        if not rotulo:
            return
        tamanho = 7.2 if largura > 150 else 6.2
        nome = self.tipo.encaixar(rotulo, NOME_SANS_MEDIO, tamanho, cartao.width - 10, 1.1)
        self.tipo.escrever(pagina, centro_x, cartao.y1 - 6.5, nome,
                           NOME_SANS_MEDIO, tamanho, self.p.apagado, 1.1, "centro")

    # capa -----------------------------------------------------------------
    def capa(self, capa_jpeg: bytes, quantidade: int, chamada: str,
             ancora: float = 0.34) -> None:
        largura, altura = self.tamanho
        pagina = self.pdf.new_page(width=largura, height=altura)
        self.tipo.registrar(pagina)
        pagina.insert_image(pymupdf.Rect(0, 0, largura, altura), stream=capa_jpeg,
                            keep_proportion=False)

        centro = largura / 2
        base = altura * ancora
        # âncora baixa: a chamada acompanha o bloco em vez de ir para o pé da página
        compacto = ancora > 0.5

        self.tipo.escrever(pagina, centro, base, "PROVAS DO ENSAIO", NOME_SANS_MEDIO, 8,
                           self.p.acento, 3.4, "centro")

        if self.logo:
            largura_logo = min(150.0 if compacto else 180.0,
                               largura * (0.34 if compacto else 0.40))
            altura_logo = largura_logo / self.logo_proporcao
            pagina.insert_image(
                pymupdf.Rect(centro - largura_logo / 2, base + 18,
                             centro + largura_logo / 2, base + 18 + altura_logo),
                stream=self.logo, keep_proportion=True)
            base += 18 + altura_logo

        base += 44 if compacto else 52
        tamanho_titulo = 22 if compacto else 25
        titulo = self.tipo.encaixar(self.titulo, NOME_SERIF, tamanho_titulo, largura - 90)
        self.tipo.escrever(pagina, centro, base, titulo, NOME_SERIF, tamanho_titulo,
                           self.p.texto, 0.4, "centro")

        pagina.draw_line((centro - 18, base + 18), (centro + 18, base + 18),
                         color=self.p.acento, width=1.1)

        meta = " · ".join(p for p in (self.subtitulo, f"{quantidade} FOTOS") if p)
        self.tipo.escrever(pagina, centro, base + 38, meta.upper(), NOME_SANS, 7.5,
                           self.p.apagado, 2.2, "centro")

        y_chamada = base + 64 if compacto else altura - 74
        self.tipo.escrever(pagina, centro, y_chamada, chamada, NOME_SERIF_ITALICO, 10.5,
                           self.p.texto, 0, "centro")
        self.tipo.escrever(pagina, centro, y_chamada + 18, self.nota_capa, NOME_SANS, 6.6,
                           self.p.apagado, 2.0, "centro")
        self.tipo.escrever(pagina, centro, altura - 32, self.site, NOME_SANS_MEDIO, 6.6,
                           self.p.acento, 1.6, "centro")

    def salvar(self, caminho: str) -> None:
        self.pdf.set_metadata({
            "title": f"{self.titulo} — provas",
            "author": self.estudio or "",
            "subject": "Seleção de fotos do ensaio",
            "creator": "Provas",
        })
        self.pdf.save(caminho, deflate=True, garbage=3)
        self.pdf.close()
