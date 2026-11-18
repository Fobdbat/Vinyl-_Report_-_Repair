# -*- coding: utf-8 -*-
"""Validació del motor d'àudio amb senyals de resultat conegut."""
import math
import os
import sys
import unittest

import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from premaster import dsp  # noqa: E402

FS = 44100


def t(dur, fs=FS):
    return np.arange(int(dur * fs)) / float(fs)


def stereo(l, r=None):
    return np.column_stack([l, l if r is None else r])


class DspTests(unittest.TestCase):
    def test_lufs_sine(self):
        # 1 kHz a -20 dBFS als dos canals -> -20,0 LUFS (definició BS.1770)
        x = stereo(0.1 * np.sin(2 * np.pi * 997 * t(10, 48000)))
        self.assertAlmostEqual(dsp.integrated_lufs(x, 48000), -20.0, delta=0.15)
        x = stereo(0.1 * np.sin(2 * np.pi * 997 * t(10)))
        self.assertAlmostEqual(dsp.integrated_lufs(x, FS), -20.0, delta=0.15)

    def test_true_peak_intersample(self):
        # Sinus a fs/4 amb fase de 45º: mostres a 0,707 però pic real 1,0 (+3 dB)
        n = np.arange(FS)
        x = stereo(np.sin(2 * np.pi * n / 4.0 + np.pi / 4))
        self.assertAlmostEqual(dsp.to_db(float(np.max(np.abs(x)))), -3.01, delta=0.02)
        self.assertAlmostEqual(dsp.to_db(dsp.true_peak(x, FS)), 0.0, delta=0.3)

    def test_clip_detection_and_declip(self):
        ceiling = 32767 / 32768.0
        orig = 1.25 * np.sin(2 * np.pi * 1000 * t(1))
        x = stereo(np.clip(orig, -1.0, ceiling))
        fs_count, clipped, segs = dsp.clip_stats(x, 16, False)
        self.assertGreater(fs_count, 100)
        self.assertGreater(clipped, 100)
        y, fixed, skipped = dsp.declip(x)
        self.assertGreater(fixed, 0)
        self.assertEqual(skipped, 0)
        # El pic reconstruït s'acosta a l'original (1,25)
        self.assertGreater(float(y.max()), 1.15)
        err = np.abs(y[:, 0] - orig)
        self.assertLess(float(err.max()), 0.08)

    def test_no_false_clip_on_clean(self):
        x = stereo(0.9 * np.sin(2 * np.pi * 440 * t(1) + 0.3))
        _, clipped, _ = dsp.clip_stats(x, 24, False)
        self.assertEqual(clipped, 0)

    def test_low_band_and_bass_mono(self):
        tt = t(8)
        kick = 0.35 * np.sin(2 * np.pi * 50 * tt)          # greu centrat
        wide_bass = 0.25 * np.sin(2 * np.pi * 80 * tt)     # greu en contrafase
        mid = 0.2 * np.sin(2 * np.pi * 1000 * tt)
        wideL = 0.15 * np.sin(2 * np.pi * 3000 * tt)
        wideR = 0.15 * np.cos(2 * np.pi * 3000 * tt)
        x = np.column_stack([kick + wide_bass + mid + wideL, kick - wide_bass + mid + wideR])
        corr, sm = dsp.low_band_stereo(x, FS)
        self.assertLess(corr, 0.5)
        self.assertGreater(sm, -6)
        y = dsp.bass_mono(x, FS, 150)
        corr2, sm2 = dsp.low_band_stereo(y, FS)
        self.assertGreater(corr2, 0.95)
        self.assertLess(sm2, -20)
        # Els aguts estèreo (3 kHz) no canvien
        hp = signal.butter(4, 1500, "high", fs=FS, output="sos")
        side_before = signal.sosfilt(hp, x[:, 0] - x[:, 1])
        side_after = signal.sosfilt(hp, y[:, 0] - y[:, 1])
        sl = slice(FS, -FS)
        diff_db = dsp.pow_db(np.mean((side_after[sl] - side_before[sl]) ** 2) / np.mean(side_before[sl] ** 2))
        self.assertLess(diff_db, -40)
        # El Mid queda intacte
        self.assertLess(float(np.max(np.abs((y[:, 0] + y[:, 1]) - (x[:, 0] + x[:, 1])))), 1e-9)

    def test_no_bass(self):
        x = stereo(0.3 * np.sin(2 * np.pi * 2000 * t(2)), 0.3 * np.cos(2 * np.pi * 2000 * t(2)))
        self.assertEqual(dsp.low_band_stereo(x, FS), (None, None))

    def test_positive_only_clipping(self):
        orig = 1.3 * np.sin(2 * np.pi * 500 * t(1)) - 0.3
        x = stereo(np.clip(orig, -2, 0.9))     # clipping només als positius, per sota de 0 dBFS
        _, clipped, _ = dsp.clip_stats(x, 24, False)
        self.assertGreater(clipped, 0)
        y, fixed, _ = dsp.declip(x)
        self.assertGreater(float(y.max()), 0.95)

    def test_mono_file(self):
        x = (0.5 * np.sin(2 * np.pi * 100 * t(2)))[:, None]
        corr, sm = dsp.low_band_stereo(x, FS)
        self.assertEqual(corr, 1.0)
        self.assertIsNone(sm)
        m = dsp.measure(x, FS, 16, False)
        self.assertEqual(m["channels"], 1)

    def test_deesser(self):
        rng = np.random.RandomState(1)
        n = 10 * FS
        base = signal.sosfilt(signal.butter(2, 2000, "low", fs=FS, output="sos"), rng.randn(n)) * 0.3
        hiss = signal.sosfilt(signal.butter(4, [6000, 8000], "band", fs=FS, output="sos"), rng.randn(n))
        env = np.zeros(n)
        for k in range(9):
            env[k * FS + FS // 2: k * FS + FS // 2 + int(0.12 * FS)] = 1.0
        x = stereo(base + 0.22 * hiss * env)
        before = dsp.sibilance_db(x, FS)
        self.assertGreater(before, -4)            # sibilància marcada (com A01: -1,9 dB)
        target = before - 7.5
        y, after, red = dsp.deess(x, FS, target_db=target)
        self.assertLessEqual(after, target + 0.3)
        self.assertGreater(red, 3)
        # Per sota de 3 kHz no canvia res
        lp = signal.butter(4, 3000, "low", fs=FS, output="sos")
        d = signal.sosfilt(lp, y[:, 0]) - signal.sosfilt(lp, x[:, 0])
        self.assertLess(dsp.pow_db(np.mean(d ** 2) / np.mean(signal.sosfilt(lp, x[:, 0]) ** 2)), -40)

    def test_deesser_noop_when_ok(self):
        x = stereo(0.3 * np.sin(2 * np.pi * 300 * t(3)))
        y, after, red = dsp.deess(x, FS, target_db=-9.0)
        self.assertEqual(red, 0.0)
        self.assertTrue(np.array_equal(x, y))

    def test_quantize(self):
        x = stereo(0.5 * np.sin(2 * np.pi * 440 * t(0.5)))
        q24 = dsp.quantize(x, 24)
        self.assertEqual(q24.dtype, np.int32)
        back = (q24 >> 8) / float(2 ** 23)
        self.assertLess(float(np.max(np.abs(back - x))), 2.0 / 2 ** 23)
        q16 = dsp.quantize(x, 16)
        self.assertEqual(q16.dtype, np.int16)
        self.assertLess(float(np.max(np.abs(q16 / 32768.0 - x))), 2.0 / 32768)

    def test_null_test(self):
        rng = np.random.RandomState(3)
        a = stereo(rng.randn(5 * FS) * 0.1, rng.randn(5 * FS) * 0.1)
        b = np.vstack([np.zeros((123, 2)), 0.5 * a])
        r = dsp.null_test(a, b, FS)
        self.assertEqual(r["lag"], 123)
        self.assertAlmostEqual(r["gain_db"], 6.02, delta=0.01)
        self.assertLess(r["residual_dbfs"], -200)
        r2 = dsp.null_test(a, a.copy(), FS)
        self.assertEqual(r2["lag"], 0)
        self.assertLess(r2["residual_dbfs"], -200)
        r3 = dsp.null_test(a, -a, FS)
        self.assertLess(r3["gain"], 0)
        c = a.copy()
        c[FS:FS + 100] += 0.01
        r4 = dsp.null_test(a, c, FS)
        self.assertGreater(r4["residual_dbfs"], -100)


if __name__ == "__main__":
    unittest.main()
