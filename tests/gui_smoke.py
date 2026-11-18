# -*- coding: utf-8 -*-
"""Prova de la interfície de punta a punta (s'executa amb xvfb-run)."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import tkinter as tk  # noqa: E402
from album import make_album  # noqa: E402
from premaster.ui import dnd  # noqa: E402
from premaster.ui.app import App  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/out"
results = []


def shot(name):
    subprocess.call(["import", "-window", "root", os.path.join(OUT, name)])


def check(cond, msg):
    results.append((bool(cond), msg))


d = tempfile.mkdtemp()
files = make_album(os.path.join(d, "disc"), seconds=10)
root = tk.Tk()
dnd.load(root)
app = App(root)
root.geometry("1320x880+0+0")


def wait(cond, then, timeout=600):
    def poll(n=[0]):
        n[0] += 1
        if cond() or n[0] > timeout:
            then()
        else:
            root.after(100, poll)
    root.after(100, poll)


def step1():
    app.project.artist, app.project.album = "Marina Soler", "Cançons de la Mediterrània"
    app.tracks.add_paths("A", files["A"][::-1])
    app.tracks.add_paths("B", files["B"])
    app.tracks.refresh()
    root.update()
    names = [os.path.basename(t.path)[:3] for t in app.project.sides["A"]]
    check(names == ["A01", "A02", "A03", "A04"], "cara A ordenada alfabèticament: %s" % names)
    shot("pm_1_tracks.png")
    app.start_analysis()
    wait(lambda: app.analysis is not None and not app.worker.busy, step2)


def step2():
    check(app.analysis is not None and len(app.analysis.tracks) == 7, "anàlisi feta (7 temes)")
    check(app.notebook.index("current") == 1, "passa a la pestanya Anàlisi")
    root.after(500, lambda: (shot("pm_2_analysis.png"), step3()))


def step3():
    app.notebook.select(2)
    root.update()
    rt = app.repair_tab
    check(len(rt.vars) == 7, "proposta amb 7 temes")
    b02 = [t for t in app.analysis.tracks if t.pos == "B02"][0]
    check(rt.vars[b02.id]["declip"].get(), "B02 té declip proposat")
    a01 = [t for t in app.analysis.tracks if t.pos == "A01"][0]
    check(rt.vars[a01.id]["deess"].get(), "A01 té de-esser proposat")
    rt.vars[b02.id]["declip"].set(False)   # l'usuari desmarca el declip
    root.after(300, lambda: (shot("pm_3_repair.png"), step4()))


def step4():
    app.start_repair()
    wait(lambda: app.repair is not None and not app.worker.busy, step5)


def step5():
    rr = app.repair
    check(rr is not None and len(rr.tracks) == 7, "reparació feta")
    b02 = [r for r in rr.tracks if r.t.pos == "B02"][0]
    check(b02.declip_fixed == 0 and b02.verdict == "no_apto", "sense declip, B02 queda No apte")
    check(abs(rr.album_tp_after - (-3.0)) < 0.2, "pic d'àlbum a -3 dBTP (%.2f)" % rr.album_tp_after)
    check(app.notebook.index("current") == 3, "passa a Resultat")
    root.after(600, lambda: (shot("pm_4_result.png"), step6()))


def step6():
    ct = app.compare_tab
    ct.vars["A"][0].set(files["A"][0])
    ct.vars["B"][0].set(app.repair.tracks[0].out_path)
    ct.vars["A"][1].set("Original")
    ct.vars["B"][1].set("Reparado")
    app.notebook.select(4)
    ct.run()
    wait(lambda: ct.result is not None and not app.worker.busy, step7)


def step7():
    check(app.compare_tab.result is not None, "comparació feta")
    root.after(600, lambda: (shot("pm_5_compare.png"), finish()))


def finish():
    check(True, "tkdnd: %s" % dnd.AVAILABLE)
    root.after(100, root.destroy)


root.after(300, step1)
root.mainloop()
for ok, msg in results:
    print(("OK   " if ok else "FAIL ") + msg)
sys.exit(0 if all(ok for ok, _ in results) else 1)
