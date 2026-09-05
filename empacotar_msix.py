r"""Gera o pacote .msix do Fanara - Fotolivro — o formato que a Store aceita.

    python empacotar_msix.py

Reaproveita o executável que o `empacotar.py` produz (`dist/Fanara - Fotolivro/`)
e o embrulha num MSIX com o manifesto, os logotipos de bloco e o índice de
recursos. Sai em `dist/Fanara - Fotolivro-<versão>-x64.msix`.

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

from empacotar import NOME, RAIZ, gerar_icone, remover_dados_usuario
from provas.recursos import ORGANIZATION_NAME, VERSION

# --- Partner Center → Identidade do produto -------------------------------
# Copiados de Partner Center > Fanara Fotolivro > Identidade do produto, do
# produto MSIX (Store ID 9NM0LV9V135F). Têm de bater exatamente: a Store recusa
# o envio se divergirem. Repare que a Microsoft tira o acento de "Estúdio" no
# nome do pacote, mas o mantém no nome de exibição.
IDENTIDADE = "EstdioFanara.FanaraFotolivro"                 # "Nome do pacote"
PUBLICADOR = "CN=12E00B3F-F6C2-4C38-A1D8-F1E54FE1BCAA"      # "Publicador"
NOME_PUBLICADOR = ORGANIZATION_NAME                         # "Nome de exibição"
STORE_ID = "9NM0LV9V135F"                                   # apps.microsoft.com/detail/…
# --------------------------------------------------------------------------

# A Store exige que o último número da versão seja 0; o resto vem da fonte única.
VERSAO = f"{VERSION}.0"
DESCRICAO = ("Mesa de edição para montar o fotolivro a partir da pasta do ensaio: "
             "analisa as fotografias, diagrama as páginas, monta a capa e exporta o "
             "PDF. Serve tanto para a prova de seleção, com marca d'água e códigos, "
             "quanto para o fotolivro limpo.")

DIST = os.path.join(RAIZ, "dist")
BUILD = os.path.join(RAIZ, "build")
PALCO = os.path.join(BUILD, "msix")

# Os três que a Store cobra; o resto o Windows deriva destes.
LOGOTIPOS = {
    "Square44x44Logo.png": 44,
    "Square150x150Logo.png": 150,
    "StoreLogo.png": 50,
}

MANIFESTO_XML = r"""<?xml version="1.0" encoding="utf-8"?>
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
    <Application Id="Fotolivro" Executable="{nome}\{nome}.exe"
                 EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="{nome}"
        Description="{descricao}"
        BackgroundColor="#111215"
        Square150x150Logo="Assets\Square150x150Logo.png"
        Square44x44Logo="Assets\Square44x44Logo.png">
        <uap:DefaultTile ShortName="Fotolivro" />
      </uap:VisualElements>
    </Application>
  </Applications>

  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""


def manifesto() -> str:
    """O AppxManifest.xml deste build. Isolado para o teste poder conferi-lo."""
    return MANIFESTO_XML.format(
        identidade=IDENTIDADE, publicador=PUBLICADOR, versao=VERSAO,
        nome=NOME, nome_publicador=NOME_PUBLICADOR, descricao=DESCRICAO)


def ferramenta(nome: str) -> str:
    """Acha o utilitário do SDK do Windows na versão mais nova instalada."""
    padroes = [
        rf"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\{nome}",
        rf"C:\Program Files\Windows Kits\10\bin\*\x64\{nome}",
    ]
    achados = sorted(c for p in padroes for c in glob.glob(p))
    if not achados:
        raise SystemExit(
            f"{nome} não encontrado. Instale o Windows SDK:\n"
            "  winget install Microsoft.WindowsSDK.10.0.26100")
    return achados[-1]


def montar_palco() -> None:
    """Monta a árvore que vira o pacote: o app, os logotipos e o manifesto."""
    origem = os.path.join(DIST, NOME)
    if not os.path.isfile(os.path.join(origem, f"{NOME}.exe")):
        print("dist ainda não existe — rodando empacotar.py…")
        if subprocess.run([sys.executable, os.path.join(RAIZ, "empacotar.py")],
                          cwd=RAIZ).returncode != 0:
            raise SystemExit("empacotar.py falhou.")

    shutil.rmtree(PALCO, ignore_errors=True)
    os.makedirs(PALCO)

    destino = os.path.join(PALCO, NOME)
    shutil.copytree(origem, destino)
    # Mesmo contrato do zip: preferências e marca d'água do fotógrafo não saem
    # desta máquina.
    remover_dados_usuario(destino)

    from PIL import Image
    simbolo = os.path.join(RAIZ, "assets", "fanara-symbol.png")
    if not os.path.isfile(simbolo):
        gerar_icone()
    base = Image.open(simbolo).convert("RGBA")
    pasta = os.path.join(PALCO, "Assets")
    os.makedirs(pasta)
    for arquivo, lado in LOGOTIPOS.items():
        base.resize((lado, lado), Image.Resampling.LANCZOS).save(
            os.path.join(pasta, arquivo))

    with open(os.path.join(PALCO, "AppxManifest.xml"), "w", encoding="utf-8") as saida:
        saida.write(manifesto())


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
    print("  Get-AppxPackage *Fotolivro* | Remove-AppxPackage    (para desinstalar)")
    print()
    print("Enviar: Partner Center > seu app > Pacotes > arraste o .msix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
