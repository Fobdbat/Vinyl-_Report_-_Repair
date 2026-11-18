# -*- coding: utf-8 -*-
"""Reparació del premàster: declip, mono en graves, de-esser i headroom d'àlbum.

Dues passades: (1) processos per tema i pic real resultant; (2) guany uniforme
per a tot el disc (balanç entre temes intacte), quantització amb dither TPDF i
mesura final. Els temes que no cal tocar es copien bit a bit.
"""
import datetime
import os
import shutil
import tempfile

import numpy as np

from . import dsp
from .analysis import classify, RANK, f1, f2s, join_es
from .audio_io import read_audio, write_audio, output_bits, same_path


class RepairSettings(object):
    def __init__(self, out_dir, tp_target=-3.0, out_bits="same", deess_target=-9.0, bass_fc=150.0):
        self.out_dir = out_dir
        self.tp_target = tp_target
        self.out_bits = out_bits
        self.deess_target = deess_target
        self.bass_fc = bass_fc


class TrackRepair(object):
    def __init__(self, t):
        self.t = t
        self.done = []        # textos del que s'ha fet
        self.not_done = []    # textos del que no s'ha pogut fer o queda pendent
        self.out_path = None
        self.bit_exact = False
        self.m_after = None
        self.status_after = {}
        self.verdict = "apto"
        self.reasons = []
        self.processed = False
        self.out_bits = None
        self.declip_fixed = 0


class RepairResult(object):
    def __init__(self, analysis, settings):
        self.analysis = analysis
        self.settings = settings
        self.tracks = []
        self.gain_db = 0.0
        self.album_tp_before = None
        self.album_tp_after = None
        self.peak_track = None
        self.date = datetime.datetime.now()
        self.cancelled = False

    def overall(self):
        order = {"apto": 0, "reservas": 1, "no_apto": 2}
        worst = max([order[r.verdict] for r in self.tracks] or [0])
        return {0: "apto", 1: "reservas", 2: "no_apto"}[worst]


def default_out_dir(analysis):
    if not analysis.tracks:
        return ""
    base = os.path.dirname(os.path.abspath(analysis.tracks[0].path))
    return os.path.join(base, "Premaster_vinilo")


def _verdict(r, limits):
    st = r.status_after
    m = r.m_after
    red, res = [], []
    if st["fs"] == "red":
        red.append("sigue habiendo clipping (%d muestras en tramos planos)" % m["clipped_samples"])
    if st["tp"] == "red":
        red.append("pico real en %s dBTP" % f1(m["tp_db"]))
    if st["corr"] == "red" or st["sm"] == "red":
        red.append("graves abiertos (corr. %s; Side/Mid %s dB)" % (f2s(m["corr150"]), f1(m["sm150"])))
    if st["sib"] == "red":
        red.append("sibilancia alta (%s dB)" % f1(m["sibilance_db"]))
    if st["crest"] != "ok" or st["lufs"] != "ok":
        res.append("dinámica limitada (crest %s dB): no recuperable en el premáster" % f1(m["crest_db"]))
    if st["tp"] == "yellow":
        res.append("pico real en %s dBTP" % f1(m["tp_db"]))
    if st["corr"] == "yellow" or st["sm"] == "yellow":
        res.append("graves algo anchos: comprobar en corte de prueba")
    if st["sib"] == "yellow":
        res.append("sibilancia moderada (%s dB)" % f1(m["sibilance_db"]))
    if r.declip_fixed:
        res.append("declip: reconstrucción/mitigación, no recupera el original")
    if red:
        return "no_apto", red + res
    if res:
        return "reservas", res
    return "apto", []


