"""Interface de linha de comando do Fotolivro editorial.

    python provas_cli.py "C:\\ensaios\\Bianca" --modo fotolivro --semente 42
    python provas_cli.py --abrir-projeto "C:\\ensaios\\Bianca.provas.json" --saida "C:\\entregas\\Bianca.pdf"
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from provas import capas, motor, tema
from provas.projeto import ProjectState, load_project, save_project


MODOS = ("prova", "fotolivro")


class ParserEmPortugues(argparse.ArgumentParser):
    """Keep the public command-line interface consistently in Portuguese."""

    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "uso:")

    def format_help(self) -> str:
        return (super().format_help()
                .replace("usage:", "uso:")
                .replace("positional arguments:", "argumentos posicionais:")
                .replace("options:", "opções:"))

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: erro: {message}\n")

    def _validar_valores_ausentes(self, valores: list[str]) -> None:
        for indice, valor in enumerate(valores):
            opcao = valor.split("=", 1)[0]
            acao = self._option_string_actions.get(opcao)
            if acao is None or "=" in valor or acao.nargs == 0:
                continue
            proximo = valores[indice + 1] if indice + 1 < len(valores) else ""
            if indice == len(valores) - 1 or proximo in self._option_string_actions:
                self.error(f"a opção {opcao} exige um valor")

    def _get_value(self, action, arg_string):
        """Convert typed options without argparse adding an English prefix."""
        type_func = self._registry_get("type", action.type, action.type)
        if not callable(type_func):
            raise TypeError(f"{type_func!r} não pode converter valores")
        try:
            return type_func(arg_string)
        except argparse.ArgumentTypeError as erro:
            opcao = action.option_strings[-1] if action.option_strings else action.dest
            raise argparse.ArgumentError(None, f"opção {opcao}: {erro}") from erro
        except (TypeError, ValueError) as erro:
            opcao = action.option_strings[-1] if action.option_strings else action.dest
            raise argparse.ArgumentError(None, f"opção {opcao}: valor inválido: {arg_string!r}") from erro

    def parse_args(self, args=None, namespace=None):
        valores = list(sys.argv[1:] if args is None else args)
        self._validar_valores_ausentes(valores)
        argumentos, desconhecidos = self.parse_known_args(valores, namespace)
        if desconhecidos:
            self.error(f"argumentos não reconhecidos: {' '.join(desconhecidos)}")
        return argumentos


def modo_editorial(value: str) -> str:
    """Validate modes with an actionable, Portuguese argparse error."""
    if value not in MODOS:
        raise argparse.ArgumentTypeError(
            f"modo inválido: {value!r}. Use 'prova' ou 'fotolivro'."
        )
    return value


def caminho_pdf(value: str) -> str:
    if value and Path(value).suffix.lower() != ".pdf":
        raise argparse.ArgumentTypeError("a saída deve terminar em .pdf")
    return value


def numero_inteiro(value: str) -> int:
    try:
        return int(value)
    except ValueError as erro:
        raise argparse.ArgumentTypeError(f"número inteiro inválido: {value!r}") from erro


def qualidade_editorial(value: str) -> str:
    if value not in motor.QUALIDADES:
        opcoes = ", ".join(motor.QUALIDADES)
        raise argparse.ArgumentTypeError(f"qualidade inválida: {value!r}. Use {opcoes}.")
    return value


def estilo_capa(value: str) -> str:
    if value not in capas.ESTILOS:
        opcoes = ", ".join(capas.ESTILOS)
        raise argparse.ArgumentTypeError(f"capa inválida: {value!r}. Use {opcoes}.")
    return value


def criar_parser() -> argparse.ArgumentParser:
    parser = ParserEmPortugues(
        description="Gera um PDF editorial de uma sessão fotográfica.", add_help=False,
    )
    parser.add_argument("-h", "--help", "--ajuda", action="help", help="mostra esta ajuda e encerra")
    parser.add_argument("pasta", nargs="?", help="pasta com as fotos da sessão")
    parser.add_argument("-o", "--saida", type=caminho_pdf, default="", help="caminho do PDF (padrão: dentro da pasta)")
    parser.add_argument("-t", "--titulo", default="", help="título da capa")
    parser.add_argument("-d", "--data", default="", help="data mostrada na capa")
    parser.add_argument("-n", "--por-pagina", type=numero_inteiro, default=4, help="fotos por página")
    parser.add_argument("-q", "--qualidade", type=qualidade_editorial, metavar="{leve,normal,alta}", default="normal")
    parser.add_argument("--logo", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png"))
    parser.add_argument("--estudio", default="", help="nome exibido quando não há logotipo")
    parser.add_argument("--site", default="", help="endereço mostrado no rodapé")
    parser.add_argument("--fundo", default=tema.FUNDO_PADRAO, help="cor de fundo, ex.: #16161A")
    parser.add_argument("--opacidade", type=float, default=0.20, help="força da marca d'água")
    parser.add_argument("--capa", type=estilo_capa, metavar="{mosaico,losango,destaque}", default="mosaico")
    parser.add_argument("--sem-capa", action="store_true")
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
        marca_dagua=not limpo,
        mostrar_codigos=not limpo,
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
            if not args.saida:
                parser.error("ao abrir um projeto, informe --saida com um novo arquivo .pdf")
            state = load_project(args.abrir_projeto)
            config = state.config.to_motor_config()
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
