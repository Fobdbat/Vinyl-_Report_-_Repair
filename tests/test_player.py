# -*- coding: utf-8 -*-
"""Lògica del reproductor A/B amb una targeta de so simulada."""
import os
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Stop(Exception):
    pass


fake = types.ModuleType("sounddevice")
fake.CallbackStop = _Stop


def _check(samplerate=None, channels=None, dtype=None):
    if samplerate and samplerate > 48000:
        raise ValueError("Invalid sample rate")


fake.check_output_settings = _check
sys.modules["sounddevice"] = fake
from premaster.ui import player as pl  # noqa: E402


class PlayerTests(unittest.TestCase):
    def test_ab_switch_keeps_position_and_level_match(self):
        fs = 44100
        a = np.ones((fs, 2)) * 0.5
        b = np.ones((fs, 2)) * 0.25          # reparat 6 dB més baix
        p = pl.ABPlayer()
        p.load(a, b, fs, lufs_a=-8.0, lufs_b=-8.0 - 20 * np.log10(2))
        out = np.zeros((1000, 2), np.float32)
        p._callback(out, 1000, None, None)
        self.assertAlmostEqual(float(out[0, 0]), 0.5, places=5)
        p.set_which("B")
        p._callback(out, 1000, None, None)
        self.assertAlmostEqual(float(out[0, 0]), 0.25, places=5)
        self.assertEqual(p.pos, 2000)                     # la posició continua
        p.match = True
        p.set_which("A")
        p._callback(out, 1000, None, None)
        self.assertAlmostEqual(float(out[0, 0]), 0.25, places=3)   # A abaixat al nivell de B
        p.seek(0.5)
        self.assertEqual(p.pos, fs // 2)

    def test_end_and_mono_and_resample(self):
        p = pl.ABPlayer()
        p.load(np.ones(96000) * 0.1, np.ones(96000) * 0.1, 96000)
        self.assertEqual(p.fs, 48000)                     # 96 kHz no admès -> 48 kHz
        self.assertEqual(p.a.shape[1], 2)                 # mono -> estèreo
        p.pos = p.length - 10
        out = np.zeros((64, 2), np.float32)
        with self.assertRaises(_Stop):
            p._callback(out, 64, None, None)
        self.assertTrue(np.all(out[10:] == 0))


if __name__ == "__main__":
    unittest.main()
