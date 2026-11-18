# -*- coding: utf-8 -*-
"""Finestra principal de VinylPremaster."""
import copy
import datetime
import os
import sys
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .. import __version__
from ..analysis import analyze, reclassify, DEFAULT_LIMITS
from ..project import Project, import_vtracklist
from ..repair import run_repair, RepairSettings, VERDICT_TEXT
from ..reports import analysis_report, repair_report, compare_report
from . import dnd
from . import theme as th
from .common import Worker, ReportView, load_config, save_config, config_dir
from .compare_tab import CompareTab
from .repair_tab import RepairTab
from .result_tab import ResultTab
from .settings_dialog import SettingsDialog
from .tracks_tab import TracksTab

APP = "VinylPremaster"
DEFAULTS = {"limits": dict(DEFAULT_LIMITS), "out_bits": "same", "last_dir": ""}


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(base, rel)


def enable_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class AnalysisTab(tk.Frame):
    def __init__(self, master, app):
        tk.Frame.__init__(self, master, bg=th.BG)
        top = tk.Frame(self, bg=th.BG)
        top.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(top, text="Exportar informe inicial (PDF)…", command=lambda: app.export_pdf("analysis")).pack(
            side="left")
        ttk.Button(top, text="Anar a Reparació →", command=lambda: app.notebook.select(2)).pack(side="left", padx=6)
        self.lbl = tk.Label(top, text="", bg=th.BG, fg=th.MUTED)
        self.lbl.pack(side="left", padx=10)
        self.view = ReportView(self, "Encara no s'ha analitzat res.\nCarrega els WAV a la pestanya 1 i clica «Analitzar».")
        self.view.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.app = app

    def refresh(self):
        res = self.app.analysis
        if res is None:
            self.view.set(None, None)
            self.lbl.configure(text="")
        else:
            self.view.set(analysis_report.layout, res)
            self.lbl.configure(text="Analitzat el %s" % res.date.strftime("%d/%m/%Y %H:%M"))


