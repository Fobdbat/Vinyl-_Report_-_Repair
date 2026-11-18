# -*- coding: utf-8 -*-
"""Lectura i escriptura de WAV (libsndfile via soundfile)."""
import os

import numpy as np
import soundfile as sf

from . import dsp

SUBTYPE_BITS = {"PCM_U8": 8, "PCM_S8": 8, "PCM_16": 16, "PCM_24": 24, "PCM_32": 32,
                "FLOAT": 32, "DOUBLE": 64}


class AudioInfo(object):
    def __init__(self, fs, channels, frames, subtype):
        self.fs = fs
        self.channels = channels
        self.frames = frames
        self.subtype = subtype
        self.bits = SUBTYPE_BITS.get(subtype, 0)
        self.is_float = subtype in ("FLOAT", "DOUBLE")
        self.is_pcm = subtype.startswith("PCM")

    @property
    def duration(self):
        return self.frames / float(self.fs) if self.fs else 0.0

    def describe(self):
        if self.is_float:
            kind = "coma flotante"
        elif self.is_pcm:
            kind = "entero"
        else:
            kind = self.subtype
        return "%s bit %s / %s kHz" % (self.bits or "?", kind, fmt_khz(self.fs))


def fmt_khz(fs):
    k = fs / 1000.0
    return ("%d" % k) if abs(k - round(k)) < 1e-9 else ("%.1f" % k).replace(".", ",")


def read_info(path):
    i = sf.info(path)
    return AudioInfo(i.samplerate, i.channels, i.frames, i.subtype)


def read_audio(path):
    data, fs = sf.read(path, dtype="float64", always_2d=True)
    return data, read_info(path)


def output_bits(info, mode):
    """mode: 'same' (igual que l'original) o 24."""
    if mode == 24 or mode == "24":
        return 24
    if info.is_pcm and info.bits in (16, 24):
        return info.bits
    return 24


def write_audio(path, y, fs, bits, seed=0):
    q = dsp.quantize(y, bits, seed=seed)
    size = q.shape[0] * q.shape[1] * (bits // 8)
    fmt = "RF64" if size > 4000000000 else "WAV"
    sf.write(path, q, fs, subtype="PCM_16" if bits == 16 else "PCM_24", format=fmt)


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
