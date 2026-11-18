# -*- coding: utf-8 -*-
"""Mesures i processos d'àudio per a premàster de vinil.

Totes les funcions treballen amb arrays numpy de forma (mostres, canals) en
coma flotant, escala de fons d'escala = 1.0 (convenció de libsndfile).
Compatible amb numpy 1.24 / scipy 1.10 (Python 3.8).
"""
import math

import numpy as np
from scipy import signal
from scipy.interpolate import CubicSpline
from scipy.ndimage import minimum_filter1d

EPS = 1e-20
FLOOR_DB = -240.0


def to_db(lin):
    return 20.0 * math.log10(lin) if lin > EPS else FLOOR_DB


def pow_db(p):
    return 10.0 * math.log10(p) if p > EPS else FLOOR_DB


# --------------------------------------------------------------------------
# Loudness (ITU-R BS.1770-4 / EBU R128)
# --------------------------------------------------------------------------
def k_weighting_sos(fs):
    """Filtre de ponderació K per a qualsevol freqüència (coeficients de libebur128)."""
    f0, G, Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    K = math.tan(math.pi * f0 / fs)
    Vh = 10.0 ** (G / 20.0)
    Vb = Vh ** 0.4996667741545416
    a0 = 1.0 + K / Q + K * K
    shelf = [(Vh + Vb * K / Q + K * K) / a0, 2.0 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0,
             1.0, 2.0 * (K * K - 1.0) / a0, (1.0 - K / Q + K * K) / a0]
    f0, Q = 38.13547087602444, 0.5003270373238773
    K = math.tan(math.pi * f0 / fs)
    d = 1.0 + K / Q + K * K
    hp = [1.0, -2.0, 1.0, 1.0, 2.0 * (K * K - 1.0) / d, (1.0 - K / Q + K * K) / d]
    return np.array([shelf, hp])


def integrated_lufs(x, fs):
    n = x.shape[0]
    block = int(round(0.4 * fs))
    hop = int(round(0.1 * fs))
    if n < block:
        return FLOOR_DB
    y = signal.sosfilt(k_weighting_sos(fs), x[:, :2], axis=0)
    cs = np.vstack([np.zeros((1, y.shape[1])), np.cumsum(y * y, axis=0)])
    starts = np.arange(0, n - block + 1, hop)
    ms = (cs[starts + block] - cs[starts]) / block
    z = ms.sum(axis=1)
    with np.errstate(divide="ignore"):
        lk = -0.691 + 10.0 * np.log10(np.maximum(z, EPS))
    above = z[lk > -70.0]
    if above.size == 0:
        return FLOOR_DB
    rel = -0.691 + 10.0 * math.log10(above.mean()) - 10.0
    gated = z[(lk > -70.0) & (lk > rel)]
    if gated.size == 0:
        return FLOOR_DB
    return -0.691 + 10.0 * math.log10(gated.mean())


# --------------------------------------------------------------------------
# Pics
# --------------------------------------------------------------------------
def oversampling_factor(fs):
    if fs <= 48000:
        return 4
    if fs <= 96000:
        return 2
    return 1


def true_peak(x, fs, chunk=1 << 18):
    """Pic real (lineal) amb sobremostreig (x4 fins a 48 kHz, x2 fins a 96 kHz)."""
    factor = oversampling_factor(fs)
    if factor == 1:
        return float(np.max(np.abs(x))) if x.size else 0.0
    pad = 256
    n = x.shape[0]
    peak = 0.0
    for c in range(x.shape[1]):
        col = x[:, c]
        for s in range(0, n, chunk):
            a = max(0, s - pad)
            b = min(n, s + chunk + pad)
            up = signal.resample_poly(col[a:b], factor, 1)
            lo = (s - a) * factor
            hi = lo + (min(n, s + chunk) - s) * factor
            m = float(np.max(np.abs(up[lo:hi]))) if hi > lo else 0.0
            if m > peak:
                peak = m
    return peak


