#!/bin/bash
# Atalho do macOS: dê duplo-clique no Finder.
# Na primeira vez pode ser preciso liberar a execução:  chmod +x "Provas.command"
cd "$(dirname "$0")" || exit 1
exec python3 "Provas.pyw"
