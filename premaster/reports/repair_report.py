# -*- coding: utf-8 -*-
"""Informe de reparació: abans/després, què s'ha fet, què no, i veredicte per a fàbrica."""
import os

from ..analysis import f1, f2, f2s
from ..repair import VERDICT_TEXT, summary_sentence, actions_line
from .canvas import Doc, PdfCanvas, NAVY, RED, GREEN, AMBER, MUTED, TEXT, WHITE, MARGIN, CONTENT_W, PAGE_W

TITLE = "Informe de reparación de premáster para vinilo"
V_COLOR = {"apto": GREEN, "reservas": AMBER, "no_apto": RED}
V_STATUS = {"apto": "green", "reservas": "yellow", "no_apto": "red"}
V_SHORT = {"apto": "Apto", "reservas": "Reservas", "no_apto": "No apto"}


def _ba(before, after, st):
    return {"text": after, "sub": "antes " + before, "status": st if st != "ok" else None, "bold": True}


def layout(rr, c):
    a = rr.analysis
    proj = a.project
    st = rr.settings
    who = " — ".join(x for x in (proj.artist, proj.album) if x)
    sub = []
    if who:
        sub.append(who)
    sub.append("%d temas · Salida: %s" % (len(rr.tracks), st.out_dir))
    sub.append("Fecha: %s" % rr.date.strftime("%d/%m/%Y %H:%M"))
    d = Doc(c, "Informe de reparación de premáster" + (" — " + who if who else ""))
    d.title(TITLE, sub)

    # Veredicte
    v = rr.overall()
    d.need(56)
    y = d.y
    c.rect(MARGIN, y - 44, CONTENT_W, 44, V_COLOR[v])
    c.text(MARGIN + 12, y - 20, VERDICT_TEXT[v], 15, True, WHITE)
    c.text(MARGIN + 12, y - 35, summary_sentence(rr), 8.8, False, WHITE)
    d.y = y - 58

    # 1. Ajustos globals
    d.h1("1. Ajustes globales")
    if rr.gain_db < 0:
        who_peak = rr.peak_track.pos if rr.peak_track is not None else "—"
        d.bullet("Headroom.", "Reducción de nivel uniforme de %s dB para dejar el pico de álbum en %s dBTP (antes %s "
                              "dBTP; lo marca %s). Balance de nivel entre temas intacto." % (
                     f1(rr.gain_db), f1(st.tp_target), f2(rr.album_tp_before), who_peak))
        d.bullet("", "La reducción solo da margen de pico; no restaura la dinámica que el limitador ya comprimió.")
    else:
        d.bullet("Headroom.", "Sin cambio de nivel: el pico de álbum ya estaba en %s dBTP." % f2(rr.album_tp_before))
    bits = sorted(set(r.out_bits for r in rr.tracks))
    mode = "igual que el original" if st.out_bits == "same" else "24 bits"
    d.bullet("Formato de salida.", "WAV entero %s bit (%s), frecuencia de muestreo original. Dither TPDF en los temas "
                                   "procesados; copia idéntica bit a bit en los que no se tocan."
             % (" / ".join(str(b) for b in bits), mode))
    d.bullet("Originales.", "No se han modificado. Los archivos reparados están en la carpeta de salida.")
    d.gap(6)

    # 2. Taula abans/després
    d.h1("2. Antes / después por tema")
    cols = [("#", 28, "left"), ("Tema", 110, "left"), ("True peak (dBTP)", 52, "right"),
            ("Clipping (muestras)", 50, "right"), ("Corr. <150 Hz", 50, "right"), ("Side/Mid <150 Hz", 52, "right"),
            ("Sibil. (dB)", 46, "right"), ("Crest (dB)", 44, "right"), ("Veredicto", 63, "center")]
    rows = []
    seps = []
    prev = None
    for r in rr.tracks:
        t, m0, m1, s1 = r.t, r.t.m, r.m_after, r.status_after
        if prev is not None and t.side != prev:
            seps.append(len(rows))
        prev = t.side
        corr0 = f2s(m0["corr150"]) if m0["corr150"] is not None else "—"
        corr1 = f2s(m1["corr150"]) if m1["corr150"] is not None else "—"
        sm0 = f1(m0["sm150"]) if m0["sm150"] is not None else "—"
        sm1 = f1(m1["sm150"]) if m1["sm150"] is not None else "—"
        rows.append([
            {"text": t.pos, "bold": True, "color": NAVY},
            {"text": t.title, "sub": "copia idéntica" if r.bit_exact else ""},
            _ba(f2(m0["tp_db"]), f2(m1["tp_db"]), s1["tp"]),
            _ba(str(m0["clipped_samples"]), str(m1["clipped_samples"]), s1["fs"]),
            _ba(corr0, corr1, s1["corr"]),
            _ba(sm0, sm1, s1["sm"]),
            _ba(f1(m0["sibilance_db"]), f1(m1["sibilance_db"]), s1["sib"]),
            _ba(f1(m0["crest_db"]), f1(m1["crest_db"]), s1["crest"]),
            {"text": V_SHORT[r.verdict], "status": V_STATUS[r.verdict], "bold": True},
        ])
    d.table(cols, rows, separators=seps)
    d.legend([("red", "sigue fuera de referencia"), ("yellow", "a vigilar"), ("green", "apto")])
    d.gap(8)

    # 3. Detall
    d.h1("3. Qué se ha hecho en cada tema")
    for r in rr.tracks:
        t = r.t
        d.need(30)
        d.runs([("%s · %s" % (t.pos, t.title), True, NAVY), (u"—", False, MUTED),
                (V_SHORT[r.verdict], True, V_COLOR[r.verdict])], size=9.5)
        d.runs([("Hecho: ", True, TEXT), (actions_line(r) + ".", False, TEXT)], size=9, indent=10)
        pend = list(r.not_done)
        if pend:
            d.runs([("No corregido / pendiente: ", True, RED if r.verdict == "no_apto" else AMBER),
                    ("; ".join(pend) + ".", False, TEXT)], size=9, indent=10)
        d.runs([("Archivo: ", True, MUTED), (os.path.basename(r.out_path or ""), False, MUTED)], size=8, indent=10)
        d.gap(5)

    # 4. Notes
    d.h1("4. Notas")
    if any(r.declip_fixed for r in rr.tracks):
        who = ", ".join(r.t.pos for r in rr.tracks if r.declip_fixed)
        d.bullet("Declip (%s)." % who, "Es una reconstrucción/mitigación del clipping de origen: NO recupera el "
                                        "original. Si existe, conviene pedir una versión sin recortar.")
    if any(r.status_after.get("crest") != "ok" for r in rr.tracks):
        d.bullet("Dinámica.", "El premáster no puede devolver la dinámica que quitó el limitador del máster. "
                              "La vía que da mejor resultado es un premáster sin la fase final de loudness.")
    d.bullet("Antes de fabricar.", "Escuchar los temas procesados (pestaña Escucha A/B) y, si es posible, pedir "
                                   "un corte de prueba (test pressing).")
    d.gap(8)
    d.note("Procesado: mono en graves con filtro paso-alto Butterworth de 4.º orden y fase cero solo en el canal Side "
           "(el Mid no se toca); de-esser de banda partida 5-9 kHz de fase cero con objetivo %s dB; declip por "
           "interpolación cúbica local (máx. +3 dB sobre el tramo plano); reducción de nivel uniforme; dither TPDF a "
           "la resolución de salida. Mediciones: ITU-R BS.1770-4, pico real sobremuestreado x4." % f1(st.deess_target))
    return d.finish()


def write_pdf(rr, path):
    c = PdfCanvas()
    layout(rr, c)
    c.save(path, TITLE)
