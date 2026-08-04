"""Extração do JPEG de pré-visualização já embutido em arquivos RAW.

Os RAW da maioria das câmeras (NEF, CR2, ARW, DNG, ORF, PEF, RW2, SRW) são
containers TIFF: além dos dados do sensor, guardam um JPEG pronto — em geral do
tamanho total da imagem. Ler esse JPEG é ordens de grandeza mais rápido do que
revelar o RAW e é exatamente o que interessa para uma prova de seleção.
"""
from __future__ import annotations

import mmap
import struct

TAMANHO_TIPO = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 13: 4}

TAG_TIRAS_OFFSET = 273
TAG_ORIENTACAO = 274
TAG_TIRAS_BYTES = 279
TAG_COMPRESSAO = 259
TAG_JPEG_OFFSET = 513
TAG_JPEG_BYTES = 514
TAG_SUBIFDS = 330
TAG_EXIF_IFD = 34665

EXTENSOES = {".nef", ".nrw", ".cr2", ".arw", ".sr2", ".srf", ".dng",
             ".orf", ".pef", ".rw2", ".raf", ".srw", ".3fr", ".iiq"}


def _ler_ifd(buf, offset: int, ordem: str, limite: int):
    """Lê um IFD TIFF e devolve ({tag: valores}, offset do próximo IFD)."""
    if offset <= 0 or offset + 2 > limite:
        return {}, 0
    (quantas,) = struct.unpack_from(ordem + "H", buf, offset)
    if quantas > 4096:                      # IFD implausível: offset errado
        return {}, 0
    entradas: dict[int, list] = {}
    pos = offset + 2
    for _ in range(quantas):
        if pos + 12 > limite:
            break
        tag, tipo, n = struct.unpack_from(ordem + "HHI", buf, pos)
        tamanho = TAMANHO_TIPO.get(tipo, 0) * n
        if tamanho == 0 or tamanho > limite:
            pos += 12
            continue
        if tamanho <= 4:
            bruto = buf[pos + 8:pos + 8 + tamanho]
        else:
            (onde,) = struct.unpack_from(ordem + "I", buf, pos + 8)
            if onde + tamanho > limite:
                pos += 12
                continue
            bruto = buf[onde:onde + tamanho]
        if tipo in (3, 8) and len(bruto) == 2 * n:
            entradas[tag] = list(struct.unpack(ordem + "H" * n, bruto))
        elif tipo in (4, 9) and len(bruto) == 4 * n:
            entradas[tag] = list(struct.unpack(ordem + "I" * n, bruto))
        pos += 12
    proximo = 0
    if pos + 4 <= limite:
        (proximo,) = struct.unpack_from(ordem + "I", buf, pos)
    return entradas, proximo


def _percorrer_ifds(buf, ordem: str, primeiro: int, limite: int):
    """Visita IFD0, os IFDs seguintes, os SubIFDs e o IFD do Exif."""
    pendentes, vistos, encontrados = [primeiro], set(), []
    while pendentes:
        offset = pendentes.pop()
        if offset in vistos or len(vistos) > 64:
            continue
        vistos.add(offset)
        entradas, proximo = _ler_ifd(buf, offset, ordem, limite)
        if not entradas:
            continue
        encontrados.append(entradas)
        if proximo:
            pendentes.append(proximo)
        pendentes.extend(entradas.get(TAG_SUBIFDS, ()))
        pendentes.extend(entradas.get(TAG_EXIF_IFD, ()))
    return encontrados


def extrair_previa(caminho: str) -> tuple[bytes | None, int]:
    """Devolve (bytes do maior JPEG embutido, orientação Exif 1..8).

    Retorna (None, 1) quando o arquivo não é um RAW baseado em TIFF ou não
    guarda pré-visualização utilizável.
    """
    with open(caminho, "rb") as arquivo:
        with mmap.mmap(arquivo.fileno(), 0, access=mmap.ACCESS_READ) as buf:
            limite = len(buf)
            if limite < 16:
                return None, 1
            cabeca = buf[:2]
            if cabeca == b"II":
                ordem = "<"
            elif cabeca == b"MM":
                ordem = ">"
            else:
                return None, 1
            (primeiro,) = struct.unpack_from(ordem + "I", buf, 4)

            ifds = _percorrer_ifds(buf, ordem, primeiro, limite)

            orientacao = 1
            for entradas in ifds:
                valores = entradas.get(TAG_ORIENTACAO)
                if valores and 1 <= valores[0] <= 8:
                    orientacao = valores[0]
                    break

            melhor = None
            for entradas in ifds:
                candidatos = []
                if TAG_JPEG_OFFSET in entradas and TAG_JPEG_BYTES in entradas:
                    candidatos.append((entradas[TAG_JPEG_OFFSET][0], entradas[TAG_JPEG_BYTES][0]))
                if (TAG_TIRAS_OFFSET in entradas and TAG_TIRAS_BYTES in entradas
                        and entradas.get(TAG_COMPRESSAO, [0])[0] in (6, 7)):
                    candidatos.append((entradas[TAG_TIRAS_OFFSET][0], entradas[TAG_TIRAS_BYTES][0]))
                for offset, tamanho in candidatos:
                    if tamanho <= 2048 or offset + tamanho > limite:
                        continue
                    if buf[offset:offset + 2] != b"\xff\xd8":
                        continue
                    if melhor is None or tamanho > melhor[1]:
                        melhor = (offset, tamanho)

            if melhor is None:
                return None, orientacao
            return bytes(buf[melhor[0]:melhor[0] + melhor[1]]), orientacao


def e_raw(caminho: str) -> bool:
    ponto = caminho.rfind(".")
    return ponto >= 0 and caminho[ponto:].lower() in EXTENSOES