def run_repair(analysis, plan, settings, progress=None, cancelled=None):
    """plan: {track_id: {'declip': bool, 'bass_mono': bool, 'deess': bool}}"""
    res = RepairResult(analysis, settings)
    limits = analysis.limits
    tracks = [t for t in analysis.tracks if t.ok]
    if not tracks:
        return res
    out_dir = settings.out_dir
    for t in tracks:
        if same_path(os.path.dirname(os.path.abspath(t.path)), out_dir):
            raise ValueError("La carpeta de salida no puede ser la de los originales.")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    tmp = tempfile.mkdtemp(prefix="premaster_")
    steps = 2 * len(tracks)
    try:
        # ---------------- passada 1: processos per tema
        tp1 = {}
        cache = {}
        reps = []
        for k, t in enumerate(tracks):
            if cancelled and cancelled():
                res.cancelled = True
                return res
            if progress:
                progress(k, steps, "Procesando %s %s" % (t.pos, t.title))
            r = TrackRepair(t)
            acts = plan.get(t.id, {})
            x, info = read_audio(t.path)
            fs = info.fs
            y = x
            if acts.get("declip") and t.m["clipped_samples"] > 0:
                y, fixed, skipped = dsp.declip(y)
                r.declip_fixed = fixed
                if fixed:
                    r.done.append("declip (%d muestras reconstruidas)" % fixed)
                    r.processed = True
                if skipped:
                    r.not_done.append("declip: %d tramos demasiado largos no se han reconstruido" % skipped)
            elif t.m["clipped_samples"] > 0:
                r.not_done.append("clipping de origen sin tratar (declip desactivado)")
            bstat = max(RANK[t.status["corr"]], RANK[t.status["sm"]])
            if acts.get("bass_mono") and x.shape[1] >= 2:
                y = dsp.bass_mono(y, fs, settings.bass_fc)
                r.processed = True
                r._bass = True
                r.done.append("mono en graves < %d Hz" % int(settings.bass_fc))
            elif bstat == 2:
                r.not_done.append("graves anchos sin corregir (mono en graves desactivado)")
            if acts.get("deess"):
                before = dsp.sibilance_db(y, fs)
                y2, after, red = dsp.deess(y, fs, settings.deess_target)
                if red > 0.05:
                    y = y2
                    r.processed = True
                    kind = "marcado" if before > limits["sib_red"] else "suave"
                    r.done.append("de-esser %s (sibilancia %s -> %s dB)" % (kind, f1(before), f1(after)))
                    if after > settings.deess_target + 0.5:
                        r.not_done.append("de-esser: no se ha llegado al objetivo (%s dB; máx. 12 dB de reducción)"
                                          % f1(after))
            elif RANK[t.status["sib"]] == 2:
                r.not_done.append("sibilancia alta sin tratar (de-esser desactivado)")
            if info.is_float:
                r.processed = True
            tp1[t.id] = dsp.true_peak(y, fs)
            if r.processed:
                p = os.path.join(tmp, "%d.npy" % t.id)
                np.save(p, y)
                cache[t.id] = p
            del x, y
            reps.append(r)

        # ---------------- guany d'àlbum
        album_tp = max(tp1.values())
        res.album_tp_before = dsp.to_db(album_tp)
        res.peak_track = next(r.t for r in reps if tp1[r.t.id] == album_tp)
        gain = min(0.0, settings.tp_target - dsp.to_db(album_tp))
        res.gain_db = gain

        # ---------------- passada 2: escriure i mesurar
        for k, r in enumerate(reps):
            t = r.t
            if cancelled and cancelled():
                res.cancelled = True
                return res
            if progress:
                progress(len(tracks) + k, steps, "Escribiendo %s %s" % (t.pos, t.title))
            info = t.info
            bits = output_bits(info, settings.out_bits)
            r.out_bits = bits
            out = os.path.join(out_dir, os.path.basename(t.path))
            r.out_path = out
            if not r.processed and abs(gain) < 1e-9 and info.is_pcm and bits == info.bits:
                shutil.copy2(t.path, out)
                r.bit_exact = True
                clipped_after = None
            else:
                y = np.load(cache[t.id]) if t.id in cache else read_audio(t.path)[0]
                if gain < 0:
                    y = dsp.apply_gain_db(y, gain)
                # El clipping que quedi es mesura abans del dither (després ja no hi ha trams idèntics)
                clipped_after = dsp.clip_stats(y, 0, True)[1]
                write_audio(out, y, info.fs, bits, seed=k + 1)
                del y
            if gain < 0:
                r.done.append("headroom (%s dB)" % f1(gain))
            y2, info2 = read_audio(out)
            r.m_after = dsp.measure(y2, info2.fs, info2.bits, info2.is_float)
            del y2
            if clipped_after is not None:
                r.m_after["clipped_samples"] = clipped_after
            r.status_after, _ = classify(r.m_after, limits, t.inner)
            if getattr(r, "_bass", False) and t.m["corr150"] is not None:
                for i, d in enumerate(r.done):
                    if d.startswith("mono en graves"):
                        r.done[i] = "mono en graves < %d Hz (corr. %s -> %s; S/M %s -> %s dB)" % (
                            int(settings.bass_fc), f2s(t.m["corr150"]), f2s(r.m_after["corr150"]),
                            f1(t.m["sm150"]), f1(r.m_after["sm150"]))
            if r.status_after.get("crest") != "ok":
                r.not_done.append("dinámica (crest %s dB): no se puede recuperar; lo ideal es un premáster "
                                  "sin limitador" % f1(r.m_after["crest_db"]))
            r.verdict, r.reasons = _verdict(r, limits)
            res.tracks.append(r)
        res.album_tp_after = max(r.m_after["tp_db"] for r in res.tracks)
        if progress:
            progress(steps, steps, "")
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def actions_line(r):
    if r.bit_exact:
        return "sin cambios (copia idéntica)"
    if not r.done:
        return "solo conversión de formato" if r.t.info.is_float else "sin cambios"
    return " + ".join(r.done)


VERDICT_TEXT = {"apto": "APTO PARA FÁBRICA", "reservas": "APTO CON RESERVAS", "no_apto": "NO APTO"}


def summary_sentence(res):
    v = res.overall()
    n = len(res.tracks)
    if v == "apto":
        return "Los %d temas cumplen los valores de referencia para corte." % n
    if v == "reservas":
        return ("Se puede enviar a fábrica: no quedan problemas críticos, pero hay aspectos que el premáster no "
                "puede corregir (ver reservas).")
    bad = [r.t.pos for r in res.tracks if r.verdict == "no_apto"]
    return "Quedan problemas críticos en %s: revisar antes de enviar a fábrica." % join_es(bad)
