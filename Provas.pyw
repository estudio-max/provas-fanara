"""Abre a janela do Provas. Serve nos três sistemas."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from provas.app import principal

if __name__ == "__main__":
    principal()
