from __future__ import annotations

from pathlib import Path
import subprocess
import sys


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


def test_cli_gera_amostra_de_fotolivro_sem_marca_ou_codigos(tmp_path: Path, image_factory):
    image_factory("fotolivro.jpg", size=(300, 450))
    saida = tmp_path / "fotolivro.pdf"

    result = executar(str(tmp_path), "--modo", "fotolivro", "--amostra", "--saida", str(saida))

    assert result.returncode == 0, result.stderr
    assert saida.exists()
    assert "Modo: fotolivro" in result.stdout


def test_cli_rejeita_modo_invalido_em_portugues(tmp_path: Path):
    result = executar(str(tmp_path), "--modo", "album")

    assert result.returncode == 2
    assert "modo inválido" in result.stderr.lower()


def test_cli_salva_e_abre_projeto_para_exportar_o_mesmo_plano(tmp_path: Path, image_factory):
    image_factory("projeto.jpg", size=(300, 450))
    projeto = tmp_path / "sessao.provas.json"
    saida = tmp_path / "projeto.pdf"

    saved = executar(
        str(tmp_path), "--modo", "fotolivro", "--semente", "42", "--amostra",
        "--salvar-projeto", str(projeto), "--saida", str(saida),
    )
    opened = executar("--abrir-projeto", str(projeto))

    assert saved.returncode == 0, saved.stderr
    assert projeto.exists()
    assert "Projeto salvo" in saved.stdout
    assert opened.returncode == 0, opened.stderr
    assert "Projeto aberto" in opened.stdout
    assert saida.exists()


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
