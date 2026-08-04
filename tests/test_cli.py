from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pymupdf
import pytest


ROOT = Path(__file__).parents[1]
CLI = ROOT / "provas_cli.py"


def executar(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_gera_amostra_de_prova_com_semente_e_mensagens_em_portugues(
    tmp_path: Path, image_factory
):
    image_factory("prova.jpg", size=(300, 450))
    saida = tmp_path / "prova.pdf"

    result = executar(
        str(tmp_path), "--modo", "prova", "--semente", "42", "--amostra", "--saida", str(saida),
    )

    assert result.returncode == 0, result.stderr
    assert saida.exists()
    assert "Modo: prova" in result.stdout
    assert "Semente: 42" in result.stdout
    assert "fotos" in result.stdout
    with pymupdf.open(saida) as pdf:
        assert "prova" in "".join(page.get_text().lower() for page in pdf)


def test_cli_gera_amostra_de_fotolivro_sem_marca_ou_codigos(tmp_path: Path, image_factory):
    image_factory("fotolivro.jpg", size=(300, 450))
    saida = tmp_path / "fotolivro.pdf"

    result = executar(str(tmp_path), "--modo", "fotolivro", "--amostra", "--saida", str(saida))

    assert result.returncode == 0, result.stderr
    assert saida.exists()
    assert "Modo: fotolivro" in result.stdout
    with pymupdf.open(saida) as pdf:
        assert "fotolivro" not in "".join(page.get_text().lower() for page in pdf)


def test_cli_rejeita_modo_invalido_em_portugues(tmp_path: Path):
    result = executar(str(tmp_path), "--modo", "album")

    assert result.returncode == 2
    assert "modo inválido" in result.stderr.lower()


def test_cli_salva_e_abre_projeto_apenas_em_novo_destino_pdf_explicito(tmp_path: Path, image_factory):
    image_factory("projeto.jpg", size=(300, 450))
    projeto = tmp_path / "sessao.provas.json"
    saida = tmp_path / "projeto.pdf"

    saved = executar(
        str(tmp_path), "--modo", "fotolivro", "--semente", "42", "--amostra",
        "--salvar-projeto", str(projeto), "--saida", str(saida),
    )
    recusado = executar("--abrir-projeto", str(projeto))
    destino_reaberto = tmp_path / "reaberto.pdf"
    opened = executar("--abrir-projeto", str(projeto), "--saida", str(destino_reaberto))

    assert saved.returncode == 0, saved.stderr
    assert projeto.exists()
    assert "Projeto salvo" in saved.stdout
    assert recusado.returncode == 2
    assert "--saida" in recusado.stderr
    assert opened.returncode == 0, opened.stderr
    assert "Projeto aberto" in opened.stdout
    assert destino_reaberto.exists()


def test_cli_rejeita_destino_de_reabertura_que_nao_e_pdf(tmp_path: Path, image_factory):
    image_factory("projeto.jpg", size=(300, 450))
    projeto = tmp_path / "sessao.provas.json"
    executar(str(tmp_path), "--amostra", "--salvar-projeto", str(projeto))

    result = executar("--abrir-projeto", str(projeto), "--saida", str(tmp_path / "fora.txt"))

    assert result.returncode == 2
    assert "pdf" in result.stderr.lower()


def test_cli_album_e_alias_obsoleto_para_fotolivro(tmp_path: Path, image_factory):
    image_factory("album.jpg", size=(300, 450))
    saida = tmp_path / "album.pdf"

    result = executar(str(tmp_path), "--album", "--amostra", "--saida", str(saida))

    assert result.returncode == 0, result.stderr
    assert "Modo: fotolivro" in result.stdout
    assert saida.exists()


def test_cli_rejeita_flags_que_quebrariam_os_modos_e_mantem_help_em_portugues(tmp_path: Path):
    result = executar(str(tmp_path), "--sem-marca")
    help_result = executar("--help")

    assert result.returncode == 2
    assert "não reconhecido" in result.stderr.lower()
    assert "uso:" in help_result.stdout.lower()
    assert "opções:" in help_result.stdout.lower()
    assert "--sem-marca" not in help_result.stdout


@pytest.mark.parametrize(
    ("args", "mensagem"),
    [
        ((), "informe a pasta"),
        (("--modo",), "exige um valor"),
        (("--por-pagina", "quatro"), "número inteiro inválido"),
        (("--qualidade", "ultra"), "qualidade inválida"),
        (("--desconhecida",), "argumentos não reconhecidos"),
    ],
)
def test_cli_erros_comuns_do_argparse_sao_integralmente_em_portugues(args, mensagem):
    result = executar(*args)

    assert result.returncode == 2
    assert mensagem in result.stderr.lower()
    assert "usage:" not in result.stderr.lower()
    assert "error:" not in result.stderr.lower()
    assert "invalid" not in result.stderr.lower()
    assert "argument " not in result.stderr.lower()


def test_cli_ajuda_curta_e_uso_nao_expoem_texto_ingles():
    result = executar("-h")

    assert result.returncode == 0
    assert "uso:" in result.stdout.lower()
    assert "mostra esta ajuda e encerra" in result.stdout.lower()
    assert "usage:" not in result.stdout.lower()
    assert "show this help message" not in result.stdout.lower()


def test_verificador_lista_dependencias_editoriais_e_permissao_de_escrita():
    result = subprocess.run(
        [sys.executable, str(ROOT / "verificar.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PySide6" in result.stdout
    assert "permissão de escrita" in result.stdout.lower()
    assert "pipeline editorial" in result.stdout.lower()


def test_verificador_compara_versoes_minimas_e_ainda_diagnostica_fontes(monkeypatch, capsys):
    import verificar

    monkeypatch.setattr(verificar, "diagnosticar_dependencias", lambda: 1)
    monkeypatch.setattr(verificar, "testar_escrita", lambda: 0)
    monkeypatch.setattr(verificar, "testar_pipeline_editorial", lambda: 0)
    fontes = []
    monkeypatch.setattr(verificar, "diagnosticar_fontes", lambda: fontes.append(True))

    assert verificar.main([]) == 1
    assert fontes == [True]
    assert "Resolva" in capsys.readouterr().out


def test_verificador_rejeita_versoes_abaixo_do_minimo():
    import verificar

    assert verificar.versao_compativel("9.9", "10.0") is False
    assert verificar.versao_compativel("1.23.9", "1.24") is False
    assert verificar.versao_compativel("10.0rc1", "10.0") is False
    assert verificar.versao_compativel("6.7.0", "6.7") is True
