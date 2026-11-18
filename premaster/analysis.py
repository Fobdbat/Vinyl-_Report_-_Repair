# -*- coding: utf-8 -*-
"""Anàlisi d'idoneïtat de tall: mesures, classificació per llindars, posició a la cara
i textos del diagnòstic (en castellà, per als informes)."""
import datetime
import os

from . import dsp
from .audio_io import read_audio, fmt_khz

DEFAULT_LIMITS = {
    "tp_red": -1.0, "tp_yellow": -3.0,         # pic real (dBTP): per sobre -> problema
    "lufs_red": -9.0, "lufs_yellow": -12.0,    # loudness integrat (LUFS): per sobre -> problema
    "crest_red": 10.0, "crest_yellow": 14.0,   # crest (dB): per sota -> problema
    "corr_red": 0.60, "corr_yellow": 0.75,     # correlació L/R < 150 Hz: per sota -> problema
    "sm_red": -6.0, "sm_yellow": -8.0,         # Side/Mid < 150 Hz (dB): per sobre -> problema
    "sib_red": -3.0, "sib_yellow": -7.0,       # sibilància 5-9 kHz (dB): per sobre -> problema
    "inner_zone": 0.60,                        # fracció de la cara a partir de la qual és «zona interior»
    "tp_target": -3.0,                         # objectiu de headroom (dBTP)
    "deess_target": -9.0,                      # objectiu del de-esser (dB)
    "bass_fc": 150.0,                          # tall del mono en graves (Hz)
}

RANK = {"ok": 0, "yellow": 1, "red": 2}
METRICS = ("lufs", "tp", "fs", "crest", "corr", "sm", "sib")


# ------------------------------------------------------------------ format
def f1(v, unit=""):
    if v is None:
        return "—"
    if v <= dsp.FLOOR_DB + 1:
        return "-inf" + unit
    return ("%.1f" % v).replace(".", ",") + unit


def f2(v):
    if v is None:
        return "—"
    return ("%.2f" % v).replace(".", ",")


def f2s(v):
    if v is None:
        return "—"
    return ("%+.2f" % v).replace(".", ",")


