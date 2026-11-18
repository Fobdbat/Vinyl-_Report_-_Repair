# -*- coding: utf-8 -*-
"""Pestanya 4: informe de reparació i escolta A/B (original / reparat)."""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox

from ..audio_io import read_audio
from ..reports import repair_report
from . import player as pl
from . import theme as th
from .common import ReportView


def fmt_time(s):
    s = max(0, int(s))
    return "%d:%02d" % (s // 60, s % 60)


class ResultTab(tk.Frame):
    def __init__(self, master, app):
        tk.Frame.__init__(self, master, bg=th.BG)
        self.app = app
        self.player = pl.ABPlayer()
        self._loaded = None
        self._dragging = False

        top = tk.Frame(self, bg=th.BG)
        top.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(top, text="Exportar informe de reparació (PDF)…",
                   command=lambda: app.export_pdf("repair")).pack(side="left")
        ttk.Button(top, text="Obrir la carpeta de sortida", command=self.open_out).pack(side="left", padx=6)
        self.lbl = tk.Label(top, text="", bg=th.BG, fg=th.MUTED)
        self.lbl.pack(side="left", padx=10)

        ab = tk.Frame(self, bg=th.PANEL, highlightthickness=1, highlightbackground=th.BORDER)
        ab.pack(fill="x", padx=10, pady=4)
        tk.Label(ab, text="ESCOLTA A/B", bg=th.PANEL, fg=th.NAVY, font=th.FONTS["bold"]).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        if not pl.AVAILABLE:
            tk.Label(ab, text="Reproducció no disponible en aquest ordinador (%s)." % pl.ERROR[:120], bg=th.PANEL,
                     fg=th.RED).grid(row=3, column=0, columnspan=8, sticky="w", padx=10, pady=(0, 8))
        self.cb = ttk.Combobox(ab, state="readonly", width=44)
        self.cb.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 8))
        self.cb.bind("<<ComboboxSelected>>", lambda e: self.load_selected())
        self.btn_play = ttk.Button(ab, text="▶ Reproduir", command=self.toggle_play)
        self.btn_play.grid(row=1, column=1, padx=4, pady=(0, 8))
        self.var_which = tk.StringVar(value="A")
        ttk.Radiobutton(ab, text="A · Original", value="A", variable=self.var_which, style="Toolbutton",
                        command=self.switch).grid(row=1, column=2, padx=(10, 0), pady=(0, 8))
        ttk.Radiobutton(ab, text="B · Reparat", value="B", variable=self.var_which, style="Toolbutton",
                        command=self.switch).grid(row=1, column=3, pady=(0, 8))
        self.var_match = tk.BooleanVar(value=True)
        ttk.Checkbutton(ab, text="Igualar nivell (escoltar només el processament)", variable=self.var_match,
                        command=self.switch).grid(row=1, column=4, padx=12, pady=(0, 8))
        self.scale = ttk.Scale(ab, from_=0, to=1, orient="horizontal", length=420)
        self.scale.grid(row=2, column=0, columnspan=4, sticky="we", padx=10, pady=(0, 10))
        self.scale.bind("<ButtonPress-1>", lambda e: setattr(self, "_dragging", True))
        self.scale.bind("<ButtonRelease-1>", self.on_seek)
        self.lbl_time = tk.Label(ab, text="0:00 / 0:00", bg=th.PANEL, fg=th.TEXT, font=th.FONTS["bold"])
        self.lbl_time.grid(row=2, column=4, sticky="w", padx=12, pady=(0, 10))
        tk.Label(ab, text="Tecles: espai = reproduir/aturar · A/B = canviar de versió (mateix punt)", bg=th.PANEL,
                 fg=th.MUTED, font=th.FONTS["small"]).grid(row=2, column=5, sticky="w", padx=6, pady=(0, 10))
        self.controls = [self.cb, self.btn_play]
        if not pl.AVAILABLE:
            for w in (self.btn_play,):
                w.state(["disabled"])

        self.view = ReportView(self, "Encara no s'ha reparat res.\nQuan acabi la reparació, aquí hi haurà l'informe i "
                                     "podràs escoltar cada tema abans/després.")
        self.view.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.after(200, self._tick)

    def refresh(self):
        rr = self.app.repair
        if rr is None:
            self.view.set(None, None)
            self.cb.configure(values=())
            self.cb.set("")
            self.lbl.configure(text="")
            return
        self.view.set(repair_report.layout, rr)
        self.lbl.configure(text="Sortida: %s" % rr.settings.out_dir)
        vals = ["%s  %s" % (r.t.pos, r.t.title) for r in rr.tracks]
        self.cb.configure(values=vals)
        if vals:
            self.cb.current(0)
            self._loaded = None

    def open_out(self):
        rr = self.app.repair
        if rr is None:
            return
        d = rr.settings.out_dir
        try:
            if sys.platform == "win32":
                os.startfile(d)  # noqa: B606
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception:
            pass

    # --- reproductor -----------------------------------------------------
    def load_selected(self):
        rr = self.app.repair
        if rr is None or not pl.AVAILABLE:
            return False
        i = self.cb.current()
        if i < 0:
            return False
        r = rr.tracks[i]
        if self._loaded == r.t.id:
            return True
        self.player.stop()
        self.winfo_toplevel().configure(cursor="watch")
        self.update_idletasks()
        try:
            a, ia = read_audio(r.t.path)
            b, _ = read_audio(r.out_path)
            self.player.load(a, b, ia.fs, r.t.m["lufs"], r.m_after["lufs"])
        except Exception as exc:
            messagebox.showerror("VinylPremaster", "No s'ha pogut carregar l'àudio:\n%s" % exc, parent=self)
            return False
        finally:
            self.winfo_toplevel().configure(cursor="")
        self._loaded = r.t.id
        self.scale.configure(to=max(0.1, self.player.duration))
        self.scale.set(0)
        self.switch()
        return True

    def toggle_play(self):
        if self.player.playing:
            self.player.stop()
            self.btn_play.configure(text="▶ Reproduir")
            return
        if not self.load_selected():
            return
        try:
            if self.player.play():
                self.btn_play.configure(text="■ Aturar")
        except Exception as exc:
            messagebox.showerror("VinylPremaster", "No s'ha pogut reproduir:\n%s" % exc, parent=self)

    def switch(self):
        self.player.match = bool(self.var_match.get())
        self.player.set_which(self.var_which.get())

    def key(self, ch):
        if ch == " ":
            self.toggle_play()
        elif ch in ("a", "b"):
            self.var_which.set(ch.upper())
            self.switch()

    def on_seek(self, _e=None):
        self._dragging = False
        self.player.seek(float(self.scale.get()))

    def _tick(self):
        p = self.player
        if p.a is not None:
            if not self._dragging:
                self.scale.set(p.position)
            self.lbl_time.configure(text="%s / %s" % (fmt_time(p.position), fmt_time(p.duration)))
            if not p.playing and self.btn_play.cget("text") != "▶ Reproduir":
                self.btn_play.configure(text="▶ Reproduir")
        self.after(200, self._tick)

    def stop(self):
        self.player.stop()
