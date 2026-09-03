def test_package_imports():
    from provas import capas, documento, imagens, motor, tema

    assert motor.QUALIDADES["normal"] == (200, 85)


def test_preferencias_saem_da_pasta_somente_leitura(tmp_path, monkeypatch):
    """Instalado pela Store (MSIX), a pasta do executavel nao aceita escrita."""
    from provas import app

    assert app._gravavel(str(tmp_path)), "pasta gravavel tem de passar no teste"

    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app.sys, "platform", "win32")
    monkeypatch.setattr(app, "_gravavel", lambda _: False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert app._pasta_gravavel() == str(tmp_path / "Provas")
