"""Interface de linha de comando do Fotolivro editorial.

    python provas_cli.py "C:\\ensaios\\Bianca" --modo fotolivro --semente 42
    python provas_cli.py --abrir-projeto "C:\\ensaios\\Bianca.provas.json"
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from provas import capas, motor, tema
from provas.projeto import ProjectState, load_project, save_project


MODOS = ("prova", "fotolivro")


def modo_editorial(value: str) -> str:
    """Validate modes with an actionable, Portuguese argparse error."""
    if value not in MODOS:
        raise argparse.ArgumentTypeError(
            f"modo inválido: {value!r}. Use 'prova' ou 'fotolivro'."
        )
    return value


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gera um PDF editorial de uma sessão fotográfica.")
    parser.add_argument("pasta", nargs="?", help="pasta com as fotos da sessão")
    parser.add_argument("-o", "--saida", default="", help="caminho do PDF (padrão: dentro da pasta)")
    parser.add_argument("-t", "--titulo", default="", help="título da capa")
    parser.add_argument("-d", "--data", default="", help="data mostrada na capa")
    parser.add_argument("-n", "--por-pagina", type=int, default=4, help="fotos por página")
    parser.add_argument("-q", "--qualidade", choices=list(motor.QUALIDADES), default="normal")
    parser.add_argument("--logo", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png"))
    parser.add_argument("--estudio", default="", help="nome exibido quando não há logotipo")
    parser.add_argument("--site", default="", help="endereço mostrado no rodapé")
    parser.add_argument("--fundo", default=tema.FUNDO_PADRAO, help="cor de fundo, ex.: #16161A")
    parser.add_argument("--opacidade", type=float, default=0.20, help="força da marca d'água")
    parser.add_argument("--capa", choices=list(capas.ESTILOS), default="mosaico")
    parser.add_argument("--sem-capa", action="store_true")
    parser.add_argument("--sem-marca", action="store_true", help="não aplicar marca d'água no modo prova")
    parser.add_argument("--sem-codigos", action="store_true", help="não escrever códigos no modo prova")
    parser.add_argument("--modo", type=modo_editorial, metavar="{prova,fotolivro}", default="prova",
                        help="prova com marca e códigos, ou fotolivro limpo")
    parser.add_argument("--album", dest="modo", action="store_const", const="fotolivro",
                        help="obsoleto: use --modo fotolivro")
    parser.add_argument("--semente", type=int, default=0, help="semente reproduzível do plano editorial")
    parser.add_argument("--salvar-projeto", default="", metavar="ARQUIVO",
                        help="salva o plano reproduzível em um arquivo .provas.json")
    parser.add_argument("--abrir-projeto", default="", metavar="ARQUIVO",
                        help="abre um projeto salvo e exporta exatamente seu plano")
    parser.add_argument("--subpastas", action="store_true")
    parser.add_argument("--amostra", action="store_true", help="usa só as 12 primeiras fotos")
    return parser


def config_dos_argumentos(args: argparse.Namespace) -> motor.Config:
    """Translate CLI switches into the constrained editorial configuration."""
    limpo = args.modo == "fotolivro"
    return motor.Config(
        pasta=args.pasta,
        saida=args.saida,
        titulo=args.titulo,
        subtitulo=args.data,
        por_pagina=args.por_pagina,
        qualidade=args.qualidade,
        logo=args.logo,
        marca_opacidade=args.opacidade,
        paisagem=True,
        estudio=args.estudio,
        site=args.site,
        cor_fundo=args.fundo,
        capa_mosaico=not args.sem_capa,
        estilo_capa=args.capa,
        marca_dagua=not (limpo or args.sem_marca),
        mostrar_codigos=not (limpo or args.sem_codigos),
        girar_horizontais=False,
        recursivo=args.subpastas,
        limite=12 if args.amostra else 0,
        modo=args.modo,
        semente=args.semente,
    )


def _progresso() -> tuple[callable, list[str]]:
    ultimo = [""]

    def informar(_feito: int, _total: int, mensagem: str) -> None:
        if mensagem != ultimo[0]:
            ultimo[0] = mensagem
            print(f"\r{mensagem:<48}", end="", flush=True)

    return informar, ultimo


def _salvar_estado(path: str, config: motor.Config, analysis: motor.PlanAnalysisResult) -> None:
    state = ProjectState(
        config,
        analysis.plan,
        tuple(photo.path for photo in analysis.photos),
    )
    save_project(path, state)


def main(argv: list[str] | None = None) -> int:
    parser = criar_parser()
    args = parser.parse_args(argv)
    progresso, _ultimo = _progresso()

    try:
        if args.abrir_projeto:
            state = load_project(args.abrir_projeto)
            config = state.config.to_motor_config()
            if args.saida:
                config.saida = args.saida
            resultado = motor.exportar(config, state.plan, progresso=progresso)
            print(f"\nProjeto aberto: {args.abrir_projeto}")
            modo = state.plan.mode
            semente = state.plan.seed
        else:
            if not args.pasta:
                parser.error("informe a pasta da sessão ou use --abrir-projeto")
            config = config_dos_argumentos(args)
            analysis = motor.analisar_plano(config, progresso=progresso)
            config = config.com_padroes()
            if args.salvar_projeto:
                _salvar_estado(args.salvar_projeto, config, analysis)
                print(f"\nProjeto salvo: {args.salvar_projeto}")
            resultado = motor.exportar(config, analysis.plan, progresso=progresso)
            modo = analysis.plan.mode
            semente = analysis.plan.seed
    except (OSError, ValueError) as erro:
        print(f"\nErro: {erro}", file=sys.stderr)
        return 1

    print(f"\nModo: {modo}")
    print(f"Semente: {semente}")
    print(resultado.saida)
    print(f"{resultado.fotos} fotos · {resultado.paginas} páginas")
    for nome, erro in resultado.falhas:
        print(f"  ignorado: {nome} ({erro})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
