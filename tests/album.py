# -*- coding: utf-8 -*-
"""Disc de prova sintètic amb problemes coneguts (com un màster de CD portat a vinil)."""
import os

import numpy as np
import soundfile as sf
from scipy import signal

FS = 44100


def music(seconds, seed, wide_bass=0.0, sib=0.0, fs=FS):
    rng = np.random.RandomState(seed)
    n = int(seconds * fs)
    t = np.arange(n) / float(fs)
    beat = (t * 2.0) % 1.0
    kick = np.sin(2 * np.pi * 55 * t) * np.exp(-beat * 6.0) * 0.8
    chord = sum(np.sin(2 * np.pi * f * t + rng.rand() * 6) for f in (220, 277, 330, 440)) * 0.12
    hats = signal.sosfilt(signal.butter(2, 8000, "high", fs=fs, output="sos"), rng.randn(n)) * 0.05 * (beat < 0.1)
    mid = kick + chord + hats
    side = signal.sosfilt(signal.butter(2, [800, 6000], "band", fs=fs, output="sos"), rng.randn(n)) * 0.08
    L = mid + side
    R = mid - side
    if wide_bass:
        wb = np.sin(2 * np.pi * 70 * t + 0.3) * wide_bass
        L = L + wb
        R = R - wb
    if sib:
        hiss = signal.sosfilt(signal.butter(4, [5500, 8500], "band", fs=fs, output="sos"), rng.randn(n))
        gate = ((t % 1.5) > 0.6) & ((t % 1.5) < 0.72)
        L = L + hiss * gate * sib
        R = R + hiss * gate * sib
    x = np.column_stack([L, R])
    x = np.tanh(1.6 * x) / np.tanh(1.6)          # compressió tipus «màster de CD»
    return x


def to_cd(x, peak_db=-0.05):
    return x * (10 ** (peak_db / 20.0) / np.max(np.abs(x)))


def make_album(folder, seconds=8.0):
    if not os.path.isdir(folder):
        os.makedirs(folder)
    specs = [
        ("A", "A01_Sibilant.wav", dict(sib=0.55)),
        ("A", "A02_Net.wav", dict()),
        ("A", "A03_Greus_amples.wav", dict(wide_bass=0.35)),
        ("A", "A04_Sibilancia_suau.wav", dict(sib=0.32)),
        ("B", "B01_Net.wav", dict()),
        ("B", "B02_Clipat.wav", dict()),
        ("B", "B03_Final_greus.wav", dict(wide_bass=0.30)),
    ]
    out = {"A": [], "B": []}
    for k, (side, name, kw) in enumerate(specs):
        x = to_cd(music(seconds, k + 1, **kw))
        if "Clipat" in name:
            x = np.clip(x * 1.6, -0.9999, 0.9999)   # tramos planos
        p = os.path.join(folder, name)
        sf.write(p, x, FS, subtype="PCM_16")
        out[side].append(p)
    return out
