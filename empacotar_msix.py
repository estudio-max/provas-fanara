r"""Gera o pacote .msix do Provas — o formato que a Microsoft Store aceita.

    python empacotar_msix.py

Reaproveita o executável que o `empacotar.py` produz (`dist/Provas/`) e o
embrulha num MSIX com o manifesto, os logotipos de bloco e o índice de
recursos. Sai em `dist/Provas-<versão>-x64.msix`.

ANTES DE ENVIAR PARA A STORE, troque os três valores abaixo pelos que o
Partner Center mostra em "Identidade do produto" depois de reservar o nome do
app. Eles têm de bater exatamente, senão o envio é recusado.

Para testar na própria máquina não é preciso assinar nem mexer nos valores:
com o Modo de Desenvolvedor ligado, instale a pasta montada direto —

    Add-AppxPackage -Register build\msix\AppxManifest.xml

O pacote enviado à Store não precisa de assinatura: a Microsoft assina.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys

# --- Partner Center → Identidade do produto -------------------------------
IDENTIDADE = "EstudioFanara.Provas"        # "Nome do pacote"
PUBLICADOR = "CN=Estudio Fanara"           # "Publicador" (vem como CN=<GUID>)
NOME_PUBLICADOR = "Estúdio Fanara"         # "Nome de exibição do publicador"
# --------------------------------------------------------------------------

NOME = "Provas"
# A Store exige que o último número da versão seja 0.
VERSAO = "1.0.0.0"
DESCRICAO = ("Monta o PDF de seleção de fotos a partir da pasta do ensaio: capa com as "
             "próprias fotos, marca d'água gravada nos pixels e o código do arquivo sob "
             "cada imagem. Lê JPG e a pré-visualização embutida nos arquivos RAW.")

RAIZ = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(RAIZ, "dist")
BUILD = os.path.join(RAIZ, "build")
PALCO = os.path.join(BUILD, "msix")

MANIFESTO = r"""<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap rescap">

  <Identity Name="{identidade}" Publisher="{publicador}" Version="{versao}"
            ProcessorArchitecture="x64" />

  <Properties>
    <DisplayName>{nome}</DisplayName>
    <PublisherDisplayName>{nome_publicador}</PublisherDisplayName>
    <Logo>Assets\StoreLogo.png</Logo>
  </Properties>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0"
                        MaxVersionTested="10.0.26100.0" />
  </Dependencies>

  <Resources>
    <Resource Language="pt-BR" />
  </Resources>

  <Applications>
    <Application Id="Provas" Executable="Provas\Provas.exe"
                 EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="{nome}"
        Description="{descricao}"
        BackgroundColor="#16161a"
        Square150x150Logo="Assets\Square150x150Logo.png"
        Square44x44Logo="Assets\Square44x44Logo.png">
        <uap:DefaultTile ShortName="{nome}" />
      </uap:VisualElements>
    </Application>
  </Applications>

  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""

# Os três que a Store cobra; o resto o Windows deriva destes.
LOGOTIPOS = {
    "Square44x44Logo.png": 44,
    "Square150x150Logo.png": 150,
    "StoreLogo.png": 50,
}


def ferramenta(nome: str) -> str:
    """Acha o utilitário do SDK do Windows na versão mais nova instalada."""
    padroes = [
        rf"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\{nome}",
        rf"C:\Program Files\Windows Kits\10\bin\*\x64\{nome}",
    ]
    achados = sorted(c for p in padroes for c in glob.glob(p))
    if not achados:
        raise SystemExit(
            f"{nome} não encontrado. Instale o Windows SDK (componente "
            f'"Windows SDK Signing Tools"/"MSIX Packaging Tools"):\n'
            "  winget install Microsoft.WindowsSDK.10.0.26100")
    return achados[-1]


def montar_palco() -> None:
    """Monta a árvore que vira o pacote: o app, os logotipos e o manifesto."""
    origem = os.path.join(DIST, NOME)
    if not os.path.isfile(os.path.join(origem, f"{NOME}.exe")):
        print("dist/Provas ainda não existe — rodando empacotar.py…")
        if subprocess.run([sys.executable, os.path.join(RAIZ, "empacotar.py")],
                          cwd=RAIZ).returncode != 0:
            raise SystemExit("empacotar.py falhou.")

    shutil.rmtree(PALCO, ignore_errors=True)
    os.makedirs(PALCO)

    # config.json é do meu computador e LEIA-ME é conversa de zip: nenhum dos
    # dois vai para a Store.
    shutil.copytree(origem, os.path.join(PALCO, NOME),
                    ignore=shutil.ignore_patterns("config.json", "LEIA-ME.txt"))

    from PIL import Image
    icone = os.path.join(RAIZ, "assets", "icone.ico")
    if not os.path.isfile(icone):
        import empacotar
        empacotar.gerar_icone()
    base = Image.open(icone).convert("RGBA")
    pasta = os.path.join(PALCO, "Assets")
    os.makedirs(pasta)
    for arquivo, lado in LOGOTIPOS.items():
        base.resize((lado, lado), Image.Resampling.LANCZOS).save(
            os.path.join(pasta, arquivo))

    with open(os.path.join(PALCO, "AppxManifest.xml"), "w", encoding="utf-8") as saida:
        saida.write(MANIFESTO.format(
            identidade=IDENTIDADE, publicador=PUBLICADOR, versao=VERSAO,
            nome=NOME, nome_publicador=NOME_PUBLICADOR, descricao=DESCRICAO))


def indexar_recursos() -> None:
    """resources.pri — a Store reclama do pacote sem índice de recursos."""
    config = os.path.join(BUILD, "priconfig.xml")
    pri = os.path.join(BUILD, "resources.pri")
    makepri = ferramenta("makepri.exe")
    passos = [
        [makepri, "createconfig", "/cf", config, "/dq", "pt-BR", "/o"],
        [makepri, "new", "/pr", PALCO, "/cf", config, "/of", pri, "/o"],
    ]
    for passo in passos:
        if subprocess.run(passo, capture_output=True).returncode != 0:
            print("Aviso: makepri falhou; o pacote sai sem resources.pri.")
            return
    shutil.copy2(pri, os.path.join(PALCO, "resources.pri"))


def main() -> int:
    montar_palco()
    indexar_recursos()

    destino = os.path.join(DIST, f"{NOME}-{VERSAO}-x64.msix")
    resultado = subprocess.run(
        [ferramenta("makeappx.exe"), "pack", "/d", PALCO, "/p", destino, "/o"])
    if resultado.returncode != 0:
        return resultado.returncode

    print(f"\nPacote: {destino}  ({os.path.getsize(destino) / 1e6:.0f} MB)")
    print(f"Identidade: {IDENTIDADE} / {PUBLICADOR} / {VERSAO}")
    print("\nTestar aqui (Modo de Desenvolvedor ligado):")
    print(rf"  Add-AppxPackage -Register {os.path.join(PALCO, 'AppxManifest.xml')}")
    print("  Get-AppxPackage *Provas* | Remove-AppxPackage      (para desinstalar)")
    print()
    print("Enviar: Partner Center > seu app > Pacotes > arraste o .msix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