class App(object):
    def __init__(self, root):
        self.root = root
        self.cfg = load_config(DEFAULTS)
        self.project = Project()
        self.analysis = None
        self.repair = None
        th.init_fonts(root)
        style = ttk.Style(root)
        style.theme_use("vista" if "vista" in style.theme_names() else "clam")
        style.configure("TNotebook.Tab", padding=(14, 5))
        style.configure("Accent.TButton", font=th.FONTS["bold"], padding=(14, 4))
        root.configure(bg=th.BG)
        scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
        root.geometry("%dx%d" % (int(1320 * scale), int(880 * scale)))
        root.minsize(int(1080 * scale), int(680 * scale))
        try:
            if sys.platform == "win32":
                root.iconbitmap(default=resource_path(os.path.join("assets", "vinylpremaster.ico")))
            else:
                root.iconphoto(True, tk.PhotoImage(file=resource_path(os.path.join("assets", "vinylpremaster.png"))))
        except Exception:
            pass
        root.title("%s %s — anàlisi i reparació de premàster per a vinil" % (APP, __version__))
        self.worker = Worker(root)
        self._menu()
        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True)
        self.notebook = nb
        self.tracks = TracksTab(nb, self)
        self.analysis_tab = AnalysisTab(nb, self)
        self.repair_tab = RepairTab(nb, self)
        self.result_tab = ResultTab(nb, self)
        self.compare_tab = CompareTab(nb, self)
        for tab, text in ((self.tracks, "1 · Temes"), (self.analysis_tab, "2 · Anàlisi"),
                          (self.repair_tab, "3 · Reparació"), (self.result_tab, "4 · Resultat i escolta A/B"),
                          (self.compare_tab, "5 · Comparar versions")):
            nb.add(tab, text="  %s  " % text)
        root.bind_all("<KeyPress>", self._on_key)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.report_callback_exception = self._tk_error
        self.tracks.refresh()

    def _menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Obrir projecte de VinylTracklist…", command=self.open_vtracklist)
        f.add_command(label="Afegir WAV a la cara A…", command=lambda: self.tracks.add_dialog("A"))
        f.add_command(label="Afegir WAV a la cara B…", command=lambda: self.tracks.add_dialog("B"))
        f.add_separator()
        f.add_command(label="Exportar informe inicial (PDF)…", command=lambda: self.export_pdf("analysis"))
        f.add_command(label="Exportar informe de reparació (PDF)…", command=lambda: self.export_pdf("repair"))
        f.add_separator()
        f.add_command(label="Sortir", command=self.on_close)
        m.add_cascade(label="Fitxer", menu=f)
        t = tk.Menu(m, tearoff=0)
        t.add_command(label="Llindars i objectius…", command=self.open_settings)
        m.add_cascade(label="Eines", menu=t)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Quant a %s" % APP, command=self.about)
        m.add_cascade(label="Ajuda", menu=h)
        self.root.configure(menu=m)

    # ------------------------------------------------------------------
    def _on_key(self, e):
        if self.notebook.select() != str(self.result_tab):
            return
        if isinstance(e.widget, (tk.Entry, ttk.Entry, tk.Spinbox, ttk.Combobox)):
            return
        ch = (e.char or "").lower()
        if ch in (" ", "a", "b"):
            self.result_tab.key(ch)

    def project_changed(self):
        if self.analysis is not None or self.repair is not None:
            self.analysis = None
            self.repair = None
            self.analysis_tab.refresh()
            self.repair_tab.refresh()
            self.result_tab.refresh()

    def open_vtracklist(self):
        path = filedialog.askopenfilename(parent=self.root, title="Obrir projecte de VinylTracklist",
                                          initialdir=self.cfg.get("last_dir") or None,
                                          filetypes=[("Projectes VinylTracklist", "*.vtracklist"),
                                                     ("Tots els fitxers", "*.*")])
        if not path:
            return
        try:
            self.project = import_vtracklist(path)
        except Exception as exc:
            messagebox.showerror(APP, "No s'ha pogut obrir el projecte:\n%s" % exc, parent=self.root)
            return
        self.cfg["last_dir"] = os.path.dirname(path)
        self.analysis = self.repair = None
        self.tracks.refresh()
        self.analysis_tab.refresh()
        self.repair_tab.refresh()
        self.result_tab.refresh()
        missing = [t.path for _, _, t in self.project.all() if not os.path.isfile(t.path)]
        if missing:
            messagebox.showwarning(APP, "No es troben %d fitxers del projecte:\n%s" % (
                len(missing), "\n".join(os.path.basename(m) for m in missing[:8])), parent=self.root)

    # --- anàlisi ------------------------------------------------------------
    def start_analysis(self):
        if self.project.is_empty():
            messagebox.showinfo(APP, "Primer carrega els WAV de cada cara.", parent=self.root)
            return
        if self.worker.busy:
            return
        self.result_tab.stop()
        tab = self.tracks
        tab.btn.state(["disabled"])
        tab.progress.show()
        limits = dict(self.cfg["limits"])
        project = self.project

        def fn(progress, cancelled):
            return analyze(project, limits, progress=lambda k, n, msg: progress(k, n, "Analitzant %s" % msg),
                           cancelled=cancelled)

        def done(res):
            tab.btn.state(["!disabled"])
            if len(res.tracks) < len(list(project.all())):
                tab.progress.hide("Anàlisi cancel·lada.")
                return
            tab.progress.hide("Anàlisi feta: %d temes." % len(res.tracks))
            self.analysis = res
            self.repair = None
            self.analysis_tab.refresh()
            self.repair_tab.refresh()
            self.result_tab.refresh()
            self.notebook.select(1)

        def err(exc, tb):
            tab.btn.state(["!disabled"])
            tab.progress.hide("")
            self.report_error("Error en l'anàlisi", exc, tb)

        self.worker.run(fn, tab.progress.update_progress, done, err)

    # --- reparació --------------------------------------------------------------
    def start_repair(self):
        if self.analysis is None:
            messagebox.showinfo(APP, "Primer cal analitzar els temes (pestanya 1).", parent=self.root)
            return
        if self.worker.busy:
            return
        rt = self.repair_tab
        v = rt.settings_values()
        if not v["out_dir"]:
            messagebox.showwarning(APP, "Tria una carpeta de sortida.", parent=self.root)
            return
        src_dirs = set(os.path.normcase(os.path.dirname(os.path.abspath(t.path))) for t in self.analysis.tracks)
        if os.path.normcase(os.path.abspath(v["out_dir"])) in src_dirs:
            messagebox.showerror(APP, "La carpeta de sortida no pot ser la dels originals.", parent=self.root)
            return
        if os.path.isdir(v["out_dir"]) and os.listdir(v["out_dir"]):
            if not messagebox.askyesno(APP, "La carpeta de sortida ja té fitxers. Els WAV amb el mateix nom se "
                                            "sobreescriuran.\nVols continuar?", parent=self.root):
                return
        self.result_tab.stop()
        self.cfg["out_bits"] = v["out_bits"]
        settings = RepairSettings(v["out_dir"], tp_target=v["tp_target"], out_bits=v["out_bits"],
                                  deess_target=v["deess_target"], bass_fc=v["bass_fc"])
        plan = rt.plan()
        analysis = self.analysis
        rt.btn.state(["disabled"])
        rt.progress.show()

        def fn(progress, cancelled):
            return run_repair(analysis, plan, settings, progress=progress, cancelled=cancelled)

        def done(res):
            rt.btn.state(["!disabled"])
            if res.cancelled:
                rt.progress.hide("Reparació cancel·lada.")
                return
            rt.progress.hide("Fet: %s." % VERDICT_TEXT[res.overall()].lower())
            self.repair = res
            self.result_tab.refresh()
            self.notebook.select(3)

        def err(exc, tb):
            rt.btn.state(["!disabled"])
            rt.progress.hide("")
            self.report_error("Error en la reparació", exc, tb)

        self.worker.run(fn, rt.progress.update_progress, done, err)

    def cancel_work(self):
        self.worker.cancel()

    # --- informes ------------------------------------------------------------
    def export_pdf(self, kind):
        data = {"analysis": self.analysis, "repair": self.repair, "compare": self.compare_tab.result}[kind]
        if data is None:
            messagebox.showinfo(APP, "Encara no hi ha cap informe d'aquest tipus.", parent=self.root)
            return
        mod = {"analysis": analysis_report, "repair": repair_report, "compare": compare_report}[kind]
        name = {"analysis": "Informe premaster vinilo", "repair": "Informe reparacion premaster",
                "compare": "Informe comparativa"}[kind]
        who = " - ".join(x for x in (self.project.artist, self.project.album) if x)
        initial = (who + " - " if who else "") + name + ".pdf"
        initialdir = None
        if kind == "repair":
            initialdir = data.settings.out_dir
        elif kind == "analysis" and data.tracks:
            initialdir = os.path.dirname(data.tracks[0].path)
        path = filedialog.asksaveasfilename(parent=self.root, title="Desar informe", defaultextension=".pdf",
                                            initialfile=initial, initialdir=initialdir or self.cfg.get("last_dir"),
                                            filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        try:
            mod.write_pdf(data, path)
        except Exception as exc:
            self.report_error("No s'ha pogut desar l'informe", exc, traceback.format_exc())
            return
        if messagebox.askyesno(APP, "Informe desat:\n%s\n\nVols obrir-lo ara?" % path, parent=self.root):
            try:
                if sys.platform == "win32":
                    os.startfile(path)  # noqa: B606
            except Exception:
                pass

    # --- altres --------------------------------------------------------------
    def open_settings(self):
        dlg = SettingsDialog(self)
        self.root.wait_window(dlg)
        if dlg.result:
            save_config(self.cfg)
            if self.analysis is not None:
                reclassify(self.analysis, self.cfg["limits"])
                self.analysis_tab.refresh()
                self.repair_tab.refresh()

    def about(self):
        messagebox.showinfo("Quant a %s" % APP,
                            "%s %s\nAnàlisi i reparació de premàster per a vinil.\n\n"
                            "Arrossegar des de l'Explorador: %s\nConfiguració: %s\n\n"
                            "Europe Multimedia Service · INDESINENTER Records"
                            % (APP, __version__, "actiu" if dnd.AVAILABLE else "no disponible", config_dir()),
                            parent=self.root)

    def report_error(self, title, exc, tb):
        try:
            d = config_dir()
            if not os.path.isdir(d):
                os.makedirs(d)
            with open(os.path.join(d, "errors.log"), "a", encoding="utf-8") as f:
                f.write("\n[%s] %s\n%s" % (datetime.datetime.now().isoformat(), title, tb))
        except Exception:
            pass
        messagebox.showerror(APP, "%s:\n%s\n\n(Detall a errors.log, a la carpeta de configuració.)" % (title, exc),
                             parent=self.root)

    def _tk_error(self, exc, val, tb):
        self.report_error("Error inesperat", val, "".join(traceback.format_exception(exc, val, tb)))

    def on_close(self):
        if self.worker.busy and not messagebox.askyesno(APP, "Hi ha un procés en marxa. Vols sortir igualment?",
                                                        parent=self.root):
            return
        self.result_tab.stop()
        save_config(self.cfg)
        self.root.destroy()


def run(argv=None):
    enable_dpi_awareness()
    root = tk.Tk()
    dnd.load(root)
    App(root)
    root.mainloop()
