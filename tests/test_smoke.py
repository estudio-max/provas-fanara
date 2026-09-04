def test_package_imports():
    from provas import capas, documento, imagens, motor, tema

    assert motor.QUALIDADES["normal"] == (200, 85)