def full_scale_threshold(bits, is_float):
    if is_float or not bits:
        return 1.0 - 1e-6
    return (2.0 ** (bits - 1) - 1.0) / 2.0 ** (bits - 1) - 1e-9


def _runs(mask, min_run):
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return [(int(s), int(e)) for s, e in zip(starts, ends) if e - s >= min_run]


def clip_segments(col, min_run=3, min_level=0.5):
    """Trams plans: 'min_run' o més mostres consecutives idèntiques al valor màxim
    (o mínim) del canal. És la marca del clipping digital, sigui o no a fons d'escala."""
    if not col.size:
        return []
    segs = []
    hi = float(col.max())
    lo = float(col.min())
    if hi >= min_level:
        segs += _runs(col >= hi - 1e-9, min_run)
    if -lo >= min_level:
        segs += _runs(col <= lo + 1e-9, min_run)
    return sorted(segs)


def clip_stats(x, bits, is_float):
    thr = full_scale_threshold(bits, is_float)
    fs_count = int(np.count_nonzero(np.abs(x) >= thr))
    segs = []
    for c in range(x.shape[1]):
        segs.append(clip_segments(x[:, c]))
    clipped = sum(e - s for ch in segs for s, e in ch)
    return fs_count, clipped, segs


# --------------------------------------------------------------------------
# Graves (estèreo per sota de 150 Hz) i sibilància
# --------------------------------------------------------------------------
def low_band_stereo(x, fs, fc=150.0):
    """(correlació L/R, energia Side/Mid en dB) per sota de fc. Mono -> (1.0, None)."""
    if x.shape[1] < 2:
        return 1.0, None
    sos = signal.butter(4, fc, "low", fs=fs, output="sos")
    y = signal.sosfilt(sos, x[:, :2], axis=0)
    L, R = y[:, 0], y[:, 1]
    ll = float(np.dot(L, L))
    rr = float(np.dot(R, R))
    total = float(np.sum(x[:, :2] * x[:, :2]))
    if total <= EPS or (ll + rr) / total < 1e-5:   # pràcticament sense greus (< -50 dB)
        return None, None
    lr = float(np.dot(L, R))
    corr = lr / math.sqrt(ll * rr) if ll > EPS and rr > EPS else 1.0
    M = 0.5 * (L + R)
    S = 0.5 * (L - R)
    mm = float(np.dot(M, M))
    ss = float(np.dot(S, S))
    sm = pow_db(ss / mm) if mm > EPS else FLOOR_DB
    return corr, sm


def sibilance_band(fs):
    hi = min(9000.0, 0.45 * fs)
    lo = min(5000.0, hi * 0.6)
    return lo, hi


