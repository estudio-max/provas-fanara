r"""Gera o instalador .msi do Fanara - Fotolivro, para a URL que a Microsoft
Store pede em "Detalhes do pacote" (Tipo de aplicativo: MSI).

    python empacotar_msi.py

Reaproveita o executável que o `empacotar.py` produz (`dist/Fanara - Fotolivro/`)
e o embrulha num .msi de verdade: instala em Arquivos de Programas, cria atalho
no Menu Iniciar, aparece em "Programas e Recursos" com ícone e opção de
desinstalar. Sai em `dist/Fanara - Fotolivro-Setup-<versão>.msi`.

Um .msi já sabe instalar silenciosamente sozinho, sem precisar de nenhum
interruptor customizado:

    msiexec /i "Fanara - Fotolivro-Setup-1.0.0.msi" /quiet

Por isso, no formulário da Store, em "Parâmetros do instalador", marque
"O instalador roda no modo silencioso, mas não requer interruptores" — não é
preciso digitar nada no campo.

Requer o WiX Toolset (`winget install WiXToolset.WiXCLI`).
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys

from empacotar import NOME, RAIZ, gerar_icone, remover_dados_usuario

# Fixo entre versões: é o que permite ao Windows Installer saber que duas
# versões são o "mesmo" produto e fazer upgrade em vez de instalar em paralelo.
# Não troque isto depois de publicado.
UPGRADE_CODE = "5887D8AE-339F-4C20-B36C-215E814004A1"

# Acompanha a tag do app. A Store guarda cada versão numa URL própria
# (.../downloads/1.0.0/...), então incremente aqui a cada envio novo.
VERSAO = "1.0.0"
FABRICANTE = "Estúdio Fanara"

DIST = os.path.join(RAIZ, "dist")
BUILD = os.path.join(RAIZ, "build", "msi")

WXS = r"""<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="{nome}"
           Manufacturer="{fabricante}"
           Version="{versao}"
           UpgradeCode="{upgrade_code}"
           Language="1046"
           InstallerVersion="500">

    <SummaryInformation Manufacturer="{fabricante}" Description="Instalador do {nome}" />

    <MajorUpgrade DowngradeErrorMessage="Uma versão mais nova do {nome} já está instalada." />
    <MediaTemplate EmbedCab="yes" />

    <Icon Id="AppIcon" SourceFile="{icone}" />
    <Property Id="ARPPRODUCTICON" Value="AppIcon" />
    <Property Id="ARPHELPLINK" Value="https://fanara.com.br" />
    <Property Id="ARPNOMODIFY" Value="1" />

    <StandardDirectory Id="ProgramFiles64Folder">
      <Directory Id="INSTALLFOLDER" Name="{nome}" />
    </StandardDirectory>
    <StandardDirectory Id="ProgramMenuFolder">
      <Directory Id="AppMenuFolder" Name="{nome}" />
    </StandardDirectory>

    <ComponentGroup Id="AppFiles" Directory="INSTALLFOLDER">
      <Files Include="{origem}\**" />
    </ComponentGroup>

    <Component Id="AppShortcut" Directory="AppMenuFolder" Guid="*">
      <Shortcut Id="StartMenuShortcut"
                Name="{nome}"
                Target="[INSTALLFOLDER]{nome}.exe"
                WorkingDirectory="INSTALLFOLDER"
                Icon="AppIcon" />
      <RemoveFolder Id="RemoveAppMenuFolder" On="uninstall" />
      <RegistryValue Root="HKCU"
                      Key="Software\{fabricante_reg}\{nome}"
                      Name="instalado"
                      Type="integer"
                      Value="1"
                      KeyPath="yes" />
    </Component>

    <Feature Id="Principal" Title="{nome}" Level="1">
      <ComponentGroupRef Id="AppFiles" />
      <ComponentRef Id="AppShortcut" />
    </Feature>

  </Package>
</Wix>
"""


def ferramenta() -> str:
    # A v7 em diante exige aceitar a EULA da Open Source Maintenance Fee antes de
    # compilar; a v6 e a v5 são MIT puro. Pega a mais nova entre as livres.
    candidatos = [caminho
                  for caminho in glob.glob(r"C:\Program Files\WiX Toolset v*\bin\wix.exe")
                  if int(re.search(r"Toolset v(\d+)", caminho).group(1)) < 7]
    if not candidatos:
        raise SystemExit(
            "wix.exe (v5 ou v6) não encontrado. Instale o WiX Toolset:\n"
            "  winget install WiXToolset.WiXCLI --version 6.0.2.0")
    return sorted(candidatos)[-1]


def main() -> int:
    if sys.platform != "win32":
        print("Este empacotador gera somente o instalador Windows; execute-o no Windows.")
        return 1

    origem = os.path.join(DIST, NOME)
    if not os.path.isfile(os.path.join(origem, f"{NOME}.exe")):
        print("dist ainda não existe — rodando empacotar.py…")
        if subprocess.run([sys.executable, os.path.join(RAIZ, "empacotar.py")],
                          cwd=RAIZ).returncode != 0:
            raise SystemExit("empacotar.py falhou.")

    remover_dados_usuario(origem)

    icone = os.path.join(RAIZ, "assets", "icone.ico")
    if not os.path.isfile(icone):
        gerar_icone()

    shutil.rmtree(BUILD, ignore_errors=True)
    os.makedirs(BUILD)
    wxs_path = os.path.join(BUILD, "produto.wxs")
    with open(wxs_path, "w", encoding="utf-8") as arquivo:
        arquivo.write(WXS.format(
            nome=NOME, fabricante=FABRICANTE, fabricante_reg=FABRICANTE.replace(" ", ""),
            versao=VERSAO, upgrade_code=UPGRADE_CODE, icone=icone, origem=origem))

    destino = os.path.join(DIST, f"{NOME}-Setup-{VERSAO}.msi")
    comando = [ferramenta(), "build", wxs_path, "-arch", "x64",
               "-culture", "pt-BR", "-o", destino]
    print("Compilando o instalador…")
    resultado = subprocess.run(comando, cwd=RAIZ)
    if resultado.returncode != 0:
        return resultado.returncode

    print(f"\nInstalador: {destino}  ({os.path.getsize(destino) / 1e6:.0f} MB)")
    print("\nTestar aqui:")
    print(f'  msiexec /i "{destino}"')
    print(f'  msiexec /i "{destino}" /quiet     (silencioso, o mesmo que a Store usa)')
    print(f'  msiexec /x "{destino}" /quiet     (desinstalar)')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
