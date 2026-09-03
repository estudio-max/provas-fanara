"""Janela do Provas."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import asdict
from datetime import date
from tkinter import colorchooser, filedialog, messagebox, ttk

from . import motor, tema

TITULO = "Provas"

def _gravavel(pasta: str) -> bool:
    """Grava um arquivo de teste. No Windows o os.access mente sobre pastas."""
    teste = os.path.join(pasta, ".provas-escrita")
    try:
        with open(teste, "w"):
            pass
        os.remove(teste)
        return True
    except OSError:
        return False


def _pasta_gravavel() -> str:
    """Onde as preferências podem ser gravadas.

    Empacotado, o código roda de uma pasta temporária que o sistema apaga. No
    Windows as preferências ficam junto do executável; no macOS não podem ficar,
    porque ali é o interior do .app — vão para Application Support, como manda o
    sistema. Instalado pela Store (MSIX) ou em Arquivos de Programas, a pasta do
    executável também é somente leitura: aí vão para LOCALAPPDATA.
    """
    if not getattr(sys, "frozen", False):
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if sys.platform == "darwin":
        pasta = os.path.expanduser("~/Library/Application Support/Provas")
        try:
            os.makedirs(pasta, exist_ok=True)
            return pasta
        except OSError:
            return os.path.expanduser("~")
    pasta = os.path.dirname(sys.executable)
    if _gravavel(pasta):
        return pasta
    destino = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Provas")
    try:
        os.makedirs(destino, exist_ok=True)
        return destino
    except OSError:
        return os.path.expanduser("~")


def _pasta_recursos() -> str:
    """De onde os arquivos embutidos (logotipo padrão) são lidos."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


ARQUIVO_CONFIG = os.path.join(_pasta_gravavel(), "config.json")
LOGO_PADRAO = os.path.join(_pasta_recursos(), "assets", "logo.png")

FUNDO = "#16161a"
PAINEL = "#1e1e24"
CAMPO = "#26262e"
TEXTO = "#ecedf0"
APAGADO = "#8b8b96"
ROSA = "#d84060"

OPCOES_POR_PAGINA = [1, 2, 3, 4, 6, 8, 9, 12, 15, 16, 20]
OPCOES_QUALIDADE = [("Leve — arquivo menor", "leve"),
                    ("Normal — recomendado", "normal"),
                    ("Alta — impressão", "alta")]
PRESETS_COR = [("Grafite", "#16161A"), ("Preto", "#000000"),
               ("Papel", "#F4F2EE"), ("Branco", "#FFFFFF")]
OPCOES_CAPA = [("Mosaico — todas as fotos", "mosaico"),
               ("Losango — malha de diamantes", "losango"),
               ("Destaque — losango central", "destaque")]