def sibilance_db(x, fs, win_s=0.05):
    """Pic d'energia 5–9 kHz en finestres de 50 ms respecte de l'RMS global de la mescla (dB)."""
    mid = x.mean(axis=1)
    lo, hi = sibilance_band(fs)
    band = signal.sosfilt(signal.butter(4, [lo, hi], "band", fs=fs, output="sos"), mid)
    win = max(1, int(round(win_s * fs)))
    hop = max(1, win // 2)
    if band.size < win:
        return FLOOR_DB
    cs = np.concatenate([[0.0], np.cumsum(band * band)])
    starts = np.arange(0, band.size - win + 1, hop)
    ms = (cs[starts + win] - cs[starts]) / win
    overall = float(np.mean(mid * mid))
    if overall <= EPS:
        return FLOOR_DB
    return pow_db(float(ms.max()) / overall)


# --------------------------------------------------------------------------
# Mesures completes d'un tema
# --------------------------------------------------------------------------
def measure(x, fs, bits=24, is_float=False):
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    rms = math.sqrt(float(np.mean(x * x))) if x.size else 0.0
    tp = true_peak(x, fs)
    fs_count, clipped, _segs = clip_stats(x, bits, is_float)
    corr, sm = low_band_stereo(x, fs)
    return {
        "duration": x.shape[0] / float(fs),
        "lufs": integrated_lufs(x, fs),
        "peak_db": to_db(peak),
        "tp_db": to_db(tp),
        "rms_db": to_db(rms),
        "crest_db": to_db(peak) - to_db(rms) if rms > EPS else 0.0,
        "fs_samples": fs_count,
        "clipped_samples": clipped,
        "corr150": corr,
        "sm150": sm,
        "sibilance_db": sibilance_db(x, fs),
        "channels": x.shape[1],
    }


# --------------------------------------------------------------------------
# Processos de reparació
# --------------------------------------------------------------------------
def bass_mono(x, fs, fc=150.0):
    """Graves en mono: passaaltes de fase zero només al canal Side. El Mid queda intacte."""
    if x.shape[1] < 2:
        return x.copy()
    L, R = x[:, 0], x[:, 1]
    M = 0.5 * (L + R)
    S = 0.5 * (L - R)
    sos = signal.butter(4, fc, "high", fs=fs, output="sos")
    S2 = signal.sosfiltfilt(sos, S)
    y = x.copy()
    y[:, 0] = M + S2
    y[:, 1] = M - S2
    return y


def deess(x, fs, target_db, max_reduction_db=12.0, iterations=5):
    """De-esser de banda partida (5–9 kHz), de fase zero, amb objectiu en dB (mateixa mètrica que l'anàlisi).

    Retorna (senyal, sibilància final en dB, reducció màxima aplicada en dB).
    """
    lo, hi = sibilance_band(fs)
    sos = signal.butter(4, [lo, hi], "band", fs=fs, output="sos")
    band = signal.sosfiltfilt(sos, x, axis=0)
    rest = x - band
    det = band.mean(axis=1)
    mid = x.mean(axis=1)
    overall = math.sqrt(float(np.mean(mid * mid)))
    if overall <= EPS:
        return x.copy(), sibilance_db(x, fs), 0.0
    w = max(1, int(round(0.005 * fs)))
    env = np.sqrt(np.maximum(np.convolve(det * det, np.ones(w) / w, mode="same"), EPS))
    smooth = signal.butter(2, 40.0, "low", fs=fs, output="sos")
    g_min = 10.0 ** (-max_reduction_db / 20.0)
    thr_db = target_db
    y = x
    current = sibilance_db(x, fs)
    if current <= target_db:
        return x.copy(), current, 0.0
    gain = np.ones_like(env)
    for _ in range(iterations):
        thr = overall * 10.0 ** (thr_db / 20.0)
        g = np.clip(thr / env, g_min, 1.0)
        g = minimum_filter1d(g, size=max(3, int(0.004 * fs)))
        g = np.clip(signal.sosfiltfilt(smooth, g), g_min, 1.0)
        y = rest + band * g[:, None]
        current = sibilance_db(y, fs)
        gain = g
        if current <= target_db + 0.25:
            break
        thr_db -= (current - target_db)
    return y, current, -to_db(float(gain.min()))


def declip(x, max_run=48, context=8, max_over_db=3.0):
    """Reconstrueix els trams plans per interpolació cúbica local.

    El pic reconstruït es limita a 'max_over_db' per sobre del tram pla, i els trams
    de més de 'max_run' mostres no es toquen (la reconstrucció no seria fiable).
    Retorna (senyal, mostres reconstruïdes, trams no tractats)."""
    k_over = 10.0 ** (max_over_db / 20.0)
    y = x.copy()
    fixed = 0
    skipped = 0
    n = x.shape[0]
    for c in range(x.shape[1]):
        col = y[:, c]
        segs = clip_segments(x[:, c])
        if not segs:
            continue
        bad = np.zeros(n, dtype=bool)
        for s, e in segs:
            bad[s:e] = True
        for s, e in segs:
            if e - s > max_run:
                skipped += 1
                continue
            left = [i for i in range(s - 1, max(-1, s - 4 * context), -1) if not bad[i]][:context][::-1]
            right = [i for i in range(e, min(n, e + 4 * context)) if not bad[i]][:context]
            if len(left) < 3 or len(right) < 3:
                skipped += 1
                continue
            idx = np.array(left + right)
            cs = CubicSpline(idx, x[idx, c])
            seg = np.arange(s, e)
            sign = 1.0 if x[s, c] > 0 else -1.0
            level = abs(float(x[s, c]))
            est = np.clip(cs(seg), -level * k_over, level * k_over)
            extreme = float(est.max()) if sign > 0 else -float(est.min())
            # Només s'accepta si el pic reconstruït supera el tram pla en el mateix sentit
            if extreme > level:
                col[s:e] = np.where(sign * est > level, est, x[s:e, c])
                fixed += e - s
            else:
                skipped += 1
    return y, fixed, skipped


def apply_gain_db(x, gain_db):
    return x * (10.0 ** (gain_db / 20.0))


def quantize(x, bits, seed=0):
    """Quantitza a enter de 'bits' amb dither TPDF. Retorna array int16 (16 bits) o int32 (24 bits, alineat a 32)."""
    scale = float(2 ** (bits - 1))
    rng = np.random.RandomState(seed)
    tpdf = rng.random_sample(x.shape) - rng.random_sample(x.shape)
    q = np.floor(x * scale + tpdf + 0.5)
    q = np.clip(q, -scale, scale - 1)
    if bits == 16:
        return q.astype(np.int16)
    return (q.astype(np.int32) << (32 - bits))


# --------------------------------------------------------------------------
# Comparació de dues versions (test d'anul·lació)
# --------------------------------------------------------------------------
def align_lag(a, b, fs, seconds=10.0, max_shift_s=2.0):
    """Desfasament (mostres) de b respecte d'a: a[i] correspon a b[i + lag]."""
    ma = a.mean(axis=1)
    mb = b.mean(axis=1)
    n = int(min(seconds * fs, len(ma)))
    if n < 64 or len(mb) < 64:
        return 0
    start = 0
    if len(ma) > n:
        cs = np.concatenate([[0.0], np.cumsum(ma * ma)])
        starts = np.arange(0, len(ma) - n + 1, max(1, n // 4))
        start = int(starts[np.argmax(cs[starts + n] - cs[starts])])
    seg_a = ma[start:start + n]
    m = int(max_shift_s * fs)
    b0 = max(0, start - m)
    b1 = min(len(mb), start + n + m)
    seg_b = mb[b0:b1]
    if len(seg_b) < n:
        return 0
    c = signal.correlate(seg_b, seg_a, mode="valid", method="fft")
    k = int(np.argmax(np.abs(c)))
    return (b0 + k) - start


def null_test(a, b, fs):
    lag = align_lag(a, b, fs)
    if lag >= 0:
        bb = b[lag:]
        aa = a
    else:
        aa = a[-lag:]
        bb = b
    n = min(len(aa), len(bb))
    ch = min(aa.shape[1], bb.shape[1])
    aa = aa[:n, :ch]
    bb = bb[:n, :ch]
    den = float(np.sum(bb * bb))
    g = float(np.sum(aa * bb)) / den if den > EPS else 1.0
    res = aa - g * bb
    res_ms = float(np.mean(res * res)) if res.size else 0.0
    sig_ms = float(np.mean(aa * aa)) if aa.size else 0.0
    return {
        "lag": lag,
        "lag_ms": 1000.0 * lag / fs,
        "gain": g,
        "gain_db": to_db(abs(g)) if g != 0 else FLOOR_DB,
        "residual_dbfs": pow_db(res_ms),
        "residual_rel_db": pow_db(res_ms / sig_ms) if sig_ms > EPS else FLOOR_DB,
        "compared_samples": n,
    }
