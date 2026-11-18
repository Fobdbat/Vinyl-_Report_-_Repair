# -*- coding: utf-8 -*-
"""Pestanya 3: proposta de reparació editable i botó Reparar."""
import os
import tkinter as tk
from tkinter import ttk, filedialog

from ..analysis import suggested_actions, track_heading, RANK, f1
from ..repair import default_out_dir
from . import theme as th
from .common import ProgressBar
from .scrollframe import ScrollFrame

TP_VALUES = tuple(("%.1f" % (-v / 2.0)).replace(".", ",") for v in range(2, 13))       # -1,0 .. -6,0
DEESS_VALUES = tuple(("%.1f" % (-v / 2.0)).replace(".", ",") for v in range(10, 29))   # -5,0 .. -14,0
FC_VALUES = ("100", "120", "150", "180", "200")
WORST_COLOR = {0: th.GREEN, 1: th.YELLOW_TEXT, 2: th.RED}


def num(s, default):
    try:
        return float(str(s).replace(",", "."))
    except ValueError:
        return default


class RepairTab(tk.Frame):
    def __init__(self, master, app):
        tk.Frame.__init__(self, master, bg=th.BG)
        self.app = app
        self.vars = {}

        sets = tk.Frame(self, bg=th.PANEL, highlightthickness=1, highlightbackground=th.BORDER)
        sets.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(sets, text="AJUSTOS GLOBALS", bg=th.PANEL, fg=th.NAVY, font=th.FONTS["bold"]).grid(
            row=0, column=0, columnspan=8, sticky="w", padx=10, pady=(8, 4))
        L = app.cfg["limits"]
        self.var_tp = tk.StringVar()
        self.var_deess = tk.StringVar()
        self.var_fc = tk.StringVar()
        self.var_bits = tk.StringVar(value=app.cfg.get("out_bits", "same"))
        self.var_out = tk.StringVar()
        r = 1
        tk.Label(sets, text="Pic real objectiu (headroom)", bg=th.PANEL).grid(row=r, column=0, sticky="w", padx=(10, 4))
        sp = tk.Spinbox(sets, values=TP_VALUES, textvariable=self.var_tp, width=6, justify="right")
        sp.grid(row=r, column=1, sticky="w")
        self.var_tp.set(f1(L["tp_target"]))
        tk.Label(sets, text="dBTP", bg=th.PANEL).grid(row=r, column=2, sticky="w", padx=(3, 20))
        tk.Label(sets, text="Objectiu del de-esser", bg=th.PANEL).grid(row=r, column=3, sticky="w", padx=(0, 4))
        sp2 = tk.Spinbox(sets, values=DEESS_VALUES, textvariable=self.var_deess, width=6, justify="right")
        sp2.grid(row=r, column=4, sticky="w")
        self.var_deess.set(f1(L["deess_target"]))
        tk.Label(sets, text="dB", bg=th.PANEL).grid(row=r, column=5, sticky="w", padx=(3, 20))
        tk.Label(sets, text="Mono en graves per sota de", bg=th.PANEL).grid(row=r, column=6, sticky="w", padx=(0, 4))
        cb = ttk.Combobox(sets, values=FC_VALUES, textvariable=self.var_fc, width=5)
        cb.grid(row=r, column=7, sticky="w")
        self.var_fc.set("%d" % L["bass_fc"])
        tk.Label(sets, text="Hz", bg=th.PANEL).grid(row=r, column=8, sticky="w", padx=(3, 10))
        r = 2
        tk.Label(sets, text="Bits de sortida", bg=th.PANEL).grid(row=r, column=0, sticky="w", padx=(10, 4), pady=6)
        bf = tk.Frame(sets, bg=th.PANEL)
        bf.grid(row=r, column=1, columnspan=4, sticky="w")
        ttk.Radiobutton(bf, text="Igual que l'original", value="same", variable=self.var_bits).pack(side="left")
        ttk.Radiobutton(bf, text="24 bits", value="24", variable=self.var_bits).pack(side="left", padx=10)
        r = 3
        tk.Label(sets, text="Carpeta de sortida", bg=th.PANEL).grid(row=r, column=0, sticky="w", padx=(10, 4),
                                                                    pady=(0, 10))
        ttk.Entry(sets, textvariable=self.var_out, width=70).grid(row=r, column=1, columnspan=6, sticky="we",
                                                                  pady=(0, 10))
        ttk.Button(sets, text="Triar…", command=self.choose_out).grid(row=r, column=7, columnspan=2, sticky="w",
                                                                      padx=6, pady=(0, 10))

        tk.Label(self, text="PROPOSTA DE REPARACIÓ  —  marcada segons l'anàlisi; pots canviar-la abans de reparar",
                 bg=th.BG, fg=th.NAVY, font=th.FONTS["bold"]).pack(anchor="w", padx=10, pady=(6, 2))
        self.table = ScrollFrame(self, bg=th.CARD)
        self.table.pack(fill="both", expand=True, padx=10)
        self.empty = tk.Label(self.table.inner, text="Primer cal analitzar els temes (pestanya 1).", bg=th.CARD,
                              fg=th.MUTED, font=th.FONTS["title"], pady=40)

        bottom = tk.Frame(self, bg=th.BG)
        bottom.pack(fill="x", padx=10, pady=10)
        self.btn = ttk.Button(bottom, text="Reparar ▶", style="Accent.TButton", command=app.start_repair)
        self.btn.pack(side="left")
        ttk.Button(bottom, text="Restablir la proposta", command=self.reset_plan).pack(side="left", padx=8)
        self.progress = ProgressBar(bottom, on_cancel=app.cancel_work)
        self.progress.pack(side="left", padx=12)
        tk.Label(bottom, text="Els originals no es modifiquen mai: els WAV reparats es desen a la carpeta de sortida.",
                 bg=th.BG, fg=th.MUTED, font=th.FONTS["small"]).pack(side="right")

    def choose_out(self):
        d = filedialog.askdirectory(parent=self, title="Carpeta de sortida", initialdir=self.var_out.get() or None)
        if d:
            self.var_out.set(d)

    def refresh(self):
        for w in self.table.inner.winfo_children():
            if w is not self.empty:
                w.destroy()
        self.vars = {}
        res = self.app.analysis
        if res is None or not res.good:
            self.empty.pack(fill="x")
            return
        self.empty.pack_forget()
        if not self.var_out.get():
            self.var_out.set(default_out_dir(res))
        inner = self.table.inner
        hdrs = ("Tema", "Diagnòstic", "Declip", "Mono en graves", "De-esser")
        for c, h in enumerate(hdrs):
            tk.Label(inner, text=h, bg=th.NAVY, fg=th.WHITE, font=th.FONTS["bold"], padx=8, pady=5,
                     anchor="w" if c < 2 else "center").grid(row=0, column=c, sticky="nsew")
        inner.grid_columnconfigure(1, weight=1)
        L = res.limits
        for i, t in enumerate(res.good, start=1):
            bg = th.CARD if i % 2 else th.PANEL
            worst = t.worst()
            sug = suggested_actions(t, L)
            tk.Label(inner, text="%s  %s" % (t.pos, t.title), bg=bg, fg=th.NAVY, font=th.FONTS["bold"], anchor="w",
                     padx=8, pady=4).grid(row=i, column=0, sticky="nsew")
            tk.Label(inner, text=track_heading(t, L), bg=bg, fg=WORST_COLOR[worst], anchor="w", padx=8,
                     font=th.FONTS["normal"]).grid(row=i, column=1, sticky="nsew")
            vs = {}
            for c, key in enumerate(("declip", "bass_mono", "deess"), start=2):
                v = tk.BooleanVar(value=sug[key])
                state = "normal"
                if key == "declip" and t.m["clipped_samples"] == 0:
                    state = "disabled"
                if key == "bass_mono" and t.m["channels"] < 2:
                    state = "disabled"
                cell = tk.Frame(inner, bg=bg)
                cell.grid(row=i, column=c, sticky="nsew")
                ttk.Checkbutton(cell, variable=v, state=state).pack(anchor="center", pady=2)
                vs[key] = v
            self.vars[t.id] = vs

    def reset_plan(self):
        self.refresh()

    def plan(self):
        return {tid: {k: bool(v.get()) for k, v in vs.items()} for tid, vs in self.vars.items()}

    def settings_values(self):
        L = self.app.cfg["limits"]
        return {
            "tp_target": max(-12.0, min(-0.5, num(self.var_tp.get(), L["tp_target"]))),
            "deess_target": max(-20.0, min(-3.0, num(self.var_deess.get(), L["deess_target"]))),
            "bass_fc": max(60.0, min(300.0, num(self.var_fc.get(), L["bass_fc"]))),
            "out_bits": self.var_bits.get(),
            "out_dir": self.var_out.get().strip(),
        }
