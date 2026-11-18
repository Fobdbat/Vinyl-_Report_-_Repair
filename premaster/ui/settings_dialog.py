# -*- coding: utf-8 -*-
"""Diàleg de llindars i objectius."""
import tkinter as tk
from tkinter import ttk, messagebox

from ..analysis import DEFAULT_LIMITS
from . import theme as th

FIELDS = [
    ("Pic real (dBTP)", "tp_red", "tp_yellow", "per sobre"),
    ("Loudness integrat (LUFS)", "lufs_red", "lufs_yellow", "per sobre"),
    ("Crest (dB)", "crest_red", "crest_yellow", "per sota"),
    ("Correlació L/R < 150 Hz", "corr_red", "corr_yellow", "per sota"),
    ("Side/Mid < 150 Hz (dB)", "sm_red", "sm_yellow", "per sobre"),
    ("Sibilància 5-9 kHz (dB)", "sib_red", "sib_yellow", "per sobre"),
]
TARGETS = [
    ("Zona interior de la cara (fracció)", "inner_zone"),
    ("Objectiu de headroom (dBTP)", "tp_target"),
    ("Objectiu del de-esser (dB)", "deess_target"),
    ("Tall del mono en graves (Hz)", "bass_fc"),
]


def _s(v):
    return ("%g" % v).replace(".", ",")


class SettingsDialog(tk.Toplevel):
    def __init__(self, app):
        tk.Toplevel.__init__(self, app.root)
        self.app = app
        self.result = False
        self.title("Llindars i objectius")
        self.configure(bg=th.BG)
        self.resizable(False, False)
        self.transient(app.root)
        f = tk.Frame(self, bg=th.BG)
        f.pack(padx=16, pady=12)
        L = app.cfg["limits"]
        self.vars = {}
        tk.Label(f, text="Mesura", bg=th.BG, font=th.FONTS["bold"]).grid(row=0, column=0, sticky="w")
        tk.Label(f, text="Problema (vermell)", bg=th.BG, fg=th.RED, font=th.FONTS["bold"]).grid(row=0, column=1, padx=8)
        tk.Label(f, text="A vigilar (groc)", bg=th.BG, fg=th.YELLOW_TEXT, font=th.FONTS["bold"]).grid(row=0, column=2,
                                                                                                    padx=8)
        for r, (label, kr, ky, sense) in enumerate(FIELDS, start=1):
            tk.Label(f, text="%s — %s" % (label, sense), bg=th.BG).grid(row=r, column=0, sticky="w", pady=2)
            for c, k in ((1, kr), (2, ky)):
                v = tk.StringVar(value=_s(L[k]))
                ttk.Entry(f, textvariable=v, width=8, justify="right").grid(row=r, column=c)
                self.vars[k] = v
        r = len(FIELDS) + 1
        ttk.Separator(f).grid(row=r, column=0, columnspan=3, sticky="ew", pady=10)
        for i, (label, k) in enumerate(TARGETS, start=r + 1):
            tk.Label(f, text=label, bg=th.BG).grid(row=i, column=0, sticky="w", pady=2)
            v = tk.StringVar(value=_s(L[k]))
            ttk.Entry(f, textvariable=v, width=8, justify="right").grid(row=i, column=1)
            self.vars[k] = v
        tk.Label(f, text="Valors per defecte basats en els informes de premàster de vinil. Els temes de la zona "
                         "interior (final de cara)\npugen un nivell en graves i sibilància.", bg=th.BG, fg=th.MUTED,
                 font=th.FONTS["small"], justify="left").grid(row=i + 1, column=0, columnspan=3, sticky="w", pady=8)
        b = tk.Frame(self, bg=th.BG)
        b.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Button(b, text="Valors per defecte", command=self.defaults).pack(side="left")
        ttk.Button(b, text="Cancel·lar", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Desar", command=self.save).pack(side="right", padx=6)
        self.grab_set()

    def defaults(self):
        for k, v in self.vars.items():
            v.set(_s(DEFAULT_LIMITS[k]))

    def save(self):
        new = dict(self.app.cfg["limits"])
        for k, v in self.vars.items():
            try:
                new[k] = float(v.get().replace(",", "."))
            except ValueError:
                messagebox.showerror("Llindars", "Valor no vàlid: %s" % v.get(), parent=self)
                return
        self.app.cfg["limits"] = new
        self.result = True
        self.destroy()
