# -*- coding: utf-8 -*-
"""Peces compartides: vista prèvia d'informes, treballs en segon pla, configuració."""
import copy
import json
import os
import queue
import sys
import threading
import traceback
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from ..reports.canvas import PAGE_W, PAGE_H
from . import theme as th

CANVAS_BG = "#d9dee5"


# ------------------------------------------------------------------ configuració
def config_dir():
    base = os.environ.get("APPDATA")
    if base:
        return os.path.join(base, "VinylPremaster")
    return os.path.join(os.path.expanduser("~"), ".config", "vinylpremaster")


def load_config(defaults):
    cfg = copy.deepcopy(defaults)
    try:
        with open(os.path.join(config_dir(), "config.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if k not in cfg:
                continue
            if k == "limits":
                if isinstance(v, dict):
                    for lk, lv in v.items():
                        if lk in cfg["limits"] and isinstance(lv, (int, float)):
                            cfg["limits"][lk] = float(lv)
            elif isinstance(v, type(cfg[k])) or (isinstance(cfg[k], float) and isinstance(v, int)):
                cfg[k] = v
    except (IOError, OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    try:
        d = config_dir()
        if not os.path.isdir(d):
            os.makedirs(d)
        with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except (IOError, OSError):
        pass


# ------------------------------------------------------------------ treballs en segon pla
class Worker(object):
    """Executa una funció llarga en un fil i en retorna el progrés i el resultat al fil de la interfície."""

    def __init__(self, widget):
        self.widget = widget
        self.q = queue.Queue()
        self.thread = None
        self._cancel = False

    @property
    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def cancel(self):
        self._cancel = True

    def run(self, fn, on_progress, on_done, on_error):
        self._cancel = False
        self.on_progress, self.on_done, self.on_error = on_progress, on_done, on_error

        def target():
            try:
                res = fn(progress=lambda k, n, msg: self.q.put(("p", k, n, msg)),
                         cancelled=lambda: self._cancel)
                self.q.put(("done", res))
            except Exception as exc:  # noqa: BLE001
                self.q.put(("err", exc, traceback.format_exc()))

        self.thread = threading.Thread(target=target)
        self.thread.daemon = True
        self.thread.start()
        self.widget.after(100, self._poll)

    def _poll(self):
        finished = False
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "p":
                    self.on_progress(*item[1:])
                elif item[0] == "done":
                    finished = True
                    self.on_done(item[1])
                else:
                    finished = True
                    self.on_error(item[1], item[2])
        except queue.Empty:
            pass
        if not finished:
            self.widget.after(100, self._poll)


class ProgressBar(tk.Frame):
    def __init__(self, master, on_cancel=None):
        tk.Frame.__init__(self, master, bg=th.BG)
        self.bar = ttk.Progressbar(self, mode="determinate", length=260)
        self.bar.pack(side="left")
        self.lbl = tk.Label(self, text="", bg=th.BG, fg=th.MUTED, font=th.FONTS["small"])
        self.lbl.pack(side="left", padx=8)
        self.btn = ttk.Button(self, text="Cancel·lar", command=on_cancel)
        if on_cancel:
            self.btn.pack(side="left")
        self.hide()

    def show(self):
        self.bar.configure(value=0)
        self.lbl.configure(text="")
        self.bar.pack(side="left")
        if self.btn.winfo_manager() == "" and self.btn.cget("command"):
            self.btn.pack(side="left")

    def update_progress(self, k, n, msg):
        self.bar.configure(maximum=max(1, n), value=k)
        self.lbl.configure(text=msg)

    def hide(self, text=""):
        self.bar.pack_forget()
        self.btn.pack_forget()
        self.lbl.configure(text=text)


# ------------------------------------------------------------------ vista prèvia
def _hex(c):
    return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in c)


class TkPainter(object):
    """Mateixa interfície que el llenç PDF, però dibuixant en un tk.Canvas."""

    def __init__(self, canvas, scale, x0, gap):
        self.cv = canvas
        self.s = scale
        self.x0 = x0
        self.gap = gap
        self.index = -1
        self.oy = 0
        self.fonts = {}
        if sys.platform == "win32":
            self.family = "Arial"
        else:
            fams = set(tkfont.families(canvas))
            self.family = next((f for f in ("Liberation Sans", "Arimo", "DejaVu Sans") if f in fams), "Helvetica")

    def _x(self, x):
        return self.x0 + x * self.s

    def _y(self, y):
        return self.oy + (PAGE_H - y) * self.s

    def _font(self, size, bold, italic):
        px = max(6, int(round(size * self.s)))
        key = (px, bold, italic)
        if key not in self.fonts:
            self.fonts[key] = tkfont.Font(self.cv, family=self.family, size=-px,
                                          weight="bold" if bold else "normal", slant="italic" if italic else "roman")
        return self.fonts[key]

    def new_page(self):
        self.index += 1
        self.oy = self.gap + self.index * (PAGE_H * self.s + self.gap)
        w, h = PAGE_W * self.s, PAGE_H * self.s
        self.cv.create_rectangle(self.x0 + 4, self.oy + 4, self.x0 + w + 4, self.oy + h + 4, fill="#b8c0ca", width=0)
        self.cv.create_rectangle(self.x0, self.oy, self.x0 + w, self.oy + h, fill="white", outline="#aab3be")

    def text(self, x, y, s, size=10, bold=False, color=(0, 0, 0), align="left", italic=False):
        f = self._font(size, bold, italic)
        anchor = {"left": "nw", "right": "ne", "center": "n"}[align]
        self.cv.create_text(self._x(x), self._y(y) - f.metrics("ascent"), text=s, font=f, fill=_hex(color),
                            anchor=anchor)

    def rect(self, x, y, w, h, fill):
        self.cv.create_rectangle(self._x(x), self._y(y + h), self._x(x + w), self._y(y), fill=_hex(fill), width=0)

    def line(self, x1, y1, x2, y2, color=(0.8, 0.8, 0.8), width=0.6):
        self.cv.create_line(self._x(x1), self._y(y1), self._x(x2), self._y(y2), fill=_hex(color),
                            width=max(1, int(round(width * self.s))))


class ReportView(tk.Frame):
    """Mostra un informe (funció layout(dades, llenç)) com a pàgines a la pantalla."""

    def __init__(self, master, empty_text):
        tk.Frame.__init__(self, master, bg=CANVAS_BG)
        self.empty_text = empty_text
        self.layout_fn = None
        self.data = None
        self._job = None
        self._last_w = 0
        self.cv = tk.Canvas(self, bg=CANVAS_BG, highlightthickness=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.cv.yview)
        self.cv.configure(yscrollcommand=self.vbar.set)
        self.cv.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="left", fill="y")
        self.cv.bind("<Configure>", self._on_resize)
        self.cv.bind("<Enter>", self._bind_wheel)
        self.cv.bind("<Leave>", self._unbind_wheel)

    def set(self, layout_fn, data):
        self.layout_fn = layout_fn
        self.data = data
        self.refresh()

    def _on_resize(self, e):
        if abs(e.width - self._last_w) > 4:
            self._last_w = e.width
            self.refresh(keep=True)

    def _bind_wheel(self, _e=None):
        if sys.platform.startswith("linux"):
            self.cv.bind_all("<Button-4>", lambda e: self.cv.yview_scroll(-2, "units"))
            self.cv.bind_all("<Button-5>", lambda e: self.cv.yview_scroll(2, "units"))
        else:
            self.cv.bind_all("<MouseWheel>", lambda e: self.cv.yview_scroll(-2 if e.delta > 0 else 2, "units"))

    def _unbind_wheel(self, _e=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.cv.unbind_all(seq)

    def refresh(self, keep=False):
        if self._job is not None:
            self.after_cancel(self._job)
        self._job = self.after(60, lambda: self._render(keep))

    def _render(self, keep):
        self._job = None
        cv = self.cv
        top = cv.yview()[0] if keep else 0.0
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 50:
            return
        if self.data is None or self.layout_fn is None:
            cv.create_text(w / 2, h / 3, text=self.empty_text, font=th.FONTS["title"], fill=th.MUTED, width=w - 80,
                           justify="center")
            cv.configure(scrollregion=(0, 0, w, h))
            return
        page_w = min(860, max(460, w - 60))
        scale = page_w / PAGE_W
        gap = 20
        painter = TkPainter(cv, scale, (w - page_w) / 2.0, gap)
        try:
            pages = self.layout_fn(self.data, painter)
        except Exception:  # noqa: BLE001
            cv.create_text(w / 2, 60, text="Error en dibuixar l'informe:\n" + traceback.format_exc()[-400:],
                           fill="#c0392b", width=w - 60)
            return
        cv.configure(scrollregion=(0, 0, w, gap + pages * (PAGE_H * scale + gap)))
        cv.yview_moveto(top)
