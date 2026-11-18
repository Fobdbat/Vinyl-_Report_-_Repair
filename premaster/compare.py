# -*- coding: utf-8 -*-
"""Comparació de dues versions d'un mateix tema (test d'anul·lació)."""
import datetime
import filecmp
import hashlib
import os

import numpy as np

from . import dsp
from .analysis import f1
from .audio_io import read_audio


class CompareResult(object):
    pass


def compare_files(path_a, path_b, label_a="Versión A", label_b="Versión B"):
    a, ia = read_audio(path_a)
    b, ib = read_audio(path_b)
    r = CompareResult()
    r.date = datetime.datetime.now()
    r.path_a, r.path_b = path_a, path_b
    r.label_a, r.label_b = label_a, label_b
    r.info_a, r.info_b = ia, ib
    r.m_a = dsp.measure(a, ia.fs, ia.bits, ia.is_float)
    r.m_b = dsp.measure(b, ib.fs, ib.bits, ib.is_float)
    r.same_fs = ia.fs == ib.fs
    r.identical_bytes = os.path.getsize(path_a) == os.path.getsize(path_b) and filecmp.cmp(path_a, path_b, shallow=False)
    r.identical_pcm = a.shape == b.shape and bool(np.array_equal(a, b))
    r.md5_a = hashlib.md5(np.ascontiguousarray(a).tobytes()).hexdigest()
    r.md5_b = hashlib.md5(np.ascontiguousarray(b).tobytes()).hexdigest()
    r.null = dsp.null_test(a, b, ia.fs) if r.same_fs and a.shape[1] == b.shape[1] else None
    r.conclusion, r.detail = conclusion(r)
    return r


def conclusion(r):
    if r.identical_bytes:
        return ("Los dos archivos son idénticos byte a byte: es el mismo máster.",
                "No hay ninguna diferencia de audio ni de cabecera.")
    if r.identical_pcm:
        return ("Las muestras de audio son idénticas: es el mismo máster.",
                "Solo cambian la cabecera o los metadatos del archivo.")
    if r.null is None:
        return ("No se pueden anular: frecuencia de muestreo o número de canales distintos.",
                "Se comparan solo las mediciones.")
    n = r.null
    lag_txt = "desfase de %d muestras (%s ms)" % (n["lag"], f1(n["lag_ms"])) if n["lag"] else "sin desfase"
    gain_txt = "diferencia de nivel de %s dB" % f1(n["gain_db"]) if abs(n["gain_db"]) > 0.01 else "mismo nivel"
    pol = " y polaridad invertida" if n["gain"] < 0 else ""
    if n["residual_dbfs"] < -120:
        return ("Es el mismo audio: %s, %s%s." % (lag_txt, gain_txt, pol),
                "Tras alinear y ajustar el nivel, el residuo es %s dBFS (anulación total)." % f1(n["residual_dbfs"]))
    if n["residual_rel_db"] < -75:
        return ("Es el mismo audio: %s, %s%s; solo cambia la cuantización (bits/dither)." % (lag_txt, gain_txt, pol),
                "El residuo queda %s dB por debajo de la señal (%s dBFS), al nivel del ruido de cuantización."
                % (f1(-n["residual_rel_db"]), f1(n["residual_dbfs"])))
    if n["residual_rel_db"] < -40:
        return ("Versiones muy parecidas (%s, %s%s)." % (lag_txt, gain_txt, pol),
                "El residuo queda %s dB por debajo de la señal: procesado ligero (dither, EQ suave o similar)."
                % f1(-n["residual_rel_db"]))
    return ("Son másters distintos (%s, %s%s)." % (lag_txt, gain_txt, pol),
            "El residuo solo queda %s dB por debajo de la señal: hay procesado diferente (nivel, limitación, EQ)."
            % f1(-n["residual_rel_db"]))