class Janela(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(TITULO)
        self.configure(bg=FUNDO)
        self.minsize(660, 640)
        self.resizable(True, True)

        self.fila: queue.Queue = queue.Queue()
        self.cancelar = threading.Event()
        self.trabalho: threading.Thread | None = None
        self.ultimo_pdf = ""

        self._variaveis()
        self._estilo()
        self._montar()
        self._carregar_config()
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.after(80, self._drenar_fila)

    # --- estado ----------------------------------------------------------
    def _variaveis(self) -> None:
        self.v_pasta = tk.StringVar()
        self.v_saida = tk.StringVar()
        self.v_titulo = tk.StringVar()
        self.v_subtitulo = tk.StringVar(value=date.today().strftime("%d.%m.%Y"))
        self.v_chamada = tk.StringVar(value="Escolha suas favoritas")
        self.v_por_pagina = tk.IntVar(value=4)
        self.v_qualidade = tk.StringVar(value="Normal — recomendado")
        self.v_paisagem = tk.BooleanVar(value=False)
        self.v_girar = tk.BooleanVar(value=True)
        self.v_capa = tk.BooleanVar(value=True)
        self.v_estilo_capa = tk.StringVar(value="Mosaico — todas as fotos")
        self.v_recursivo = tk.BooleanVar(value=False)
        self.v_marca = tk.BooleanVar(value=True)
        self.v_codigos = tk.BooleanVar(value=True)
        self.v_logo = tk.StringVar(value=LOGO_PADRAO if os.path.exists(LOGO_PADRAO) else "")
        self.v_estudio = tk.StringVar()
        self.v_site = tk.StringVar()
        self.v_cor_fundo = tk.StringVar(value=tema.FUNDO_PADRAO)
        self.v_opacidade = tk.IntVar(value=20)
        self.v_tamanho_marca = tk.IntVar(value=62)
        self.v_status = tk.StringVar(value="Escolha a pasta da sessão.")

    def _estilo(self) -> None:
        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure(".", background=FUNDO, foreground=TEXTO,
                         fieldbackground=CAMPO, borderwidth=0)
        estilo.configure("TLabel", background=FUNDO, foreground=TEXTO, font=("Segoe UI", 9))
        estilo.configure("Fraco.TLabel", foreground=APAGADO, font=("Segoe UI", 8))
        estilo.configure("Secao.TLabel", foreground=ROSA, font=("Segoe UI Semibold", 8))
        estilo.configure("Titulo.TLabel", foreground=TEXTO, font=("Segoe UI Light", 20))
        estilo.configure("TEntry", fieldbackground=CAMPO, foreground=TEXTO,
                         insertcolor=TEXTO, bordercolor=CAMPO, lightcolor=CAMPO,
                         darkcolor=CAMPO, padding=5)
        estilo.configure("TCheckbutton", background=FUNDO, foreground=TEXTO,
                         font=("Segoe UI", 9), focuscolor=FUNDO)
        estilo.map("TCheckbutton", background=[("active", FUNDO)],
                   indicatorcolor=[("selected", ROSA), ("!selected", CAMPO)])
        estilo.configure("TCombobox", fieldbackground=CAMPO, background=CAMPO,
                         foreground=TEXTO, arrowcolor=APAGADO, padding=4)
        estilo.configure("TButton", background=CAMPO, foreground=TEXTO,
                         font=("Segoe UI", 9), padding=(12, 6))
        estilo.map("TButton", background=[("active", "#33333d"), ("disabled", "#202027")],
                   foreground=[("disabled", "#5a5a63")])
        estilo.configure("Acao.TButton", background=ROSA, foreground="#ffffff",
                         font=("Segoe UI Semibold", 9), padding=(18, 8))
        estilo.map("Acao.TButton", background=[("active", "#e8577a"), ("disabled", "#4a2a33")],
                   foreground=[("disabled", "#9a8189")])
        estilo.configure("TProgressbar", background=ROSA, troughcolor=CAMPO,
                         bordercolor=FUNDO, lightcolor=ROSA, darkcolor=ROSA)
        estilo.configure("TScale", background=FUNDO, troughcolor=CAMPO)
        estilo.configure("TSeparator", background="#2c2c34")

    # --- construção da tela ----------------------------------------------
    def _montar(self) -> None:
        raiz = ttk.Frame(self, padding=(22, 18, 22, 16))
        raiz.pack(fill="both", expand=True)
        raiz.columnconfigure(0, weight=1)

        cabecalho = ttk.Frame(raiz)
        cabecalho.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ttk.Label(cabecalho, text=TITULO, style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(cabecalho, text="PDF de seleção a partir da pasta do ensaio",
                  style="Fraco.TLabel").pack(anchor="w")

        linha = 1
        linha = self._secao(raiz, linha, "SESSÃO")
        linha = self._campo_pasta(raiz, linha)
        linha = self._campo_texto(raiz, linha, "Título", self.v_titulo,
                                  "em branco usa o nome da pasta")
        linha = self._par_texto(raiz, linha, "Data", self.v_subtitulo,
                                "Chamada da capa", self.v_chamada)

        linha = self._secao(raiz, linha, "DIAGRAMAÇÃO")
        linha = self._linha_diagramacao(raiz, linha)
        linha = self._linha_capa(raiz, linha)
        linha = self._linha_cor(raiz, linha)
        linha = self._linha_opcoes(raiz, linha)

        linha = self._secao(raiz, linha, "ESTÚDIO E MARCA D'ÁGUA")
        linha = self._campo_texto(raiz, linha, "Nome do estúdio", self.v_estudio,
                                  "aparece no topo quando não há logotipo")
        linha = self._campo_texto(raiz, linha, "Site", self.v_site,
                                  "vai no rodapé de todas as páginas")
        linha = self._campo_logo(raiz, linha)
        linha = self._linha_marca(raiz, linha)
        self._atualizar_marca()

        linha = self._secao(raiz, linha, "SAÍDA")
        linha = self._campo_saida(raiz, linha)

        raiz.rowconfigure(linha, weight=1)
        linha += 1

        rodape = ttk.Frame(raiz)
        rodape.grid(row=linha, column=0, sticky="ew", pady=(14, 0))
        rodape.columnconfigure(0, weight=1)

        self.barra = ttk.Progressbar(rodape, mode="determinate", maximum=100)
        self.barra.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 6))
        ttk.Label(rodape, textvariable=self.v_status, style="Fraco.TLabel").grid(
            row=1, column=0, sticky="w")

        self.botao_abrir = ttk.Button(rodape, text="Abrir PDF", command=self._abrir_pdf,
                                      state="disabled")
        self.botao_abrir.grid(row=1, column=1, padx=(8, 0))
        self.botao_amostra = ttk.Button(rodape, text="Amostra (12 fotos)",
                                        command=lambda: self._iniciar(amostra=True))
        self.botao_amostra.grid(row=1, column=2, padx=(8, 0))
        self.botao_gerar = ttk.Button(rodape, text="Gerar PDF", style="Acao.TButton",
                                      command=lambda: self._iniciar(amostra=False))
        self.botao_gerar.grid(row=1, column=3, padx=(8, 0))

    def _secao(self, pai, linha: int, texto: str) -> int:
        quadro = ttk.Frame(pai)
        quadro.grid(row=linha, column=0, sticky="ew", pady=(12, 6))
        quadro.columnconfigure(1, weight=1)
        ttk.Label(quadro, text=texto, style="Secao.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Separator(quadro, orient="horizontal").grid(row=0, column=1, sticky="ew", padx=(10, 0))
        return linha + 1

    def _campo_pasta(self, pai, linha: int) -> int:
        quadro = ttk.Frame(pai)
        quadro.grid(row=linha, column=0, sticky="ew", pady=2)
        quadro.columnconfigure(1, weight=1)
        ttk.Label(quadro, text="Pasta", width=16).grid(row=0, column=0, sticky="w")
        ttk.Entry(quadro, textvariable=self.v_pasta).grid(row=0, column=1, sticky="ew")
        ttk.Button(quadro, text="Escolher…", command=self._escolher_pasta).grid(
            row=0, column=2, padx=(8, 0))
        return linha + 1

    def _campo_texto(self, pai, linha: int, rotulo: str, variavel, dica: str) -> int:
        quadro = ttk.Frame(pai)
        quadro.grid(row=linha, column=0, sticky="ew", pady=2)
        quadro.columnconfigure(1, weight=1)
        ttk.Label(quadro, text=rotulo, width=16).grid(row=0, column=0, sticky="w")
        ttk.Entry(quadro, textvariable=variavel).grid(row=0, column=1, sticky="ew")
        ttk.Label(quadro, text=dica, style="Fraco.TLabel").grid(row=0, column=2, padx=(8, 0))
        return linha + 1

    def _par_texto(self, pai, linha: int, rot1: str, var1, rot2: str, var2) -> int:
        quadro = ttk.Frame(pai)
        quadro.grid(row=linha, column=0, sticky="ew", pady=2)
        quadro.columnconfigure(1, weight=1)
        quadro.columnconfigure(3, weight=2)
        ttk.Label(quadro, text=rot1, width=16).grid(row=0, column=0, sticky="w")
        ttk.Entry(quadro, textvariable=var1, width=14).grid(row=0, column=1, sticky="w")
        ttk.Label(quadro, text=rot2).grid(row=0, column=2, sticky="e", padx=(16, 8))
        ttk.Entry(quadro, textvariable=var2).grid(row=0, column=3, sticky="ew")
        return linha + 1

    def _linha_diagramacao(self, pai, linha: int) -> int:
        quadro = ttk.Frame(pai)
        quadro.grid(row=linha, column=0, sticky="ew", pady=2)
        ttk.Label(quadro, text="Fotos por página", width=16).grid(row=0, column=0, sticky="w")
        combo = ttk.Combobox(quadro, values=[str(n) for n in OPCOES_POR_PAGINA],
                             state="readonly", width=5)
        combo.set(str(self.v_por_pagina.get()))
        combo.bind("<<ComboboxSelected>>",
                   lambda _e: self.v_por_pagina.set(int(combo.get())))
        combo.grid(row=0, column=1, sticky="w")
        self.combo_por_pagina = combo

        ttk.Label(quadro, text="Qualidade").grid(row=0, column=2, padx=(20, 8))
        combo_q = ttk.Combobox(quadro, values=[r for r, _ in OPCOES_QUALIDADE],
                               state="readonly", width=22, textvariable=self.v_qualidade)
        combo_q.grid(row=0, column=3, sticky="w")
        return linha + 1

    def _linha_capa(self, pai, linha: int) -> int:
        quadro = ttk.Frame(pai)
        quadro.grid(row=linha, column=0, sticky="ew", pady=2)
        ttk.Label(quadro, text="Capa", width=16).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(quadro, text="Gerar", variable=self.v_capa,
                        command=self._atualizar_marca).grid(row=0, column=1, sticky="w")
        self.combo_capa = ttk.Combobox(quadro, values=[r for r, _ in OPCOES_CAPA],
                                       state="readonly", width=28,
                                       textvariable=self.v_estilo_capa)
        self.combo_capa.grid(row=0, column=2, sticky="w", padx=(12, 0))
        return linha + 1

    def _linha_cor(self, pai, linha: int) -> int:
        quadro = ttk.Frame(pai)
        quadro.grid(row=linha, column=0, sticky="ew", pady=2)
        ttk.Label(quadro, text="Cor de fundo", width=16).grid(row=0, column=0, sticky="w")

        self.amostra_cor = tk.Label(quadro, width=6, relief="flat", bd=0, text=" ")
        self.amostra_cor.grid(row=0, column=1, sticky="w", ipady=6)
        ttk.Button(quadro, text="Escolher…", command=self._escolher_cor).grid(
            row=0, column=2, padx=(8, 0))

        for coluna, (nome, valor) in enumerate(PRESETS_COR):
            ttk.Button(quadro, text=nome, width=9,
                       command=lambda v=valor: self._definir_cor(v)).grid(
                row=0, column=coluna + 3, padx=(6, 0))
        self._definir_cor(self.v_cor_fundo.get())
        return linha + 1

    def _definir_cor(self, valor: str) -> None:
        cor = tema.escrever_hex(tema.ler_hex(valor))
        self.v_cor_fundo.set(cor)
        clara = tema.paleta(cor).claro
        self.amostra_cor.configure(bg=cor, fg="#000000" if clara else "#ffffff", text=cor)

    def _escolher_cor(self) -> None:
        _, escolhida = colorchooser.askcolor(
            color=self.v_cor_fundo.get(), title="Cor de fundo do PDF", parent=self)
        if escolhida:
            self._definir_cor(escolhida)

    def _linha_opcoes(self, pai, linha: int) -> int:
        quadro = ttk.Frame(pai)
        quadro.grid(row=linha, column=0, sticky="ew", pady=(6, 2))
        ttk.Label(quadro, text="", width=16).grid(row=0, column=0)
        for coluna, (texto, variavel) in enumerate((
                ("Códigos sob as fotos", self.v_codigos),
                ("Girar horizontais", self.v_girar),
                ("A4 deitado", self.v_paisagem),
                ("Incluir subpastas", self.v_recursivo))):
            ttk.Checkbutton(quadro, text=texto, variable=variavel).grid(
                row=0, column=coluna + 1, sticky="w", padx=(0, 16))
        return linha + 1

    def _campo_logo(self, pai, linha: int) -> int:
        quadro = ttk.Frame(pai)
        quadro.grid(row=linha, column=0, sticky="ew", pady=2)
        quadro.columnconfigure(2, weight=1)
        ttk.Checkbutton(quadro, text="Aplicar", variable=self.v_marca,
                        command=self._atualizar_marca).grid(row=0, column=0, sticky="w")
        ttk.Label(quadro, text="Logotipo").grid(row=0, column=1, sticky="w", padx=(12, 8))
        self.campo_logo = ttk.Entry(quadro, textvariable=self.v_logo)
        self.campo_logo.grid(row=0, column=2, sticky="ew")
        self.botao_logo = ttk.Button(quadro, text="Escolher…", command=self._escolher_logo)
        self.botao_logo.grid(row=0, column=3, padx=(8, 0))
        return linha + 1

    def _atualizar_marca(self) -> None:
        """Liga e desliga os controles que só valem quando a opção está ativa."""
        estado = "normal" if self.v_marca.get() else "disabled"
        for widget in (self.campo_logo, self.botao_logo,
                       getattr(self, "escala_opacidade", None),
                       getattr(self, "escala_tamanho", None)):
            if widget is not None:
                widget.configure(state=estado)
        if hasattr(self, "combo_capa"):
            self.combo_capa.configure(state="readonly" if self.v_capa.get() else "disabled")

    def _linha_marca(self, pai, linha: int) -> int:
        quadro = ttk.Frame(pai)
        quadro.grid(row=linha, column=0, sticky="ew", pady=2)
        quadro.columnconfigure(1, weight=1)
        quadro.columnconfigure(4, weight=1)

        ttk.Label(quadro, text="Opacidade", width=16).grid(row=0, column=0, sticky="w")
        self.escala_opacidade = ttk.Scale(
            quadro, from_=3, to=45, variable=self.v_opacidade,
            command=lambda v: self.v_opacidade.set(round(float(v))))
        self.escala_opacidade.grid(row=0, column=1, sticky="ew")
        rotulo_o = ttk.Label(quadro, text="", style="Fraco.TLabel", width=5)
        rotulo_o.grid(row=0, column=2, padx=(6, 18))

        ttk.Label(quadro, text="Tamanho").grid(row=0, column=3, padx=(0, 8))
        self.escala_tamanho = ttk.Scale(
            quadro, from_=25, to=90, variable=self.v_tamanho_marca,
            command=lambda v: self.v_tamanho_marca.set(round(float(v))))
        self.escala_tamanho.grid(row=0, column=4, sticky="ew")
        rotulo_t = ttk.Label(quadro, text="", style="Fraco.TLabel", width=5)
        rotulo_t.grid(row=0, column=5, padx=(6, 0))

        def sincronizar(*_):
            rotulo_o.config(text=f"{self.v_opacidade.get()}%")
            rotulo_t.config(text=f"{self.v_tamanho_marca.get()}%")

        self.v_opacidade.trace_add("write", sincronizar)
        self.v_tamanho_marca.trace_add("write", sincronizar)
        sincronizar()
        return linha + 1

    def _campo_saida(self, pai, linha: int) -> int:
        quadro = ttk.Frame(pai)
        quadro.grid(row=linha, column=0, sticky="ew", pady=2)
        quadro.columnconfigure(1, weight=1)
        ttk.Label(quadro, text="Arquivo PDF", width=16).grid(row=0, column=0, sticky="w")
        ttk.Entry(quadro, textvariable=self.v_saida).grid(row=0, column=1, sticky="ew")
        ttk.Button(quadro, text="Escolher…", command=self._escolher_saida).grid(
            row=0, column=2, padx=(8, 0))
        return linha + 1

    # --- ações -----------------------------------------------------------
    def _escolher_pasta(self) -> None:
        inicial = self.v_pasta.get() or os.path.expanduser("~")
        pasta = filedialog.askdirectory(title="Pasta do ensaio", initialdir=inicial)
        if not pasta:
            return
        pasta = os.path.normpath(pasta)
        self.v_pasta.set(pasta)
        nome = os.path.basename(pasta)
        if not self.v_titulo.get().strip():
            self.v_titulo.set(nome)
        self.v_saida.set(os.path.join(pasta, f"{nome} - provas.pdf"))
        self.v_status.set(f"Pasta escolhida: {nome}")

    def _escolher_logo(self) -> None:
        caminho = filedialog.askopenfilename(
            title="Logotipo", filetypes=[("Imagens", "*.png *.jpg *.jpeg"), ("Todos", "*.*")])
        if caminho:
            self.v_logo.set(os.path.normpath(caminho))

    def _escolher_saida(self) -> None:
        caminho = filedialog.asksaveasfilename(
            title="Salvar PDF", defaultextension=".pdf",
            initialfile=os.path.basename(self.v_saida.get() or "provas.pdf"),
            initialdir=os.path.dirname(self.v_saida.get() or self.v_pasta.get() or ""),
            filetypes=[("PDF", "*.pdf")])
        if caminho:
            self.v_saida.set(os.path.normpath(caminho))

    def _abrir_pdf(self) -> None:
        if not self.ultimo_pdf or not os.path.exists(self.ultimo_pdf):
            return
        if sys.platform == "win32":
            os.startfile(self.ultimo_pdf)          # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.ultimo_pdf])
        else:
            subprocess.Popen(["xdg-open", self.ultimo_pdf])

    def _config_atual(self, amostra: bool) -> motor.Config:
        qualidade = dict(OPCOES_QUALIDADE).get(self.v_qualidade.get(), "normal")
        saida = self.v_saida.get().strip()
        if amostra and saida:
            base, ext = os.path.splitext(saida)
            saida = f"{base} (amostra){ext}"
        return motor.Config(
            pasta=self.v_pasta.get().strip(),
            saida=saida,
            titulo=self.v_titulo.get().strip(),
            subtitulo=self.v_subtitulo.get().strip(),
            por_pagina=self.v_por_pagina.get(),
            paisagem=self.v_paisagem.get(),
            girar_horizontais=self.v_girar.get(),
            qualidade=qualidade,
            marca_opacidade=self.v_opacidade.get() / 100,
            marca_largura=self.v_tamanho_marca.get() / 100,
            logo=self.v_logo.get().strip(),
            estudio=self.v_estudio.get().strip(),
            site=self.v_site.get().strip(),
            cor_fundo=self.v_cor_fundo.get(),
            recursivo=self.v_recursivo.get(),
            capa_mosaico=self.v_capa.get(),
            estilo_capa=dict(OPCOES_CAPA).get(self.v_estilo_capa.get(), "mosaico"),
            marca_dagua=self.v_marca.get(),
            mostrar_codigos=self.v_codigos.get(),
            chamada=self.v_chamada.get().strip(),
            limite=12 if amostra else 0,
        )

    def _iniciar(self, amostra: bool) -> None:
        if self.trabalho and self.trabalho.is_alive():
            self.cancelar.set()
            self.v_status.set("Cancelando…")
            return
        pasta = self.v_pasta.get().strip()
        if not pasta or not os.path.isdir(pasta):
            messagebox.showwarning(TITULO, "Escolha uma pasta de ensaio válida.")
            return

        logo = self.v_logo.get().strip()
        if self.v_marca.get() and not (logo and os.path.exists(logo)):
            if not messagebox.askokcancel(
                    TITULO,
                    "A marca d'água está ligada, mas nenhum logotipo válido foi escolhido.\n\n"
                    "Gerar o PDF sem marca d'água?"):
                return

        self._salvar_config()
        config = self._config_atual(amostra)
        self.cancelar = threading.Event()
        self.barra.config(value=0)
        self.botao_abrir.config(state="disabled")
        self.botao_amostra.config(state="disabled")
        self.botao_gerar.config(text="Cancelar")

        def tarefa():
            try:
                resultado = motor.gerar(
                    config,
                    progresso=lambda f, t, m: self.fila.put(("progresso", (f, t, m))),
                    cancelar=self.cancelar)
                self.fila.put(("fim", resultado))
            except motor.Cancelado:
                self.fila.put(("cancelado", None))
            except Exception as erro:                       # erro vai para a tela
                self.fila.put(("erro", str(erro)))

        self.trabalho = threading.Thread(target=tarefa, daemon=True)
        self.trabalho.start()

    def _drenar_fila(self) -> None:
        try:
            while True:
                tipo, carga = self.fila.get_nowait()
                if tipo == "progresso":
                    feito, total, mensagem = carga
                    self.barra.config(value=100 * feito / max(1, total))
                    self.v_status.set(mensagem)
                elif tipo == "fim":
                    self._concluir(carga)
                elif tipo == "cancelado":
                    self._liberar("Cancelado.")
                elif tipo == "erro":
                    self._liberar("Não deu certo.")
                    messagebox.showerror(TITULO, carga)
        except queue.Empty:
            pass
        self.after(80, self._drenar_fila)

    def _concluir(self, resultado: motor.Resultado) -> None:
        self.ultimo_pdf = resultado.saida
        self.botao_abrir.config(state="normal")
        recado = f"{resultado.fotos} fotos em {resultado.paginas} páginas."
        if resultado.falhas:
            recado += f" {len(resultado.falhas)} arquivo(s) ignorado(s)."
        self._liberar(recado)
        if resultado.falhas:
            detalhe = "\n".join(f"• {nome}: {erro}" for nome, erro in resultado.falhas[:12])
            messagebox.showwarning("Arquivos ignorados", detalhe)

    def _liberar(self, mensagem: str) -> None:
        self.barra.config(value=100 if "fotos" in mensagem else 0)
        self.v_status.set(mensagem)
        self.botao_gerar.config(text="Gerar PDF")
        self.botao_amostra.config(state="normal")

    # --- persistência ----------------------------------------------------
    def _salvar_config(self) -> None:
        dados = asdict(self._config_atual(amostra=False))
        dados.pop("limite", None)
        dados.pop("saida", None)
        try:
            with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as arquivo:
                json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _carregar_config(self) -> None:
        try:
            with open(ARQUIVO_CONFIG, encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
        except (OSError, ValueError):
            return
        self.v_por_pagina.set(dados.get("por_pagina", 4))
        self.combo_por_pagina.set(str(self.v_por_pagina.get()))
        self.v_paisagem.set(dados.get("paisagem", False))
        self.v_girar.set(dados.get("girar_horizontais", True))
        self.v_capa.set(dados.get("capa_mosaico", True))
        self.v_recursivo.set(dados.get("recursivo", False))
        self.v_marca.set(dados.get("marca_dagua", True))
        self.v_codigos.set(dados.get("mostrar_codigos", True))
        for rotulo, chave in OPCOES_CAPA:
            if chave == dados.get("estilo_capa"):
                self.v_estilo_capa.set(rotulo)
        self.v_chamada.set(dados.get("chamada", self.v_chamada.get()))
        self.v_opacidade.set(round(dados.get("marca_opacidade", 0.20) * 100))
        self.v_tamanho_marca.set(round(dados.get("marca_largura", 0.62) * 100))
        if dados.get("logo"):
            self.v_logo.set(dados["logo"])
        self.v_estudio.set(dados.get("estudio", ""))
        self.v_site.set(dados.get("site", ""))
        self._definir_cor(dados.get("cor_fundo", tema.FUNDO_PADRAO))
        for rotulo, chave in OPCOES_QUALIDADE:
            if chave == dados.get("qualidade"):
                self.v_qualidade.set(rotulo)
        self._atualizar_marca()

    def _fechar(self) -> None:
        self.cancelar.set()
        self._salvar_config()
        self.destroy()


def principal() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    Janela().mainloop()