def fdur(sec):
    s = int(round(sec))
    return "%d:%02d" % (s // 60, s % 60)


def join_es(items):
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " y " + items[-1]


# ------------------------------------------------------------------ resultat
class TrackResult(object):
    def __init__(self, item, side, index, n_side):
        self.item = item
        self.id = item.id
        self.path = item.path
        self.title = item.title
        self.side = side
        self.index = index
        self.pos = "%s%02d" % (side, index + 1)
        self.is_last = index == n_side - 1
        self.is_penultimate = index == n_side - 2
        self.inner = False
        self.info = None
        self.m = None
        self.error = None
        self.status = {}
        self.escalated = set()

    @property
    def ok(self):
        return self.m is not None

    def worst(self):
        return max([RANK[s] for s in self.status.values()] or [0])

    def position_text(self):
        if self.is_last:
            return "el final de cara %s" % self.side
        if self.is_penultimate:
            return "el penúltimo de cara %s" % self.side
        return "la zona interior de la cara %s" % self.side


def classify(m, limits, inner):
    L = limits
    st = {}
    tp = m["tp_db"]
    st["tp"] = "red" if tp > L["tp_red"] else ("yellow" if tp > L["tp_yellow"] else "ok")
    lufs = m["lufs"]
    st["lufs"] = "red" if lufs > L["lufs_red"] else ("yellow" if lufs > L["lufs_yellow"] else "ok")
    cr = m["crest_db"]
    st["crest"] = "red" if cr < L["crest_red"] else ("yellow" if cr < L["crest_yellow"] else "ok")
    st["fs"] = "red" if m["clipped_samples"] > 0 else ("yellow" if m["fs_samples"] > 0 else "ok")
    corr, sm = m["corr150"], m["sm150"]
    st["corr"] = "ok" if corr is None else ("red" if corr < L["corr_red"] else
                                            ("yellow" if corr < L["corr_yellow"] else "ok"))
    st["sm"] = "ok" if sm is None else ("red" if sm >= L["sm_red"] else ("yellow" if sm >= L["sm_yellow"] else "ok"))
    sib = m["sibilance_db"]
    st["sib"] = "red" if sib > L["sib_red"] else ("yellow" if sib > L["sib_yellow"] else "ok")
    escalated = set()
    if inner:
        for k in ("corr", "sm", "sib"):
            if st[k] == "yellow":
                st[k] = "red"
                escalated.add(k)
    return st, escalated


def bass_status(t):
    return max(RANK[t.status.get("corr", "ok")], RANK[t.status.get("sm", "ok")])


def suggested_actions(t, limits):
    """Proposta de reparació per defecte (editable a la interfície)."""
    if not t.ok:
        return {"declip": False, "bass_mono": False, "deess": False}
    return {
        "declip": t.m["clipped_samples"] > 0,
        "bass_mono": bass_status(t) == 2,
        "deess": RANK[t.status["sib"]] >= 1,
    }


# ------------------------------------------------------------------ anàlisi
class AnalysisResult(object):
    def __init__(self, project, limits):
        self.project = project
        self.limits = dict(limits)
        self.tracks = []
        self.date = datetime.datetime.now()

    @property
    def good(self):
        return [t for t in self.tracks if t.ok]

    def side_tracks(self, side):
        return [t for t in self.tracks if t.side == side]

    def source_folder(self):
        paths = [t.path for t in self.tracks]
        return os.path.basename(os.path.dirname(paths[0])) if paths else ""

    def formats(self):
        fm = []
        for t in self.good:
            d = t.info.describe()
            if d not in fm:
                fm.append(d)
        return fm


def analyze(project, limits=None, progress=None, cancelled=None):
    limits = dict(DEFAULT_LIMITS, **(limits or {}))
    res = AnalysisResult(project, limits)
    items = list(project.all())
    total = len(items)
    for k, (side, i, item) in enumerate(items):
        if cancelled and cancelled():
            break
        n_side = len(project.sides[side])
        t = TrackResult(item, side, i, n_side)
        if progress:
            progress(k, total, "%s %s" % (t.pos, t.title))
        try:
            x, info = read_audio(item.path)
            t.info = info
            t.m = dsp.measure(x, info.fs, info.bits, info.is_float)
            del x
        except Exception as exc:  # fitxer il·legible
            t.error = str(exc)
        res.tracks.append(t)
    reclassify(res, limits)
    if progress:
        progress(total, total, "")
    return res


def reclassify(res, limits):
    """Torna a aplicar llindars i zona interior sense tornar a mesurar."""
    res.limits = dict(DEFAULT_LIMITS, **limits)
    for side in res.project.names():
        st = res.side_tracks(side)
        total_s = sum(t.m["duration"] for t in st if t.ok) or 1.0
        acc = 0.0
        for t in st:
            d = t.m["duration"] if t.ok else 0.0
            mid = (acc + d / 2.0) / total_s
            t.inner = t.is_last or mid >= res.limits["inner_zone"]
            acc += d
    for t in res.tracks:
        if t.ok:
            t.status, t.escalated = classify(t.m, res.limits, t.inner)


# ------------------------------------------------------------------ textos
def track_heading(t, limits):
    if not t.ok:
        return "No se ha podido leer"
    parts = []
    if t.status["fs"] == "red":
        parts.append("pedir sin clipping")
    b = bass_status(t)
    if b == 2:
        parts.append("mono en graves")
    if t.status["sib"] == "red":
        parts.append("de-esser marcado" if t.m["sibilance_db"] > limits["sib_red"] else "de-esser")
    elif t.status["sib"] == "yellow":
        parts.append("de-esser suave")
    if b == 1:
        parts.append("vigilar graves")
    headroom = t.m["tp_db"] > limits["tp_target"]
    if headroom:
        parts.append("headroom")
    if not parts:
        return "Sin cambios."
    if parts == ["headroom"]:
        return "Solo headroom."
    s = " + ".join(parts)
    return s[0].upper() + s[1:] + "."


def track_advice(t, limits):
    if not t.ok:
        return ["El archivo no se ha podido leer (%s). Revisar que sea un WAV válido." % t.error]
    m = t.m
    out = []
    st = t.status
    if st["fs"] == "red":
        out.append("Viene con clipping real de origen (%d muestras en tramos planos): si es posible, pedir "
                   "una versión sin recortar; si no, se puede reconstruir (declip) como mitigación."
                   % m["clipped_samples"])
    elif st["fs"] == "yellow":
        out.append("Toca fondo de escala en %d muestras sueltas (sin tramos planos)." % m["fs_samples"])
    if st["sib"] == "red":
        out.append("Sibilancia %s (picos de 5-9 kHz a %s dB de la mezcla): %s"
                   % ("extrema" if m["sibilance_db"] > limits["sib_red"] else "elevada", f1(m["sibilance_db"]),
                      "es lo más urgente del tema." if m["sibilance_db"] > limits["sib_red"]
                      else "conviene de-esser."))
    elif st["sib"] == "yellow":
        out.append("Sibilancia moderada (%s dB): de-esser suave." % f1(m["sibilance_db"]))
    b = bass_status(t)
    if b == 2:
        out.append("Graves anchos/fuera de fase (corr. %s; Side/Mid %s dB): pasar a mono por debajo de ~%d Hz "
                   "antes de cortar." % (f2s(m["corr150"]), f1(m["sm150"]), int(limits["bass_fc"])))
    elif b == 1:
        out.append("Graves algo anchos (corr. %s; Side/Mid %s dB): vigilar; estrechar por debajo de ~120 Hz "
                   "si hace falta o comprobar en el corte de prueba." % (f2s(m["corr150"]), f1(m["sm150"])))
    elif m["corr150"] is None:
        out.append("Prácticamente sin graves por debajo de 150 Hz.")
    if t.inner and (b >= 1 or RANK[st["sib"]] >= 1):
        out.append("Es %s (diámetro interior), la zona más delicada del disco." % t.position_text())
    if st["crest"] == "red":
        out.append("Dinámica aplastada (crest %s dB): no se puede recuperar en el premáster." % f1(m["crest_db"]))
    elif st["crest"] == "yellow" and st["lufs"] != "ok":
        out.append("Máster comprimido (crest %s dB, %s LUFS)." % (f1(m["crest_db"]), f1(m["lufs"])))
    if m["tp_db"] > 0:
        out.append("Picos inter-muestra por encima de 0 dBTP (%s dBTP): rebajar y dejar %s dBTP."
                   % (f2(m["tp_db"]), f1(limits["tp_target"])))
    elif m["tp_db"] > limits["tp_target"]:
        out.append("Picos reales en %s dBTP: recuperar headroom (%s dBTP)." % (f2(m["tp_db"]), f1(limits["tp_target"])))
    if t.info.is_float:
        out.append("WAV en coma flotante: se entregará en entero (24 bits).")
    if not out or all(s.startswith("Picos reales") for s in out):
        clean = "Tema limpio en todos los parámetros."
        out = [clean + (" Únicamente margen de pico." if out else "")]
    return out


def executive_summary(res):
    """(frase inicial, [viñetas])"""
    L = res.limits
    good = res.good
    reds = [t for t in good if t.worst() == 2]
    yellows = [t for t in good if t.worst() == 1]
    bullets = []
    hr = [t for t in good if t.m["tp_db"] > L["tp_red"]]
    if hr:
        lo = min(t.m["tp_db"] for t in hr)
        hi = max(t.m["tp_db"] for t in hr)
        who = ("los %d temas" % len(good)) if len(hr) == len(good) else join_es(t.pos for t in hr)
        bullets.append(("Falta de headroom en %s." % who,
                        "Picos reales entre %s y %s dBTP. El corte necesita margen; hay que rebajar y dejar "
                        "los picos en -3/-6 dBTP." % (f2(lo), f2(hi))))
    cl = [t for t in good if t.status["fs"] == "red"]
    if cl:
        bullets.append(("Clipping real de origen en %s." % join_es(t.pos for t in cl),
                        "Tramos planos de muestras: %s ya viene%s recortado%s del máster."
                        % ("ese tema" if len(cl) == 1 else "esos temas", "" if len(cl) == 1 else "n",
                           "" if len(cl) == 1 else "s")))
    bass = [t for t in good if bass_status(t) == 2]
    if bass:
        txt = "Correlación por debajo de 150 Hz de %s, con energía Side/Mid de %s dB. Requieren mono en graves antes de cortar." % (
            join_es(f2s(t.m["corr150"]) for t in bass), join_es(f1(t.m["sm150"]) for t in bass))
        crit = [t for t in bass if t.is_last]
        if crit:
            txt += " El caso de %s es crítico por ser final de cara." % join_es(t.pos for t in crit)
        bullets.append(("Graves anchos / fuera de fase en %s." % join_es(t.pos for t in bass), txt))
    sib_r = [t for t in good if t.status["sib"] == "red"]
    sib_y = [t for t in good if t.status["sib"] == "yellow"]
    if sib_r or sib_y:
        head = "Sibilancia elevada en %s" % join_es(t.pos for t in (sib_r or sib_y))
        txt = ""
        if sib_r:
            txt = "Picos de agudos a %s dB de la mezcla" % join_es(f1(t.m["sibilance_db"]) for t in sib_r)
            if sib_y:
                txt += "; en menor grado en %s" % join_es(t.pos for t in sib_y)
            txt += ". Se doma con de-esser."
        else:
            txt = "Sibilancia moderada. Se doma con de-esser suave."
        bullets.append((head + ".", txt))
    comp = [t for t in good if t.status["lufs"] != "ok" or t.status["crest"] == "red"]
    if comp and len(comp) >= max(1, len(good) // 2):
        bullets.append(("Máster maximizado.",
                        "Entre %s y %s LUFS integrados, crest de %s a %s dB. La dinámica perdida no se recupera "
                        "en el premáster." % (f1(min(t.m["lufs"] for t in good)), f1(max(t.m["lufs"] for t in good)),
                                               f1(min(t.m["crest_db"] for t in good)),
                                               f1(max(t.m["crest_db"] for t in good)))))
    fl = [t for t in good if t.info.is_float]
    if fl:
        bullets.append(("WAV en coma flotante en %s." % join_es(t.pos for t in fl),
                        "No apto para fábrica tal cual: hay que entregarlo en entero (PCM)."))
    rates = sorted(set(t.info.fs for t in good))
    if len(rates) > 1:
        bullets.append(("Frecuencias de muestreo distintas.",
                        "Hay temas a %s kHz. Conviene unificar." % join_es(fmt_khz(r) for r in rates)))
    bad = [t for t in res.tracks if not t.ok]
    if bad:
        bullets.append(("Archivos ilegibles: %s." % join_es(t.pos for t in bad), "Revisar los archivos."))
    if reds:
        lead = ("El disco no debe enviarse a corte tal cual: se han detectado problemas que conviene resolver "
                "en un premáster específico de vinilo.")
    elif yellows:
        lead = "El disco es cortable con reservas: hay aspectos a vigilar."
    else:
        lead = "El disco es apto para corte: todos los parámetros están dentro de los valores de referencia."
    return lead, bullets


def global_diagnosis(res):
    good = res.good
    if not good:
        return "No hay temas analizables."
    L = res.limits
    lo_l = min(t.m["lufs"] for t in good)
    hi_l = max(t.m["lufs"] for t in good)
    lo_c = min(t.m["crest_db"] for t in good)
    hi_c = max(t.m["crest_db"] for t in good)
    s = "Loudness integrado entre %s y %s LUFS y crest de %s a %s dB. " % (f1(lo_l), f1(hi_l), f1(lo_c), f1(hi_c))
    if hi_l > L["lufs_yellow"]:
        s += ("Es un máster pensado para reproducción digital, no para corte: al cortarlo tan caliente aparece "
              "distorsión de trazado. ")
    else:
        s += "El nivel es adecuado para corte. "
    ok_bass = [t for t in good if bass_status(t) == 0]
    if len(ok_bass) >= len(good) * 2 / 3.0:
        s += "La mayoría de temas tienen los graves bien centrados. "
    else:
        s += "Varios temas tienen los graves abiertos o fuera de fase. "
    tp_all = all(t.m["tp_db"] > L["tp_red"] for t in good)
    if tp_all:
        s += "El margen de pico afecta a todos los temas."
    return s.strip()


def delivery_notes(res):
    L = res.limits
    good = res.good
    notes = [("Origen ideal.", "Pedir un premáster de vinilo con la fase final de loudness retirada o muy relajada, "
                               "a 24 bits y frecuencia nativa, con picos reales en -3/-6 dBTP y crest > 14 dB.")]
    acts = []
    if any(t.m["tp_db"] > L["tp_target"] for t in good):
        acts.append("rebajar nivel para recuperar margen de pico")
    bass = [t.pos for t in good if bass_status(t) == 2]
    if bass:
        acts.append("mono en graves en %s" % join_es(bass))
    sib = [t.pos for t in good if RANK[t.status["sib"]] >= 1]
    if sib:
        acts.append("de-esser en %s" % join_es(sib))
    cl = [t.pos for t in good if t.status["fs"] == "red"]
    if cl:
        acts.append("declip en %s (o pedir copia sin clipping)" % join_es(cl))
    if acts:
        notes.append(("Si solo hay este máster.", "Reprocesar: " + "; ".join(acts) + "."))
    ends = [t for t in good if t.is_last and (bass_status(t) >= 1 or RANK[t.status["sib"]] >= 1)]
    if ends:
        notes.append(("Secuenciación.", "Punto delicado: %s al final de cara. Lo resuelven los ajustes propuestos o "
                                        "un cambio de orden." % join_es(t.pos for t in ends)))
    else:
        notes.append(("Secuenciación.", "Correcta en lo esencial: ningún tema problemático cae al final de cara."))
    notes.append(("Entrega.", "Un WAV por tema, con cabecera, sin normalizar, indicando orden de caras y duraciones."))
    return notes


METHODOLOGY = ("Mediciones: loudness ITU-R BS.1770-4 (LUFS integrado), pico real sobremuestreado x4 (dBTP), "
               "muestras a fondo de escala y tramos planos (clipping), crest factor (pico/RMS), correlación de fase "
               "y energía Side/Mid por debajo de 150 Hz (Butterworth 4.º orden), energía de sibilancia 5-9 kHz "
               "(pico de ventana de 50 ms respecto al RMS de la mezcla).")
