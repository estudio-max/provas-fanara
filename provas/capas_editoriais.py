"""Capas editoriais: cada estilo desenha a própria tipografia.

Os estilos antigos entregam a imagem e uma âncora, e quem chama desenha o texto
centralizado ali. Isso serve para composições simétricas, mas não para uma capa
com o texto numa coluna lateral ou girado na vertical. Estes estilos assumem o
texto — `Capa.identity_embedded` diz a quem chama que não há mais nada a fazer.

As medidas do guia estão em pontos sobre A4 paisagem (842 × 595). Aqui elas são
relativas à altura da tela, para a capa sair igual em qualquer resolução.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from . import cor_capa, tema
from .tipografia_capas import ParTipografico, par

#: Altura de referência do guia, em pontos: A4 paisagem.
_ALTURA_GUIA = 595.0


def _pt(pontos: float, altura: int) -> int:
    """Converte um corpo do guia para pixels nesta tela."""
    return max(1, round(pontos * altura / _ALTURA_GUIA))


def _fonte(origem: tema.Fonte, corpo: int) -> ImageFont.ImageFont:
    if origem.arquivo:
        try:
            return ImageFont.truetype(origem.arquivo, corpo)
        except OSError:
            pass
    return ImageFont.load_default(size=corpo)


def _escrever(
    desenho: ImageDraw.ImageDraw,
    texto: str,
    fonte: ImageFont.ImageFont,
    posicao: tuple[int, int],
    cor: tuple[int, int, int],
    entreletra: float = 0.0,
) -> int:
    """Escreve uma linha com entreletra manual e devolve a largura usada."""
    if not texto:
        return 0
    x, y = posicao
    if entreletra <= 0:
        desenho.text((x, y), texto, font=fonte, fill=cor)
        return round(desenho.textlength(texto, font=fonte))
    passo = fonte.size * entreletra
    for letra in texto:
        desenho.text((x, y), letra, font=fonte, fill=cor)
        x += desenho.textlength(letra, font=fonte) + passo
    return round(x - posicao[0])


def _quebrar(
    desenho: ImageDraw.ImageDraw,
    texto: str,
    fonte: ImageFont.ImageFont,
    limite: int,
    entreletra: float = 0.0,
) -> list[str]:
    """Quebra o texto em linhas que cabem em `limite` pixels."""
    palavras = texto.split()
    if not palavras:
        return []

    def largura(frase: str) -> float:
        base = desenho.textlength(frase, font=fonte)
        return base + fonte.size * entreletra * max(0, len(frase) - 1)

    linhas: list[str] = []
    atual = palavras[0]
    for palavra in palavras[1:]:
        tentativa = f"{atual} {palavra}"
        if largura(tentativa) <= limite:
            atual = tentativa
        else:
            linhas.append(atual)
            atual = palavra
    linhas.append(atual)

    # Um endereço de site é uma palavra só e pode ser mais largo que a coluna.
    # Sem partir, ele saía pela borda da capa — o que é pior que partir feio.
    inteiras: list[str] = []
    for linha in linhas:
        while largura(linha) > limite and len(linha) > 1:
            corte = len(linha) - 1
            while corte > 1 and largura(linha[:corte]) > limite:
                corte -= 1
            inteiras.append(linha[:corte])
            linha = linha[corte:]
        inteiras.append(linha)
    return inteiras


def _fonte_de_apoio(
    desenho: ImageDraw.ImageDraw,
    texto: str,
    origem: tema.Fonte,
    corpo: int,
    limite: int,
    minimo: int = 8,
) -> ImageFont.ImageFont:
    """Corpo da linha de apoio que faz a maior parte caber inteira na coluna.

    Um nome de estúdio ou um endereço de site é indivisível na leitura. Numa
    coluna estreita ele quebrava no meio; ceder um ponto ou dois de corpo lê
    melhor do que partir o nome de quem assina o trabalho.
    """
    fonte = _fonte(origem, corpo)
    partes = [parte.strip() for parte in (texto or "").split("·") if parte.strip()]
    if not partes:
        return fonte
    maior = max(partes, key=lambda parte: desenho.textlength(parte, font=fonte))
    while corpo > minimo and desenho.textlength(maior, font=fonte) > limite:
        corpo -= 1
        fonte = _fonte(origem, corpo)
    return fonte


def _linhas_de_apoio(
    desenho: ImageDraw.ImageDraw,
    texto: str,
    fonte: ImageFont.ImageFont,
    limite: int,
    entreletra: float = 0.0,
) -> list[str]:
    """Quebra a linha de apoio entre as suas partes, nunca no meio de uma.

    Data, fotógrafo e site são três coisas, não um parágrafo. Quebrando a string
    inteira como texto corrido, o separador sobrava pendurado no fim da linha e
    o nome do estúdio partia ao meio — foi assim que o crédito saiu na primeira
    versão. Só uma parte que sozinha não cabe na coluna volta a ceder por palavra.
    """
    partes = [parte.strip() for parte in (texto or "").split("·") if parte.strip()]
    if not partes:
        return []

    def largura(frase: str) -> float:
        base = desenho.textlength(frase, font=fonte)
        return base + fonte.size * entreletra * max(0, len(frase) - 1)

    linhas: list[str] = []
    atual = ""
    for parte in partes:
        if atual and largura(f"{atual} · {parte}") <= limite:
            atual = f"{atual} · {parte}"
            continue
        if atual:
            linhas.append(atual)
            atual = ""
        if largura(parte) > limite:
            pedacos = _quebrar(desenho, parte, fonte, limite, entreletra)
            linhas.extend(pedacos[:-1])
            atual = pedacos[-1] if pedacos else ""
        else:
            atual = parte
    if atual:
        linhas.append(atual)
    return linhas


def _apoio(subtitulo: str, credito: str) -> str:
    """Junta subtítulo e crédito numa linha só de apoio.

    O fotógrafo e o site precisam aparecer em toda capa — é a assinatura do
    trabalho. As capas editoriais desenham a própria tipografia, então não
    recebem o bloco de identidade que o motor põe nas outras: o crédito entra
    aqui, na linha que cada estilo já sabe posicionar e colorir. Campo vazio
    simplesmente não aparece, e sem nenhum deles não sobra linha alguma.
    """
    partes = [parte for parte in ((subtitulo or "").strip(), (credito or "").strip()) if parte]
    return " · ".join(partes)


def _entrelinha(fonte: ImageFont.ImageFont, fator: float) -> int:
    """Avanço de linha: o fator do estilo, mas nunca menos do que a fonte pede.

    Bodoni e Playfair têm ascendente e descendente maiores que o corpo. Um fator
    afinado com uma substituta mais estreita fazia a linha seguinte pousar em
    cima da anterior — e o subtítulo, sobre a última linha do título.
    """
    ascendente, descendente = fonte.getmetrics()
    return max(round(fonte.size * fator), ascendente + descendente)


def _tira_girada(
    texto: str,
    origem: tema.Fonte,
    corpo: int,
    limite: int,
    cor: tuple[int, int, int],
    entreletra: float,
    graus: int,
) -> Image.Image:
    """Título na vertical, com o corpo cedendo até caber na altura disponível.

    Com corpo fixo, uma fonte mais larga que a substituta passava do rodapé e o
    fim do título sumia fora da capa.
    """
    regua = ImageDraw.Draw(Image.new("L", (1, 1)))
    corpo = max(1, corpo)
    while True:
        fonte = _fonte(origem, corpo)
        comprimento = round(regua.textlength(texto, font=fonte)
                            + corpo * entreletra * max(0, len(texto) - 1))
        if comprimento <= limite or corpo <= 8:
            break
        corpo = round(corpo * 0.94)
    tira = Image.new("RGBA", (max(1, comprimento + corpo), _entrelinha(fonte, 1.5)),
                     (0, 0, 0, 0))
    _escrever(ImageDraw.Draw(tira), texto, fonte, (0, 0), cor, entreletra)
    return tira.rotate(graus, expand=True)


def _encaixar(
    desenho: ImageDraw.ImageDraw,
    texto: str,
    origem: tema.Fonte,
    corpo_inicial: int,
    limite: int,
    entreletra: float,
    minimo: float = 0.55,
) -> tuple[ImageFont.ImageFont, list[str]]:
    """Reduz o corpo até o texto caber em no máximo duas linhas."""
    corpo = corpo_inicial
    while corpo > corpo_inicial * minimo:
        fonte = _fonte(origem, corpo)
        linhas = _quebrar(desenho, texto, fonte, limite, entreletra)
        if len(linhas) <= 2:
            return fonte, linhas
        corpo = round(corpo * 0.92)
    fonte = _fonte(origem, corpo)
    return fonte, _quebrar(desenho, texto, fonte, limite, entreletra)


def _preencher(foto: Image.Image, largura: int, altura: int) -> Image.Image:
    """Recorta a foto para cobrir a área, sem distorcer."""
    if largura <= 0 or altura <= 0:
        raise ValueError("A área da fotografia precisa ter medidas positivas.")
    origem = foto.convert("RGB")
    escala = max(largura / origem.width, altura / origem.height)
    redimensionada = origem.resize(
        (max(1, round(origem.width * escala)), max(1, round(origem.height * escala))),
        Image.LANCZOS,
    )
    esquerda = (redimensionada.width - largura) // 2
    topo = (redimensionada.height - altura) // 2
    return redimensionada.crop((esquerda, topo, esquerda + largura, topo + altura))


@dataclass(frozen=True)
class Composta:
    """Resultado de um estilo editorial: a arte pronta, texto incluído."""

    imagem: Image.Image
    fotos_usadas: tuple[str, ...] = ()


def jornada(
    foto: Image.Image,
    largura: int,
    altura: int,
    titulo: str,
    subtitulo: str = "",
    credito: str = "",
    tipografia: ParTipografico | None = None,
) -> Composta:
    """Minimalismo e espaço: foto à direita em 2/3, texto na coluna esquerda.

    O fundo é claro por escolha do guia — o contraste vem do branco contra a
    fotografia, não de cor. Por isso este estilo não usa a cor extraída.
    """
    if largura <= 0 or altura <= 0:
        raise ValueError("A capa precisa ter medidas positivas.")
    tipografia = tipografia or par("geometrico")
    subtitulo = _apoio(subtitulo, credito)

    fundo = (250, 249, 247)
    tinta = (26, 27, 31)
    tela = Image.new("RGB", (largura, altura), fundo)

    margem = round(altura * 0.085)
    largura_foto = round(largura * 0.58)
    x_foto = largura - largura_foto - margem
    altura_foto = altura - 2 * margem
    tela.paste(_preencher(foto, largura_foto, altura_foto), (x_foto, margem))

    desenho = ImageDraw.Draw(tela)
    coluna = x_foto - 2 * margem
    titulo = (titulo or "").strip()
    if tipografia.titulo_caixa_alta:
        titulo = titulo.upper()

    fonte_titulo, linhas = _encaixar(
        desenho, titulo, tipografia.titulo, _pt(40, altura), coluna,
        tipografia.titulo_entreletra,
    )
    entrelinha = _entrelinha(fonte_titulo, 1.16)
    # O bloco fica na metade inferior da coluna, como no guia: o alto respira.
    y = round(altura * 0.52) - (len(linhas) - 1) * entrelinha
    for linha in linhas:
        _escrever(desenho, linha, fonte_titulo, (margem, y), tinta,
                  tipografia.titulo_entreletra)
        y += entrelinha

    subtitulo = (subtitulo or "").strip()
    if subtitulo:
        fonte_sub = _fonte_de_apoio(desenho, subtitulo, tipografia.subtitulo,
                                    _pt(15, altura), coluna)
        y += round(fonte_titulo.size * 0.55)
        for linha in _linhas_de_apoio(desenho, subtitulo, fonte_sub, coluna):
            _escrever(desenho, linha, fonte_sub, (margem, y), (92, 94, 102))
            y += _entrelinha(fonte_sub, 1.35)

    return Composta(tela)


def _luminancia_media(recorte: Image.Image) -> float:
    """Luminância de uma área da foto, para decidir a cor do texto por cima."""
    pequena = recorte.convert("L").resize((16, 16), Image.LANCZOS)
    dados = list(pequena.get_flattened_data())
    return sum(dados) / len(dados) / 255


def _veu(tela: Image.Image, caixa: tuple[int, int, int, int], forca: float,
         clara: bool, direcao: str = "chapado") -> None:
    """Escurece uma faixa da foto para o texto pousar.

    Chapado deixa uma borda dura visível sobre a fotografia, que denuncia o
    truque. Com `direcao`, o véu desvanece para o lado indicado e a emenda some.
    """
    esquerda, topo, direita, base = caixa
    largura, altura = direita - esquerda, base - topo
    if largura <= 0 or altura <= 0:
        return
    cor = (255, 255, 255) if clara else (0, 0, 0)
    faixa = Image.new("RGB", (largura, altura), cor)
    topo_alfa = round(255 * forca)
    if direcao == "chapado":
        mascara = Image.new("L", (largura, altura), topo_alfa)
    else:
        vertical = direcao in ("cima", "baixo")
        comprimento = altura if vertical else largura
        rampa = Image.new("L", (1, comprimento) if vertical else (comprimento, 1))
        pixels = rampa.load()
        for posicao in range(comprimento):
            fracao = posicao / max(1, comprimento - 1)
            if direcao in ("baixo", "direita"):
                fracao = 1 - fracao
            valor = round(topo_alfa * fracao ** 1.4)
            if vertical:
                pixels[0, posicao] = valor
            else:
                pixels[posicao, 0] = valor
        mascara = rampa.resize((largura, altura), Image.BILINEAR)
    tela.paste(faixa, (esquerda, topo), mascara)


def toscana(foto, largura, altura, titulo, subtitulo="", credito="", tipografia=None) -> Composta:
    """Passpartout: foto centralizada com margens amplas sobre creme, texto abaixo."""
    tipografia = tipografia or par("editorial")
    subtitulo = _apoio(subtitulo, credito)
    fundo = cor_capa.fundo_claro_da_capa(foto)
    tinta = (38, 36, 33)
    tela = Image.new("RGB", (largura, altura), fundo)

    margem_x = round(largura * 0.13)
    margem_topo = round(altura * 0.10)
    area_texto = round(altura * 0.22)
    caixa = (largura - 2 * margem_x, altura - margem_topo - area_texto)
    tela.paste(_preencher(foto, *caixa), (margem_x, margem_topo))
    # Fio fino em volta: o passpartout precisa de borda para ler como moldura.
    ImageDraw.Draw(tela).rectangle(
        (margem_x, margem_topo, margem_x + caixa[0] - 1, margem_topo + caixa[1] - 1),
        outline=(206, 200, 191),
    )

    desenho = ImageDraw.Draw(tela)
    texto = (titulo or "").strip()
    if tipografia.titulo_caixa_alta:
        texto = texto.upper()
    fonte, linhas = _encaixar(desenho, texto, tipografia.titulo, _pt(41, altura),
                              round(largura * 0.7), tipografia.titulo_entreletra)
    y = margem_topo + caixa[1] + round(altura * 0.055)
    for linha in linhas:
        comprimento = desenho.textlength(linha, font=fonte)
        _escrever(desenho, linha, fonte, (round((largura - comprimento) / 2), y), tinta,
                  tipografia.titulo_entreletra)
        y += _entrelinha(fonte, 1.14)

    if (subtitulo or "").strip():
        fonte_sub = _fonte(tipografia.subtitulo, _pt(15, altura))
        y += round(fonte.size * 0.28)
        for linha in _linhas_de_apoio(desenho, subtitulo, fonte_sub, round(largura * 0.66)):
            comprimento = desenho.textlength(linha, font=fonte_sub)
            _escrever(desenho, linha, fonte_sub,
                      (round((largura - comprimento) / 2), y), (104, 100, 94))
            y += _entrelinha(fonte_sub, 1.3)
    return Composta(tela)


def neon(foto, largura, altura, titulo, subtitulo="", credito="", tipografia=None) -> Composta:
    """Sangria total, título condensado na vertical à direita e bloco na base."""
    tipografia = tipografia or par("condensado")
    subtitulo = _apoio(subtitulo, credito)
    tela = _preencher(foto, largura, altura)
    desenho = ImageDraw.Draw(tela)
    claro = (250, 250, 252)

    faixa = round(largura * 0.13)
    _veu(tela, (largura - faixa, 0, largura, altura), 0.78, clara=False)
    base = round(altura * 0.26)
    _veu(tela, (0, altura - base, largura - faixa, altura), 0.74,
         clara=False, direcao="cima")

    texto = (titulo or "").strip().upper()
    palavras = texto.split(" ")
    # Um artigo sozinho na tira vertical vira um borrão de uma letra: junta
    # palavras até a tira carregar algo que se leia como palavra.
    corte = 1
    while corte < len(palavras) and len(" ".join(palavras[:corte])) < 4:
        corte += 1
    vertical, horizontal = " ".join(palavras[:corte]), " ".join(palavras[corte:])

    # O título vertical é desenhado numa tira própria e girado: o Pillow não
    # escreve em ângulo, e girar a tela inteira estragaria a fotografia.
    margem_tira = round(altura * 0.06)
    girada = _tira_girada(vertical, tipografia.titulo, _pt(56, altura),
                          altura - 2 * margem_tira, claro,
                          tipografia.titulo_entreletra, 90)
    tela.paste(girada, (largura - faixa + round(faixa * 0.12), margem_tira), girada)

    corpo = _pt(56, altura)
    fonte = _fonte(tipografia.titulo, corpo)
    y = altura - round(base * 0.78)
    if horizontal:
        fonte, linhas = _encaixar(desenho, horizontal, tipografia.titulo, corpo,
                                  largura - faixa - round(largura * 0.09),
                                  tipografia.titulo_entreletra)
        for linha in linhas:
            _escrever(desenho, linha, fonte, (round(largura * 0.045), y), claro,
                      tipografia.titulo_entreletra)
            y += _entrelinha(fonte, 1.05)
    if (subtitulo or "").strip():
        fonte_sub = _fonte(tipografia.subtitulo, _pt(14, altura))
        _escrever(desenho, subtitulo.strip(), fonte_sub,
                  (round(largura * 0.045), y), claro)
    return Composta(tela)


def fluir(foto, largura, altura, titulo, subtitulo="", credito="", tipografia=None) -> Composta:
    """Sangria total com tipografia clara no quadrante mais calmo da imagem."""
    tipografia = tipografia or par("alto_contraste")
    subtitulo = _apoio(subtitulo, credito)
    tela = _preencher(foto, largura, altura)
    desenho = ImageDraw.Draw(tela)

    # Escolhe o quadrante superior de menor variação para o texto pousar.
    metade = largura // 2
    quadrantes = {
        "esquerda": (0, 0, metade, altura // 2),
        "direita": (metade, 0, largura, altura // 2),
    }
    escolhido = min(quadrantes,
                    key=lambda nome: _luminancia_media(tela.crop(quadrantes[nome])))
    caixa = quadrantes[escolhido]
    x = round(largura * 0.06) if escolhido == "esquerda" else metade + round(largura * 0.04)
    limite = metade - round(largura * 0.10)
    texto = (titulo or "").strip()
    if tipografia.titulo_caixa_alta:
        texto = texto.upper()
    fonte, linhas = _encaixar(desenho, texto, tipografia.titulo, _pt(48, altura),
                              limite, tipografia.titulo_entreletra)
    topo = round(altura * 0.16)
    fonte_sub = _fonte(tipografia.subtitulo, _pt(14, altura))
    linhas_sub = _linhas_de_apoio(desenho, subtitulo, fonte_sub, limite) if subtitulo else []

    # O véu é medido pelo texto, não chutado: o bloco cresce com o crédito, e o
    # quadrante calmo foi escolhido olhando só a metade de cima. Chapado onde as
    # letras pousam e desvanecendo logo abaixo — assim não há borda visível, e
    # sobre uma camisa branca o cinza claro continua legível.
    base_do_bloco = (topo + sum(_entrelinha(fonte, 1.1) for _ in linhas)
                     + (round(fonte.size * 0.34) if linhas_sub else 0)
                     + sum(_entrelinha(fonte_sub, 1.38) for _ in linhas_sub))
    base_do_bloco = min(altura, base_do_bloco + round(altura * 0.03))
    _veu(tela, (0, 0, largura, base_do_bloco), 0.55, clara=False, direcao="chapado")
    _veu(tela, (0, base_do_bloco, largura, min(altura, base_do_bloco + round(altura * 0.22))),
         0.55, clara=False, direcao="baixo")

    y = topo
    for linha in linhas:
        _escrever(desenho, linha, fonte, (x, y), (252, 252, 253),
                  tipografia.titulo_entreletra)
        y += _entrelinha(fonte, 1.1)
    if linhas_sub:
        y += round(fonte.size * 0.34)
        for linha in linhas_sub:
            _escrever(desenho, linha, fonte_sub, (x, y), (240, 240, 244))
            y += _entrelinha(fonte_sub, 1.38)
    return Composta(tela)


def _grade(fotos, largura, altura, colunas, linhas, vao):
    """Recorta as fotos numa grade regular e devolve as peças e o tamanho."""
    celula_l = (largura - vao * (colunas - 1)) // colunas
    celula_a = (altura - vao * (linhas - 1)) // linhas
    pecas = []
    for indice in range(colunas * linhas):
        foto = fotos[indice % len(fotos)]
        pecas.append((_preencher(foto, celula_l, celula_a),
                      (indice % colunas) * (celula_l + vao),
                      (indice // colunas) * (celula_a + vao)))
    return pecas, celula_l, celula_a


def ritmos(fotos, largura, altura, titulo, subtitulo="", credito="", tipografia=None) -> Composta:
    """Grade 2x2 simétrica sobre campo claro, texto centralizado abaixo."""
    if not fotos:
        raise ValueError("A capa em grade exige ao menos uma fotografia.")
    tipografia = tipografia or par("geometrico")
    subtitulo = _apoio(subtitulo, credito)
    fundo = cor_capa.fundo_claro_da_capa(fotos[0])
    tela = Image.new("RGB", (largura, altura), fundo)

    margem = round(altura * 0.09)
    vao = round(altura * 0.028)
    area_texto = round(altura * 0.26)
    grade_l = largura - 2 * margem
    grade_a = altura - margem - area_texto
    # Grade quadrada e centrada: o guia pede quatro fotos iguais, com respiro.
    lado = min(grade_l, grade_a)
    pecas, _, _ = _grade(fotos, lado, lado, 2, 2, vao)
    origem_x = (largura - lado) // 2
    for peca, x, y in pecas:
        tela.paste(peca, (origem_x + x, margem + y))

    desenho = ImageDraw.Draw(tela)
    tinta = (28, 29, 33)
    texto = (titulo or "").strip()
    if tipografia.titulo_caixa_alta:
        texto = texto.upper()
    fonte, linhas = _encaixar(desenho, texto, tipografia.titulo, _pt(36, altura),
                              round(largura * 0.72), tipografia.titulo_entreletra)
    y = margem + lado + round(altura * 0.055)
    for linha in linhas:
        comprimento = desenho.textlength(linha, font=fonte)
        _escrever(desenho, linha, fonte, (round((largura - comprimento) / 2), y), tinta,
                  tipografia.titulo_entreletra)
        y += _entrelinha(fonte, 1.14)

    if (subtitulo or "").strip():
        fonte_sub = _fonte(tipografia.subtitulo, _pt(14, altura))
        y += round(fonte.size * 0.22)
        comprimento = desenho.textlength(subtitulo.strip(), font=fonte_sub)
        _escrever(desenho, subtitulo.strip(), fonte_sub,
                  (round((largura - comprimento) / 2), y), (104, 106, 112))
    return Composta(tela)


def fragmentos(fotos, largura, altura, titulo, subtitulo="", credito="", tipografia=None) -> Composta:
    """Colagem diagonal de três fotos à esquerda, texto no respiro à direita."""
    if not fotos:
        raise ValueError("A colagem exige ao menos uma fotografia.")
    tipografia = tipografia or par("editorial")
    subtitulo = _apoio(subtitulo, credito)
    fundo = cor_capa.fundo_claro_da_capa(fotos[0])
    tela = Image.new("RGB", (largura, altura), fundo)

    # Três peças em diagonal, com leve sobreposição e moldura branca — o efeito
    # de fotografia impressa apoiada sobre a capa.
    disposicao = (
        (0.055, 0.10, 0.34, 0.52),
        (0.215, 0.34, 0.28, 0.44),
        (0.360, 0.60, 0.26, 0.34),
    )
    moldura = max(2, round(altura * 0.012))
    for indice, (rx, ry, rl, ra) in enumerate(disposicao):
        foto = fotos[indice % len(fotos)]
        peca_l, peca_a = round(largura * rl), round(altura * ra)
        peca = _preencher(foto, peca_l, peca_a)
        cartao = Image.new("RGB", (peca_l + 2 * moldura, peca_a + 2 * moldura),
                           (252, 251, 249))
        cartao.paste(peca, (moldura, moldura))
        tela.paste(cartao, (round(largura * rx), round(altura * ry)))

    desenho = ImageDraw.Draw(tela)
    tinta = (34, 32, 30)
    x = round(largura * 0.56)
    limite = largura - x - round(largura * 0.06)
    texto = (titulo or "").strip()
    if tipografia.titulo_caixa_alta:
        texto = texto.upper()
    fonte, linhas = _encaixar(desenho, texto, tipografia.titulo, _pt(42, altura),
                              limite, tipografia.titulo_entreletra)
    y = round(altura * 0.14)
    for linha in linhas:
        _escrever(desenho, linha, fonte, (x, y), tinta, tipografia.titulo_entreletra)
        y += _entrelinha(fonte, 1.12)

    if (subtitulo or "").strip():
        fonte_sub = _fonte(tipografia.subtitulo, _pt(16, altura))
        y += round(fonte.size * 0.3)
        for linha in _linhas_de_apoio(desenho, subtitulo, fonte_sub, limite):
            _escrever(desenho, linha, fonte_sub, (x, y), (108, 104, 98))
            y += _entrelinha(fonte_sub, 1.32)
    return Composta(tela)


def contrastes(fotos, largura, altura, titulo, subtitulo="", credito="", tipografia=None) -> Composta:
    """Mosaico assimétrico sobre cinza, com o título girado na vertical."""
    if not fotos:
        raise ValueError("O mosaico exige ao menos uma fotografia.")
    tipografia = tipografia or par("geometrico")
    subtitulo = _apoio(subtitulo, credito)
    claro = cor_capa.fundo_claro_da_capa(fotos[0])
    # Cinza neutro do guia: o claro extraído, rebaixado para o mosaico saltar.
    fundo = tuple(round(canal * 0.72) for canal in claro)
    tela = Image.new("RGB", (largura, altura), fundo)

    margem = round(altura * 0.06)
    faixa_texto = round(largura * 0.16)
    area_l = largura - 2 * margem - faixa_texto
    area_a = altura - 2 * margem
    vao = round(altura * 0.022)

    # Uma vertical grande à direita da área, duas menores empilhadas à esquerda.
    grande_l = round(area_l * 0.46)
    tela.paste(_preencher(fotos[0], grande_l, area_a),
               (margem + area_l - grande_l, margem))
    menor_l = area_l - grande_l - vao
    menor_a = (area_a - vao) // 2
    for indice in range(2):
        foto = fotos[(indice + 1) % len(fotos)]
        tela.paste(_preencher(foto, menor_l, menor_a),
                   (margem, margem + indice * (menor_a + vao)))

    desenho = ImageDraw.Draw(tela)
    tinta = (24, 25, 28)
    texto = (titulo or "").strip().upper()
    # O subtítulo divide a faixa com o título: mede-se primeiro, para o título
    # ceder corpo em vez de descer por cima dele.
    x_faixa = largura - faixa_texto + round(faixa_texto * 0.1)
    # A faixa é estreita de propósito, e o crédito precisa caber nela inteiro.
    limite_faixa = faixa_texto - round(faixa_texto * 0.2)
    fonte_sub = _fonte_de_apoio(desenho, subtitulo, tipografia.subtitulo,
                                _pt(13, altura), limite_faixa, minimo=7)
    linhas_sub = (_linhas_de_apoio(desenho, subtitulo, fonte_sub, limite_faixa)
                  if (subtitulo or "").strip() else [])
    pe = sum(_entrelinha(fonte_sub, 1.3) for _ in linhas_sub)
    if pe:
        pe += round(altura * 0.03)

    girada = _tira_girada(texto, tipografia.titulo, _pt(56, altura),
                          altura - 2 * margem - pe, tinta,
                          tipografia.titulo_entreletra, 270)
    tela.paste(girada, (x_faixa, margem), girada)

    # Ao pé do título vertical: sobre as fotos ele ficava ilegível e cortado.
    y = altura - margem - sum(_entrelinha(fonte_sub, 1.3) for _ in linhas_sub)
    for linha in linhas_sub:
        _escrever(desenho, linha, fonte_sub, (x_faixa, y), (58, 59, 64))
        y += _entrelinha(fonte_sub, 1.3)
    return Composta(tela)


def caminho(fotos, largura, altura, titulo, subtitulo="", credito="", tipografia=None) -> Composta:
    """Três fotos em sequência na metade inferior, respiro amplo em cima."""
    if not fotos:
        raise ValueError("A narrativa linear exige ao menos uma fotografia.")
    tipografia = tipografia or par("narrativo")
    subtitulo = _apoio(subtitulo, credito)
    fundo = cor_capa.fundo_claro_da_capa(fotos[0])
    # Bege quente: o claro extraído, levemente rebaixado para não competir.
    fundo = tuple(round(canal * 0.93) for canal in fundo)
    tela = Image.new("RGB", (largura, altura), fundo)

    margem = round(largura * 0.075)
    vao = round(largura * 0.018)
    faixa_a = round(altura * 0.34)
    faixa_y = altura - margem - faixa_a
    peca_l = (largura - 2 * margem - 2 * vao) // 3
    for indice in range(3):
        foto = fotos[indice % len(fotos)]
        tela.paste(_preencher(foto, peca_l, faixa_a),
                   (margem + indice * (peca_l + vao), faixa_y))

    desenho = ImageDraw.Draw(tela)
    tinta = (40, 36, 31)
    texto = (titulo or "").strip()
    if tipografia.titulo_caixa_alta:
        texto = texto.upper()
    fonte, linhas = _encaixar(desenho, texto, tipografia.titulo, _pt(48, altura),
                              round(largura * 0.78), tipografia.titulo_entreletra)
    y = round(altura * 0.16)
    for linha in linhas:
        comprimento = desenho.textlength(linha, font=fonte)
        _escrever(desenho, linha, fonte, (round((largura - comprimento) / 2), y), tinta,
                  tipografia.titulo_entreletra)
        y += _entrelinha(fonte, 1.12)

    if (subtitulo or "").strip():
        fonte_sub = _fonte(tipografia.subtitulo, _pt(18, altura))
        y += round(fonte.size * 0.26)
        for linha in _linhas_de_apoio(desenho, subtitulo, fonte_sub, round(largura * 0.7)):
            comprimento = desenho.textlength(linha, font=fonte_sub)
            _escrever(desenho, linha, fonte_sub,
                      (round((largura - comprimento) / 2), y), (96, 90, 82))
            y += _entrelinha(fonte_sub, 1.3)
    return Composta(tela)


#: Nome do estilo → função que o desenha, e se ele consome uma foto ou várias.
ESTILOS_EDITORIAIS = {
    "jornada": (jornada, False),
    "toscana": (toscana, False),
    "neon": (neon, False),
    "fluir": (fluir, False),
    "ritmos": (ritmos, True),
    "fragmentos": (fragmentos, True),
    "contrastes": (contrastes, True),
    "caminho": (caminho, True),
}
