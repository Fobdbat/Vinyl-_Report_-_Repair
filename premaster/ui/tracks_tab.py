# -*- coding: utf-8 -*-
"""Pestanya 1: temes per cares (importar de VinylTracklist o arrossegar WAV) i botó Analitzar."""
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from ..project import WAV_EXTS, filename_key
from ..analysis import fdur
from . import dnd
from . import theme as th
from .common import ProgressBar


def header_text(h):
    if not h.ok:
        return "il·legible"
    k = h.sample_rate / 1000.0
    rate = ("%d" % k) if abs(k - round(k)) < 1e-9 else ("%.1f" % k).replace(".", ",")
    kind = "float" if h.is_float else ("enter" if h.is_pcm else "comprimit")
    return "%s kHz · %d bit %s%s" % (rate, h.effective_bits, kind, " · mono" if h.channels == 1 else "")


class SideList(tk.Frame):
    def __init__(self, master, tab, side):
        tk.Frame.__init__(self, master, bg=th.PANEL, highlightthickness=1, highlightbackground=th.BORDER)
        self.tab = tab
        self.side = side
        head = tk.Frame(self, bg=th.NAVY)
        head.pack(fill="x")
        tk.Label(head, text="CARA %s" % side, bg=th.NAVY, fg=th.WHITE, font=th.FONTS["side"], padx=10,
                 pady=6).pack(side="left")
        self.lbl_total = tk.Label(head, text="", bg=th.NAVY, fg=th.WHITE, font=th.FONTS["bold"], padx=10)
        self.lbl_total.pack(side="right")
        bar = tk.Frame(self, bg=th.PANEL)
        bar.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Button(bar, text="+ Afegir WAV…", command=lambda: tab.add_dialog(side)).pack(side="left")
        other = "B" if side == "A" else "A"
        ttk.Button(bar, text="Treure", command=lambda: tab.remove(self.selected())).pack(side="right")
        ttk.Button(bar, text=("→ Cara %s" if side == "A" else "← Cara %s") % other,
                   command=lambda: tab.move_other(self.selected())).pack(side="right", padx=4)
        ttk.Button(bar, text="▼", width=3, command=lambda: tab.shift(self.selected(), 1)).pack(side="right")
        ttk.Button(bar, text="▲", width=3, command=lambda: tab.shift(self.selected(), -1)).pack(side="right", padx=2)
        body = tk.Frame(self, bg=th.PANEL)
        body.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        self.tree = ttk.Treeview(body, columns=("pos", "title", "dur", "fmt"), show="headings", selectmode="browse")
        for col, txt, w, anchor in (("pos", "Pos.", 50, "w"), ("title", "Títol", 220, "w"), ("dur", "Durada", 60, "e"),
                                    ("fmt", "Format", 170, "w")):
            self.tree.heading(col, text=txt, anchor=anchor)
            self.tree.column(col, width=w, anchor=anchor, stretch=(col == "title"))
        sb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.tag_configure("bad", foreground=th.RED)
        self.tree.bind("<Double-1>", lambda e: tab.rename(self.selected()))
        self.tree.bind("<Delete>", lambda e: tab.remove(self.selected()))
        dnd.register_files_drop(self.tree, lambda paths, _y=None: tab.add_paths(side, paths))

    def selected(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def refresh(self, select_id=None):
        self.tree.delete(*self.tree.get_children())
        items = self.tab.app.project.sides.get(self.side, [])
        for i, t in enumerate(items):
            bad = (not t.header.ok) or t.header.is_float or not (t.header.is_pcm or t.header.is_float)
            self.tree.insert("", "end", iid=str(t.id), values=("%s%02d" % (self.side, i + 1), t.title,
                                                               fdur(t.duration), header_text(t.header)),
                             tags=("bad",) if bad else ())
        if select_id is not None and self.tree.exists(str(select_id)):
            self.tree.selection_set(str(select_id))
            self.tree.see(str(select_id))
        total = sum(t.duration for t in items)
        self.lbl_total.configure(text="%d temes · %s" % (len(items), fdur(total)) if items else "")


class TracksTab(tk.Frame):
    def __init__(self, master, app):
        tk.Frame.__init__(self, master, bg=th.BG)
        self.app = app
        top = tk.Frame(self, bg=th.BG)
        top.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(top, text="Obrir projecte de VinylTracklist…", command=app.open_vtracklist).pack(side="left")
        ttk.Button(top, text="Buidar la llista", command=self.clear).pack(side="left", padx=6)
        self.lbl_source = tk.Label(top, text="", bg=th.BG, fg=th.MUTED, font=th.FONTS["small"])
        self.lbl_source.pack(side="left", padx=8)

        meta = tk.Frame(self, bg=th.BG)
        meta.pack(fill="x", padx=10, pady=(2, 6))
        self.var_artist = tk.StringVar()
        self.var_album = tk.StringVar()
        for label, var, attr in (("Artista", self.var_artist, "artist"), ("Disc", self.var_album, "album")):
            tk.Label(meta, text=label, bg=th.BG, fg=th.TEXT).pack(side="left", padx=(0, 4))
            ttk.Entry(meta, textvariable=var, width=34).pack(side="left", padx=(0, 14))
            var.trace_add("write", lambda *_a, v=var, a=attr: setattr(self.app.project, a, v.get()))
        tk.Label(meta, text="(surten a la capçalera dels informes)", bg=th.BG, fg=th.MUTED,
                 font=th.FONTS["small"]).pack(side="left")

        sides = tk.Frame(self, bg=th.BG)
        sides.pack(fill="both", expand=True, padx=10, pady=4)
        self.lists = {}
        for c, s in enumerate(("A", "B")):
            sl = SideList(sides, self, s)
            sl.grid(row=0, column=c, sticky="nsew", padx=(0, 8) if c == 0 else 0)
            sides.grid_columnconfigure(c, weight=1, uniform="s")
            self.lists[s] = sl
        sides.grid_rowconfigure(0, weight=1)
        tk.Label(self, text="Arrossega els WAV des de l'Explorador a cada cara (s'ordenen alfabèticament) o obre un "
                            "projecte de VinylTracklist. L'ordre de cares importa: el final de cada cara és la zona "
                            "més delicada del disc.", bg=th.BG, fg=th.MUTED, font=th.FONTS["small"],
                 wraplength=1100, justify="left").pack(fill="x", padx=10)

        bottom = tk.Frame(self, bg=th.BG)
        bottom.pack(fill="x", padx=10, pady=10)
        self.btn = ttk.Button(bottom, text="Analitzar ▶", style="Accent.TButton", command=app.start_analysis)
        self.btn.pack(side="left")
        self.progress = ProgressBar(bottom, on_cancel=app.cancel_work)
        self.progress.pack(side="left", padx=12)

    def refresh(self, select_id=None):
        p = self.app.project
        self.var_artist.set(p.artist)
        self.var_album.set(p.album)
        self.lbl_source.configure(text=("Projecte: " + os.path.basename(p.source)) if p.source else "")
        for sl in self.lists.values():
            sl.refresh(select_id)

    def changed(self, select_id=None):
        self.app.project_changed()
        for sl in self.lists.values():
            sl.refresh(select_id)

    # --- accions ---------------------------------------------------------
    def add_dialog(self, side):
        paths = filedialog.askopenfilenames(parent=self, title="Afegir WAV a la cara %s" % side,
                                            initialdir=self.app.cfg.get("last_dir") or None,
                                            filetypes=[("Fitxers WAV", "*.wav *.WAV *.wave *.bwf"),
                                                       ("Tots els fitxers", "*.*")])
        if paths:
            self.add_paths(side, list(self.tk.splitlist(paths)) if isinstance(paths, str) else list(paths))

    def add_paths(self, side, paths):
        files = []
        for p in paths:
            if os.path.isdir(p):
                files += sorted((os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(WAV_EXTS)),
                                key=filename_key)
            elif p.lower().endswith(WAV_EXTS):
                files.append(p)
        if not files:
            messagebox.showwarning("VinylPremaster", "Només es poden carregar fitxers WAV.", parent=self)
            return
        self.app.cfg["last_dir"] = os.path.dirname(files[0])
        self.app.project.add_files(side, files)
        self.changed()

    def shift(self, tid, delta):
        if tid is not None:
            self.app.project.shift(tid, delta)
            self.changed(tid)

    def move_other(self, tid):
        if tid is not None:
            self.app.project.move_other(tid)
            self.changed(tid)

    def remove(self, tid):
        if tid is not None:
            self.app.project.remove(tid)
            self.changed()

    def rename(self, tid):
        if tid is None:
            return
        side, i = self.app.project.locate(tid)
        t = self.app.project.sides[side][i]
        new = simpledialog.askstring("Títol del tema", "Títol:", initialvalue=t.title, parent=self)
        if new and new.strip():
            t.title = new.strip()
            self.changed(tid)

    def clear(self):
        if self.app.project.is_empty():
            return
        if messagebox.askyesno("VinylPremaster", "Vols buidar la llista de temes?", parent=self):
            self.app.project.clear()
            self.app.project_changed()
            self.refresh()
