# -*- coding: utf-8 -*-
"""Pestanya 5: comparar dues versions d'un tema (test d'anul·lació)."""
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ..compare import compare_files
from ..reports import compare_report
from . import dnd
from . import theme as th
from .common import ReportView, ProgressBar


class CompareTab(tk.Frame):
    def __init__(self, master, app):
        tk.Frame.__init__(self, master, bg=th.BG)
        self.app = app
        self.result = None
        box = tk.Frame(self, bg=th.PANEL, highlightthickness=1, highlightbackground=th.BORDER)
        box.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(box, text="COMPARAR DUES VERSIONS (per exemple, màster de vinil i màster de CD)", bg=th.PANEL,
                 fg=th.NAVY, font=th.FONTS["bold"]).grid(row=0, column=0, columnspan=5, sticky="w", padx=10,
                                                          pady=(8, 4))
        self.vars = {}
        for r, (key, default) in enumerate((("A", "Vinilo"), ("B", "CD")), start=1):
            path = tk.StringVar()
            name = tk.StringVar(value=default)
            self.vars[key] = (path, name)
            tk.Label(box, text="Versió %s" % key, bg=th.PANEL, font=th.FONTS["bold"]).grid(row=r, column=0, padx=10,
                                                                                          sticky="w")
            e = ttk.Entry(box, textvariable=path, width=80)
            e.grid(row=r, column=1, sticky="we", pady=3)
            dnd.register_files_drop(e, lambda paths, _y=None, v=path: v.set(paths[0]) if paths else None)
            ttk.Button(box, text="Triar…", command=lambda v=path: self.choose(v)).grid(row=r, column=2, padx=6)
            tk.Label(box, text="Nom a l'informe", bg=th.PANEL).grid(row=r, column=3, sticky="e")
            ttk.Entry(box, textvariable=name, width=14).grid(row=r, column=4, padx=(4, 10), sticky="w")
        box.grid_columnconfigure(1, weight=1)
        bar = tk.Frame(box, bg=th.PANEL)
        bar.grid(row=3, column=0, columnspan=5, sticky="w", padx=10, pady=(4, 10))
        self.btn = ttk.Button(bar, text="Comparar ▶", style="Accent.TButton", command=self.run)
        self.btn.pack(side="left")
        ttk.Button(bar, text="Exportar informe (PDF)…", command=lambda: app.export_pdf("compare")).pack(
            side="left", padx=8)
        self.progress = ProgressBar(bar)
        self.progress.pack(side="left", padx=10)
        self.view = ReportView(self, "Tria dos WAV i clica «Comparar».\nEs mesuren tots dos i es fa un test "
                                     "d'anul·lació per saber si són el mateix màster.")
        self.view.pack(fill="both", expand=True, padx=10, pady=(4, 10))

    def choose(self, var):
        p = filedialog.askopenfilename(parent=self, title="Triar WAV", initialdir=self.app.cfg.get("last_dir") or None,
                                       filetypes=[("Fitxers WAV", "*.wav *.WAV *.wave *.bwf"), ("Tots", "*.*")])
        if p:
            var.set(p)

    def run(self):
        pa, na = self.vars["A"]
        pb, nb = self.vars["B"]
        a, b = pa.get().strip(), pb.get().strip()
        if not (os.path.isfile(a) and os.path.isfile(b)):
            messagebox.showwarning("VinylPremaster", "Tria dos fitxers WAV que existeixin.", parent=self)
            return
        if self.app.worker.busy:
            return
        self.btn.state(["disabled"])
        self.progress.show()
        self.progress.update_progress(0, 1, "Mesurant i comparant…")

        def fn(progress, cancelled):
            return compare_files(a, b, na.get().strip() or "Versión A", nb.get().strip() or "Versión B")

        def done(res):
            self.btn.state(["!disabled"])
            self.progress.hide("Fet.")
            self.result = res
            self.view.set(compare_report.layout, res)

        def err(exc, tb):
            self.btn.state(["!disabled"])
            self.progress.hide("")
            self.app.report_error("No s'ha pogut comparar", exc, tb)

        self.app.worker.run(fn, lambda *a: None, done, err)
