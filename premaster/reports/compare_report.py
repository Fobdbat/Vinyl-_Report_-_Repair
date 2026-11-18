# -*- coding: utf-8 -*-
"""Informe de comparació de dues versions (test d'anul·lació)."""
import os

from ..analysis import f1, f2, f2s, fdur
from .canvas import Doc, PdfCanvas, NAVY, RED, GREEN, TEXT, MUTED, MARGIN, CONTENT_W

TITLE = "Informe técnico — comparativa de dos versiones"


def layout(r, c):
    d = Doc(c, "Comparativa de dos versiones — %s / %s" % (os.path.basename(r.path_a), os.path.basename(r.path_b)))
    d.title(TITLE, ["%s: %s  ·  %s: %s" % (r.label_a, os.path.basename(r.path_a), r.label_b, os.path.basename(r.path_b)),
                    "Fecha: %s" % r.date.strftime("%d/%m/%Y")])
    same = r.identical_bytes or r.identical_pcm or (r.null and r.null["residual_rel_db"] < -75)
    d.h1("1. Conclusión principal")
    d.para(r.conclusion, size=10.5, bold=True, color=GREEN if same else NAVY, after=4)
    d.para(r.detail, after=8)

    d.h1("2. Archivos analizados")
    cols = [("Versión", 80, "left"), ("Archivo", 250, "left"), ("Formato", 110, "right"), ("Duración", 55, "right")]
    rows = []
    for lab, p, i in ((r.label_a, r.path_a, r.info_a), (r.label_b, r.path_b, r.info_b)):
        rows.append([{"text": lab, "bold": True, "color": NAVY}, os.path.basename(p), i.describe(), fdur(i.duration)])
    d.table(cols, rows)
    d.gap(6)

    d.h1("3. Resultado de la comparación")
    cols = [("Métrica", 200, "left"), (r.label_a, 140, "right"), (r.label_b, 140, "right")]
    ma, mb = r.m_a, r.m_b

    def row(name, fa, fb, bold=False):
        return [name, {"text": fa, "bold": bold}, {"text": fb, "bold": bold}]

    rows = [
        row("Loudness integrado (LUFS)", f1(ma["lufs"]), f1(mb["lufs"]), True),
        row("RMS (dBFS)", f1(ma["rms_db"]), f1(mb["rms_db"])),
        row("Pico de muestra (dBFS)", f2(ma["peak_db"]), f2(mb["peak_db"])),
        row("Pico real (dBTP)", f2(ma["tp_db"]), f2(mb["tp_db"]), True),
        row("Muestras a fondo de escala", str(ma["fs_samples"]), str(mb["fs_samples"])),
        row("Clipping (muestras en tramos planos)", str(ma["clipped_samples"]), str(mb["clipped_samples"])),
        row("Crest factor (dB)", f1(ma["crest_db"]), f1(mb["crest_db"]), True),
        row("Correlación L/R <150 Hz", f2s(ma["corr150"]), f2s(mb["corr150"])),
        row("Side/Mid <150 Hz (dB)", f1(ma["sm150"]), f1(mb["sm150"])),
        row("Sibilancia 5-9 kHz (dB)", f1(ma["sibilance_db"]), f1(mb["sibilance_db"])),
    ]
    d.table(cols, rows)
    lines = []
    if r.null:
        n = r.null
        lines.append("Desfase temporal entre fuentes: %d muestras (%s ms)" % (n["lag"], f2(n["lag_ms"])))
        lines.append("Ganancia necesaria para igualar: %s (%s dB)%s" % (
            ("%.4f" % abs(n["gain"])).replace(".", ","), f2(n["gain_db"]), ", polaridad invertida" if n["gain"] < 0 else ""))
        lines.append("Residuo tras la anulación: %s dBFS (%s dB respecto a la señal)" % (
            f1(n["residual_dbfs"]), f1(n["residual_rel_db"])))
    else:
        lines.append("No se ha podido hacer la anulación: frecuencia de muestreo o canales distintos.")
    lines.append("Muestras PCM idénticas (MD5): %s  ·  Archivos byte a byte idénticos: %s" % (
        "SÍ" if r.identical_pcm else "NO", "SÍ" if r.identical_bytes else "NO"))
    d.box("TEST DE ANULACIÓN — resultado", lines, RED)

    d.need(150)
    top = d.y
    y1 = d.bars("Loudness integrado", [r.label_a, r.label_b], [ma["lufs"], mb["lufs"]], "LUFS",
                target=-12.0, target_label="objetivo vinilo")
    d.y = top
    y2 = d.bars("Rango dinámico (crest)", [r.label_a, r.label_b], [ma["crest_db"], mb["crest_db"]], "dB",
                target=14.0, target_label="objetivo vinilo", x0=MARGIN + CONTENT_W / 2 + 10)
    d.y = min(y1, y2) - 6
    d.note("Metodología: loudness ITU-R BS.1770-4, RMS, pico de muestra y pico real sobremuestreado x4, muestras a "
           "fondo de escala y tramos planos, crest factor, correlación de fase y Side/Mid por debajo de 150 Hz. "
           "Test de anulación con alineación temporal por correlación cruzada y ajuste de ganancia por mínimos "
           "cuadrados; comparación directa de las muestras PCM (MD5) y de los bytes del archivo.")
    return d.finish()


def write_pdf(r, path):
    c = PdfCanvas()
    layout(r, c)
    c.save(path, TITLE)
