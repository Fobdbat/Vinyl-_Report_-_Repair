# -*- coding: utf-8 -*-
"""Informe inicial: «Informe técnico de premasterizado para vinilo»."""
from ..analysis import (executive_summary, global_diagnosis, delivery_notes, track_heading, track_advice,
                        METHODOLOGY, f1, f2, f2s, fdur, bass_status, RANK)
from .canvas import Doc, PdfCanvas, RED, GREEN, NAVY, TEXT, MUTED

TITLE = "Informe técnico de premasterizado para vinilo"


def _cell(text, status="ok", bold=False):
    return {"text": text, "status": status if status != "ok" else None, "bold": bold}


def layout(res, c):
    good = res.good
    n = len(res.tracks)
    proj = res.project
    sides = [s for s in proj.names() if res.side_tracks(s)]
    who = " — ".join(x for x in (proj.artist, proj.album) if x)
    sub = []
    if who:
        sub.append(who)
    sub.append("Análisis de idoneidad de corte · %d temas · Fuente: %s" % (n, res.source_folder() or "—"))
    fm = res.formats()
    sub.append("Fecha: %s  ·  Formato de origen: %s  ·  %s" % (
        res.date.strftime("%d/%m/%Y"), ", ".join(fm) if fm else "—",
        " · ".join("Cara %s: %d temas" % (s, len(res.side_tracks(s))) for s in sides)))
    d = Doc(c, "Informe premasterizado vinilo — análisis de idoneidad de corte" + (" — " + who if who else ""))
    d.title(TITLE, sub)

    # 1. Resumen
    d.h1("1. Resumen ejecutivo")
    lead, bullets = executive_summary(res)
    d.para(lead, size=10, bold=True, color=NAVY, after=6)
    for head, txt in bullets:
        d.bullet(head, txt)
    d.gap(6)

    # 2. Taula
    d.h1("2. Parámetros por canción")
    L = res.limits
    cols = [("#", 28, "left"), ("Tema", 128, "left"), ("Dur.", 32, "right"), ("LUFS", 36, "right"),
            ("True peak (dBTP)", 44, "right"), ("Clipping (muestras)", 46, "right"), ("Crest (dB)", 36, "right"),
            ("Corr. <150 Hz", 42, "right"), ("Side/Mid <150 Hz", 46, "right"), ("Sibil. (dB)", 40, "right")]
    rows = []
    seps = []
    prev = None
    for t in res.tracks:
        if prev is not None and t.side != prev:
            seps.append(len(rows))
        prev = t.side
        if not t.ok:
            rows.append([_cell(t.pos, bold=True), t.title, "—", "—", "—", "—", "—", "—", "—", _cell("ilegible", "red")])
            continue
        m, st = t.m, t.status
        clip_txt = str(m["clipped_samples"]) if m["clipped_samples"] else str(m["fs_samples"])
        corr_txt = f2s(m["corr150"]) if m["corr150"] is not None else "—"
        title = t.title + (" (final cara %s)" % t.side if t.is_last else "")
        rows.append([
            {"text": t.pos, "bold": True, "color": NAVY},
            title,
            fdur(m["duration"]),
            _cell(f1(m["lufs"]), st["lufs"]),
            _cell(f2(m["tp_db"]), st["tp"]),
            _cell(clip_txt, st["fs"]),
            _cell(f1(m["crest_db"]), st["crest"]),
            _cell(corr_txt, st["corr"]),
            _cell(f1(m["sm150"]) if m["sm150"] is not None else "—", st["sm"]),
            _cell(f1(m["sibilance_db"]), st["sib"]),
        ])
    d.table(cols, rows, separators=seps)
    d.legend([("red", "problema a corregir"), ("yellow", "a vigilar")])
    d.note("Referencias vinilo: true peak <= %s dBTP (ideal -3/-6) · LUFS <= %s · crest >= %s dB · corr. <150 Hz >= %s · "
           "Side/Mid <150 Hz < %s dB · sibilancia < %s dB. Clipping: muestras en tramos planos (o a fondo de escala). "
           "En la zona interior de cada cara (final) los avisos de graves y sibilancia suben de nivel."
           % (f1(L["tp_red"]), f1(L["lufs_yellow"]), f1(L["crest_yellow"]), f2s(L["corr_yellow"]),
              f1(L["sm_yellow"]), f1(L["sib_yellow"])))
    d.gap(10)

    # Gràfics
    if good:
        d.need(150)
        top = d.y
        labels = [t.pos for t in good]
        y1 = d.bars("Loudness integrado (LUFS)", labels, [t.m["lufs"] for t in good], "LUFS",
                    target=L["lufs_yellow"], target_label="objetivo vinilo")
        d.y = top
        from .canvas import MARGIN, CONTENT_W
        y2 = d.bars("Rango dinámico (crest, dB)", labels, [t.m["crest_db"] for t in good], "dB",
                    target=L["crest_yellow"], target_label="objetivo vinilo", x0=MARGIN + CONTENT_W / 2 + 10)
        d.y = min(y1, y2) - 4

    # 3. Diagnòstic global
    d.h1("3. Diagnóstico global")
    d.para(global_diagnosis(res))
    d.gap(4)

    # 4. Per tema
    d.h1("4. Qué ajustar en cada canción")
    for t in res.tracks:
        head = track_heading(t, L)
        ok = head == "Sin cambios."
        d.need(30)
        d.runs([("%s · %s" % (t.pos, t.title), True, NAVY), (u"—", False, MUTED),
                (head, True, GREEN if ok else RED)], size=9.5)
        d.para(" ".join(track_advice(t, L)), size=9, after=6)

    # 5. Lliurament
    d.h1("5. Cómo entregar los WAV para el corte")
    for head, txt in delivery_notes(res):
        d.bullet(head, txt)
    d.gap(8)
    d.note(METHODOLOGY + " Análisis sobre los WAV facilitados.")
    return d.finish()


def write_pdf(res, path):
    c = PdfCanvas()
    layout(res, c)
    c.save(path, TITLE)
